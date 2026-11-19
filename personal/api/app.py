"""Local Web console API for the personal extension layer."""

from __future__ import annotations

import base64
import binascii
import json
import math
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from personal import __version__
from personal.analytics.journal_outcomes import (
    HORIZONS,
    evaluate_journal_outcomes,
)
from personal.analytics.portfolio_risk import RiskLimits, analyze_portfolio_risk
from personal.analytics.trade_plans import (
    PlanValidationError,
    plan_to_dict,
    preview_trade_plan,
)
from personal.backtest.demo import run_demo_backtest
from personal.backtest.replay import replay_upstream
from personal.backtest.types import BacktestConfig, BacktestResult
from personal.config import Settings, get_settings
from personal.contracts.upstream_db import UpstreamDB
from personal.contracts.version import detect
from personal.datahub.models import (
    AccountPositionSnapshot,
    AccountSnapshot,
    TradePlan,
)
from personal.datahub.normalize import normalize_code
from personal.datahub.screenshot import (
    ScreenshotError,
    confirm_account_snapshot,
    parse_account_screenshot,
)
from personal.datahub.store import PersonalStore
from personal.datahub.sync import DataSyncService, build_sources
from personal.execution.qmt_client import QmtBridgeClient, QmtBridgeError
from personal.plugins.loader import load_plugins

STATIC_DIR = Path(__file__).resolve().parent / "static"


class SyncRequest(BaseModel):
    dataset: Literal["bars", "adjust", "calendar", "status"] = "bars"
    source: str = "auto"
    codes: Optional[list[str]] = None
    start: Optional[str] = None
    end: Optional[str] = None
    cross_check: Optional[bool] = None


class MarketSyncRequest(BaseModel):
    dataset: Literal[
        "futures", "margin", "turnover", "zt", "pcr", "cffex_rank",
        "sector", "etf_share", "bond", "release",
    ] = "futures"
    start: Optional[str] = None
    end: Optional[str] = None


class DemoRequest(BaseModel):
    days: int = Field(default=400, ge=60, le=3000)
    save: bool = False


class ReplayRequest(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    include: Literal["both", "analyses", "signals"] = "both"
    save: bool = False
    adjust: Optional[Literal["hfq", "qfq", "none"]] = None


class BrokerImportRequest(BaseModel):
    """Statement upload as base64 (avoids a multipart dependency)."""

    filename: str
    content_b64: str
    column_map: Optional[dict[str, str]] = None
    plan_id: Optional[int] = None


class ScreenshotParseRequest(BaseModel):
    filename: str
    content_b64: str


class AccountPositionRequest(BaseModel):
    code: str
    name: str = ""
    quantity: float = 0
    available_quantity: Optional[float] = None
    avg_cost: Optional[float] = None
    market_price: Optional[float] = None
    market_value: Optional[float] = None
    pnl: Optional[float] = None


class AccountSnapshotRequest(BaseModel):
    account_alias: str = "同花顺"
    as_of: date
    cash: Optional[float] = None
    available_cash: Optional[float] = None
    market_value: Optional[float] = None
    equity: Optional[float] = None
    source_file: str = ""
    content_hash: str = ""
    ocr_engine: str = ""
    positions: list[AccountPositionRequest] = Field(default_factory=list)


class TradePlanRequest(BaseModel):
    plan_date: Optional[date] = None
    valid_until: Optional[date] = None
    code: str
    name: str = ""
    side: Literal["buy", "sell"]
    entry_low: float
    entry_high: float
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    risk_budget_pct: Optional[float] = None
    risk_budget_amount: Optional[float] = None
    max_position_pct: Optional[float] = None
    requested_quantity: Optional[float] = None
    account_snapshot_id: Optional[int] = None
    status: Literal["draft", "active", "closed", "cancelled"] = "draft"
    thesis: str = ""
    catalyst: str = ""
    invalidation: str = ""
    horizon_days: Optional[int] = Field(default=None, ge=1, le=3650)
    analysis_id: Optional[int] = None
    decision_signal_id: Optional[int] = None


class PlanStatusRequest(BaseModel):
    status: Literal["draft", "active", "closed", "cancelled"]


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _parse_date(value: Optional[str], default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid date: {value}") from exc


def _decode_base64_image(content_b64: str, max_mb: float) -> bytes:
    if not content_b64:
        raise HTTPException(status_code=400, detail="图片内容为空")
    max_bytes = int(max_mb * 1024 * 1024)
    if max_bytes > 0 and len(content_b64) > max_bytes * 4 // 3 + 16:
        raise HTTPException(status_code=400, detail=f"图片超过 {max_mb:g}MB 限制")
    try:
        content = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="图片 base64 无效") from exc
    if max_bytes > 0 and len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"图片超过 {max_mb:g}MB 限制")
    if not content:
        raise HTTPException(status_code=400, detail="图片内容为空")
    return content


def _account_positions_payload(
    positions: list[AccountPositionSnapshot],
) -> list[dict[str, Any]]:
    return [
        {
            "code": position.code,
            "name": position.name,
            "quantity": position.quantity,
            "available_quantity": position.available_quantity,
            "avg_cost": position.avg_cost,
            "market_price": position.market_price,
            "market_value": position.market_value,
            "pnl": position.pnl,
        }
        for position in positions
    ]


def _account_snapshot_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = dict(snapshot)
    positions = payload.pop("positions", [])
    if positions and isinstance(positions[0], AccountPositionSnapshot):
        payload["positions"] = _account_positions_payload(positions)
    else:
        payload["positions"] = positions
    return _json_safe(payload)


def _risk_limits(settings: Settings) -> RiskLimits:
    return RiskLimits(
        max_single_pct=settings.risk_max_single_pct,
        max_top5_pct=settings.risk_max_top5_pct,
        min_cash_pct=settings.risk_min_cash_pct,
        max_liquidation_days=settings.risk_max_liquidation_days,
        max_correlation=settings.risk_max_correlation,
        default_budget_pct=settings.risk_default_budget_pct,
    )


def _plan_from_request(
    request: TradePlanRequest,
    *,
    account_snapshot_id: int | None = None,
    preview_json: str = "",
    default_risk_budget_pct: float | None = None,
) -> TradePlan:
    try:
        code = normalize_code(request.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if request.entry_low > request.entry_high:
        raise HTTPException(status_code=400, detail="价格区间下限不能高于上限")
    if request.risk_budget_pct is not None and request.risk_budget_amount is not None:
        raise HTTPException(
            status_code=400, detail="风险预算比例和金额只能填写一个"
        )
    risk_budget_pct = request.risk_budget_pct
    if (
        request.side == "buy"
        and risk_budget_pct is None
        and request.risk_budget_amount is None
        and default_risk_budget_pct is not None
    ):
        risk_budget_pct = default_risk_budget_pct
    return TradePlan(
        plan_date=request.plan_date or date.today(),
        valid_until=request.valid_until,
        code=code,
        name=request.name.strip(),
        side=request.side,
        entry_low=request.entry_low,
        entry_high=request.entry_high,
        stop_loss=request.stop_loss,
        target_price=request.target_price,
        risk_budget_pct=risk_budget_pct,
        risk_budget_amount=request.risk_budget_amount,
        max_position_pct=request.max_position_pct,
        requested_quantity=request.requested_quantity,
        account_snapshot_id=account_snapshot_id or request.account_snapshot_id,
        status=request.status,
        thesis=request.thesis.strip(),
        catalyst=request.catalyst.strip(),
        invalidation=request.invalidation.strip(),
        horizon_days=request.horizon_days,
        analysis_id=request.analysis_id,
        decision_signal_id=request.decision_signal_id,
        preview_json=preview_json,
    )


def _resolve_plan_snapshot(
    store: PersonalStore, request: TradePlanRequest
) -> dict[str, Any]:
    snapshot = (
        store.get_account_snapshot(request.account_snapshot_id)
        if request.account_snapshot_id is not None
        else store.get_latest_account_snapshot(include_positions=True)
    )
    if snapshot is None:
        raise HTTPException(
            status_code=400,
            detail="没有账户快照，请先在账本中导入同花顺资产/持仓截图",
        )
    return snapshot


def _preview_plan(
    settings: Settings,
    store: PersonalStore,
    request: TradePlanRequest,
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = _resolve_plan_snapshot(store, request)
    plan = _plan_from_request(
        request,
        account_snapshot_id=int(snapshot["id"]),
        default_risk_budget_pct=settings.risk_default_budget_pct,
    )
    try:
        preview = preview_trade_plan(
            plan,
            snapshot,
            list(snapshot.get("positions") or []),
            limits=_risk_limits(settings),
        )
    except PlanValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return plan, preview


def _require_preview_saved(preview: dict[str, Any]) -> None:
    blockers = preview.get("blockers") or []
    if blockers:
        raise HTTPException(status_code=400, detail="；".join(blockers))


def _result_payload(result: BacktestResult) -> dict[str, Any]:
    equity = [
        {"date": index.isoformat(), "value": float(value)}
        for index, value in result.equity_curve.items()
    ]
    benchmark = None
    if result.benchmark_curve is not None:
        benchmark = [
            {"date": index.isoformat(), "value": float(value)}
            for index, value in result.benchmark_curve.items()
        ]
    trades = [
        {
            "date": trade.trade_date.isoformat(),
            "code": trade.code,
            "side": trade.side,
            "quantity": float(trade.quantity),
            "price": float(trade.price),
            "gross_amount": float(trade.gross_amount),
            "fee": float(trade.fee),
            "realized_pnl": float(trade.realized_pnl),
            "reason": trade.reason,
        }
        for trade in result.trades
    ]
    return {
        "metrics": _json_safe(result.metrics),
        "equity": equity,
        "benchmark": benchmark,
        "trades": trades,
        "final_cash": float(result.final_cash),
        "final_positions": {
            code: float(quantity) for code, quantity in result.final_positions.items()
        },
    }


def create_app(settings_override: Optional[Settings] = None) -> FastAPI:
    settings = settings_override or get_settings()
    app = FastAPI(title="DSA Personal Console", version=__version__)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        capabilities = detect(settings.upstream_db)
        store = PersonalStore(settings.personal_db)
        try:
            stats = store.stats()
            coverage = store.coverage()
            runs = store.list_backtest_runs(limit=5)
            quality = store.list_quality_events(limit=5)
            sync_state = store.get_sync_state()
        finally:
            store.close()

        registry, plugin_errors = load_plugins(
            settings.plugin_dirs, settings.plugin_allowlist
        )
        return _json_safe(
            {
                "app": {"version": __version__},
                "settings": {
                    "root": str(settings.root),
                    "personal_db": str(settings.personal_db),
                    "upstream_db": str(settings.upstream_db),
                    "stock_list": list(settings.stock_list),
                    "data_source_priority": list(settings.data_source_priority),
                },
                "upstream": {
                    "available": capabilities.available,
                    "has_analysis_history": capabilities.has_analysis_history,
                    "has_portfolio": capabilities.has_portfolio,
                    "has_decision_signals": capabilities.has_decision_signals,
                    "missing": list(capabilities.missing),
                },
                "storage": stats,
                "coverage": coverage,
                "plugins": [
                    {
                        "name": item.manifest.name,
                        "version": item.manifest.version,
                        "type": item.manifest.type,
                        "display_name": item.manifest.display_name,
                    }
                    for item in registry.all()
                ],
                "plugin_errors": plugin_errors,
                "recent_runs": runs,
                "recent_quality": quality,
                "sync_state": sync_state,
                "qmt": {
                    "bridge_url": settings.qmt_bridge_url,
                    "trading_enabled": settings.qmt_trading_enabled,
                    "require_confirm": settings.qmt_require_confirm,
                },
            }
        )

    @app.get("/api/plugins")
    def plugins() -> dict[str, Any]:
        registry, errors = load_plugins(settings.plugin_dirs, settings.plugin_allowlist)
        return {
            "plugins": [
                {
                    "name": item.manifest.name,
                    "version": item.manifest.version,
                    "type": item.manifest.type,
                    "display_name": item.manifest.display_name,
                    "description": item.manifest.description,
                    "permissions": list(item.manifest.permissions),
                }
                for item in registry.all()
            ],
            "errors": errors,
        }

    @app.get("/api/data/coverage")
    def coverage() -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            return {"coverage": store.coverage(), "stats": store.stats()}
        finally:
            store.close()

    @app.get("/api/data/quality")
    def quality(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            return {"events": store.list_quality_events(limit=limit)}
        finally:
            store.close()

    @app.get("/api/market/breadth")
    def market_breadth(days: int = Query(default=30, ge=1, le=500)) -> dict[str, Any]:
        """Recent market breadth / TRIN rows (oldest -> newest)."""
        store = PersonalStore(settings.personal_db)
        try:
            rows = store.get_market_breadth(limit=days)
        finally:
            store.close()
        return {
            "rows": [
                {
                    "trade_date": row.trade_date.isoformat(),
                    "up_count": row.up_count,
                    "down_count": row.down_count,
                    "flat_count": row.flat_count,
                    "sample_count": row.sample_count,
                    "up_vol_yi": row.up_vol_yi,
                    "down_vol_yi": row.down_vol_yi,
                    "up_amount_yi": row.up_amount_yi,
                    "down_amount_yi": row.down_amount_yi,
                    "adv_ratio": row.adv_ratio,
                    "trin": row.trin,
                    "trin_amount": row.trin_amount,
                    "trin_pct": row.trin_pct,
                    "interpretation": row.interpretation,
                    "band": row.band,
                    "index_close": row.index_close,
                    "index_chg_pct": row.index_chg_pct,
                    "index_pos": row.index_pos,
                    "divergence": row.divergence,
                    "signal_tag": row.signal_tag,
                    "signal_detail": row.signal_detail,
                    "source": row.source,
                }
                for row in rows
            ]
        }

    @app.post("/api/data/sync")
    def sync(request: SyncRequest) -> dict[str, Any]:
        codes = request.codes or list(settings.stock_list)
        if not codes and request.dataset != "calendar":
            raise HTTPException(
                status_code=400,
                detail="no codes: pass codes or set PERSONAL_STOCK_LIST",
            )
        end = _parse_date(request.end, date.today())
        start = _parse_date(request.start, end - timedelta(days=730))
        cross_check = (
            settings.cross_source_check
            if request.cross_check is None
            else request.cross_check
        )
        try:
            sources = build_sources(settings, request.source)
            store = PersonalStore(settings.personal_db)
            try:
                service = DataSyncService(
                    store,
                    sources,
                    cross_check=cross_check,
                    preferred_sources=settings.data_source_priority,
                )
                if request.dataset == "adjust":
                    results = service.sync_adjust_factors(codes, start, end)
                elif request.dataset == "calendar":
                    results = [service.sync_calendar(start, end)]
                elif request.dataset == "status":
                    results = service.sync_trading_status(codes, start, end)
                else:
                    results = service.sync_daily_bars(codes, start, end)
            finally:
                store.close()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _json_safe(
            {
                "dataset": request.dataset,
                "start": start,
                "end": end,
                "results": [asdict(item) for item in results],
            }
        )

    @app.get("/api/market/futures")
    def market_futures(days: int = Query(default=20, ge=1, le=500)) -> dict[str, Any]:
        """Recent CFFEX main-contract rows (IF/IH/IC/IM), oldest -> newest."""
        store = PersonalStore(settings.personal_db)
        try:
            rows = store.get_index_futures(limit=days)
        finally:
            store.close()
        return {
            "rows": [
                {
                    "trade_date": row.trade_date.isoformat(),
                    "symbol": row.symbol,
                    "close": row.close,
                    "volume": row.volume,
                    "open_interest": row.open_interest,
                    "oi_chg": row.oi_chg,
                    "index_close": row.index_close,
                    "basis": row.basis,
                    "basis_pct": row.basis_pct,
                    "source": row.source,
                }
                for row in rows
            ]
        }

    @app.get("/api/market/margin")
    def market_margin(days: int = Query(default=20, ge=1, le=500)) -> dict[str, Any]:
        """Recent margin-financing balances (market + board scopes), oldest -> newest."""
        store = PersonalStore(settings.personal_db)
        try:
            # 7 scopes per day (总计/沪市/深市 + 4 boards) + slack
            rows = store.get_margin_balance(limit=days * 8)
        finally:
            store.close()
        return {
            "rows": [
                {
                    "trade_date": row.trade_date.isoformat(),
                    "scope_type": row.scope_type,
                    "scope": row.scope,
                    "rzye": row.rzye,
                    "rqye": row.rqye,
                    "rzrqye": row.rzrqye,
                    "rzye_buy": row.rzye_buy,
                    "source": row.source,
                }
                for row in rows
            ]
        }

    @app.post("/api/market/sync")
    def market_sync(request: MarketSyncRequest) -> dict[str, Any]:
        from personal.datahub.market import (
            sync_bond_yield,
            sync_etf_share,
            sync_futures_rank,
            sync_index_futures,
            sync_limit_up,
            sync_margin_balance,
            sync_option_pcr,
            sync_restricted_release,
            sync_sector_amount,
            sync_turnover,
        )

        end = _parse_date(request.end, date.today())
        start = _parse_date(request.start, end - timedelta(days=10))
        dispatch = {
            "futures": lambda store: sync_index_futures(store, start=start, end=end),
            "margin": lambda store: sync_margin_balance(
                store,
                start=start,
                end=end,
                stock_codes=list(
                    dict.fromkeys(
                        [
                            *settings.stock_list,
                            *store.broker_position_codes(),
                            *store.account_position_codes(),
                        ]
                    )
                ),
            ),
            "turnover": lambda store: sync_turnover(store, start=start, end=end),
            "zt": lambda store: sync_limit_up(store, start=start, end=end),
            "pcr": lambda store: sync_option_pcr(store, start=start, end=end),
            "cffex_rank": lambda store: sync_futures_rank(store, start=start, end=end),
            "sector": lambda store: sync_sector_amount(
                store, trade_date=end if request.end else None
            ),
            "etf_share": lambda store: sync_etf_share(
                store, trade_date=end if request.end else None
            ),
            "bond": lambda store: sync_bond_yield(store),
            "release": lambda store: sync_restricted_release(store, start=start, end=end),
        }
        store = PersonalStore(settings.personal_db)
        try:
            result = dispatch[request.dataset](store)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            store.close()
        return _json_safe(result.as_dict())

    @app.get("/api/market/limitup")
    def market_limitup(days: int = Query(default=20, ge=1, le=500)) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            rows = store.get_limit_up_stats(limit=days)
        finally:
            store.close()
        return {
            "rows": [
                {
                    "trade_date": row.trade_date.isoformat(),
                    "zt_count": row.zt_count,
                    "first_board": row.first_board,
                    "streak_ge2": row.streak_ge2,
                    "max_streak": row.max_streak,
                    "zb_count": row.zb_count,
                    "zb_rate": row.zb_rate,
                    "prev_zt_mean": row.prev_zt_mean,
                    "prev_zt_up_ratio": row.prev_zt_up_ratio,
                }
                for row in rows
            ]
        }

    @app.get("/api/market/pcr")
    def market_pcr(
        days: int = Query(default=20, ge=1, le=500),
        underlying: str = Query(default="50ETF"),
    ) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            rows = store.get_option_pcr(limit=days, underlying=underlying)
        finally:
            store.close()
        return {
            "underlying": underlying,
            "rows": [
                {
                    "trade_date": row.trade_date.isoformat(),
                    "call_vol": row.call_vol,
                    "put_vol": row.put_vol,
                    "pcr_vol": row.pcr_vol,
                    "call_oi": row.call_oi,
                    "put_oi": row.put_oi,
                    "pcr_oi": row.pcr_oi,
                }
                for row in rows
            ],
        }

    @app.get("/api/market/cffex-rank")
    def market_cffex_rank(days: int = Query(default=20, ge=1, le=500)) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            rows = store.get_futures_rank(limit=days * 4)
        finally:
            store.close()
        return {
            "rows": [
                {
                    "trade_date": row.trade_date.isoformat(),
                    "symbol": row.symbol,
                    "contracts": row.contracts,
                    "top20_buy": row.top20_buy,
                    "top20_sell": row.top20_sell,
                    "net": row.net,
                    "net_ratio": row.net_ratio,
                }
                for row in rows
            ]
        }

    @app.get("/api/market/flows")
    def market_flows(days: int = Query(default=30, ge=1, le=500)) -> dict[str, Any]:
        """Turnover + margin-buy ratio + broad ETF shares (server-side join)."""
        from personal.datahub.composite import _margin_ratios

        store = PersonalStore(settings.personal_db)
        try:
            ratios = _margin_ratios(store, date.today() - timedelta(days=days * 2), date.today())
            ratios = ratios[-days:]
            turnover_rows = store.get_market_turnover(limit=days)
            etf_rows = store.get_etf_share(limit=days * len(
                ("510050", "510300", "510500", "512100", "159915", "588000", "159949")
            ))
        finally:
            store.close()
        return {
            "margin_ratio": [
                {"trade_date": day.isoformat(), "ratio_pct": value}
                for day, value in ratios
            ],
            "turnover": [
                {
                    "trade_date": row.trade_date.isoformat(),
                    "total_amount_yi": round(row.total_amount / 1e8, 1) if row.total_amount else None,
                }
                for row in turnover_rows
            ],
            "etf_share": [
                {
                    "trade_date": row.trade_date.isoformat(),
                    "code": row.code,
                    "name": row.name,
                    "share_yi": row.share_yi,
                }
                for row in etf_rows
            ],
        }

    @app.get("/api/market/crowding")
    def market_crowding(days: int = Query(default=30, ge=1, le=500)) -> dict[str, Any]:
        """Industry-turnover share with 250-day percentile per board."""
        from collections import defaultdict

        store = PersonalStore(settings.personal_db)
        try:
            rows = store.get_sector_amounts(limit=days * 100)
        finally:
            store.close()
        history: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            if row.share_pct is not None:
                history[row.board].append(row.share_pct)
        latest_day = max((row.trade_date for row in rows), default=None)
        latest = [
            row for row in rows
            if latest_day is not None and row.trade_date == latest_day and row.share_pct
        ]
        latest.sort(key=lambda row: row.share_pct or 0, reverse=True)
        from personal.datahub.composite import percentile_rank

        return {
            "trade_date": latest_day.isoformat() if latest_day else None,
            "rows": [
                {
                    "board": row.board,
                    "amount_yi": row.amount_yi,
                    "share_pct": row.share_pct,
                    "pct_chg": row.pct_chg,
                    "share_pctile": percentile_rank(history[row.board], row.share_pct),
                    "samples": len(history[row.board]),
                }
                for row in latest[:15]
            ],
        }

    @app.get("/api/market/macro")
    def market_macro(days: int = Query(default=120, ge=1, le=2000)) -> dict[str, Any]:
        """CN/US yield spreads + upcoming restricted-release calendar."""
        store = PersonalStore(settings.personal_db)
        try:
            bonds = store.get_bond_yield(limit=days)
            releases = store.get_restricted_release(
                start=date.today(), end=date.today() + timedelta(days=60)
            )
        finally:
            store.close()
        return {
            "bond_yield": [
                {
                    "trade_date": row.trade_date.isoformat(),
                    "cn_10y": row.cn_10y,
                    "us_10y": row.us_10y,
                    "spread_10y": row.spread_10y,
                    "spread_2y": row.spread_2y,
                }
                for row in bonds
            ],
            "release": [
                {
                    "release_date": row.release_date.isoformat(),
                    "company_count": row.company_count,
                    "market_value_yi": row.market_value_yi,
                }
                for row in releases
            ],
        }

    @app.get("/api/market/composite")
    def market_composite() -> dict[str, Any]:
        from personal.datahub.composite import composite_score

        store = PersonalStore(settings.personal_db)
        try:
            payload = composite_score(store)
        finally:
            store.close()
        return _json_safe(payload.as_dict())

    @app.get("/api/market/validate")
    def market_validate(
        days: int = Query(default=400, ge=0, le=5000),
        online: bool = Query(default=False),
    ) -> dict[str, Any]:
        """Indicator data health: identities, ranges, gaps, optional cross-source."""
        from personal.datahub.validate import validate_store

        store = PersonalStore(settings.personal_db)
        try:
            payload = validate_store(store, days=days, online=online)
        finally:
            store.close()
        return _json_safe(payload.as_dict())

    # ------------------------------------------------------------------
    # Broker ledger (交割单 / 持仓 / 决策快照) — RM-12/15/42
    # ------------------------------------------------------------------
    @app.post("/api/broker/import")
    def broker_import(request: BrokerImportRequest) -> dict[str, Any]:
        from personal.datahub.broker import import_statement

        try:
            content = base64.b64decode(request.content_b64, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid base64: {exc}")
        if not content:
            raise HTTPException(status_code=400, detail="empty file")
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="交割单文件超过 20MB 限制")
        store = PersonalStore(settings.personal_db)
        try:
            summary = import_statement(
                store,
                request.filename,
                content,
                column_map=request.column_map,
                plan_id=request.plan_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            store.close()
        return _json_safe(summary.as_dict())

    @app.get("/api/broker/positions")
    def broker_positions() -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            rows = store.get_broker_positions()
        finally:
            store.close()
        return {"positions": _json_safe(rows)}

    @app.get("/api/broker/journal")
    def broker_journal(
        limit: int = Query(default=100, ge=1, le=1000),
        code: Optional[str] = Query(default=None),
    ) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            rows = store.list_journal(limit=limit, code=code)
        finally:
            store.close()
        for row in rows:
            if row.get("snapshot"):
                try:
                    row["snapshot"] = json.loads(row["snapshot"])
                except (TypeError, ValueError):
                    pass
        return {"journal": _json_safe(rows)}

    # ------------------------------------------------------------------
    # Account snapshots (同花顺截图 / 手工快照)
    # ------------------------------------------------------------------
    @app.post("/api/account-snapshots/parse")
    def account_snapshot_parse(request: ScreenshotParseRequest) -> dict[str, Any]:
        content = _decode_base64_image(
            request.content_b64, settings.ocr_max_image_mb
        )
        try:
            result = parse_account_screenshot(
                content,
                filename=request.filename,
                max_mb=settings.ocr_max_image_mb,
                enabled=settings.ocr_enabled,
            )
        except ScreenshotError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _json_safe(result)

    @app.post("/api/account-snapshots")
    def account_snapshot_confirm(request: AccountSnapshotRequest) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            snapshot_id, snapshot, warnings = confirm_account_snapshot(
                store,
                {
                    "cash": request.cash,
                    "available_cash": request.available_cash,
                    "market_value": request.market_value,
                    "equity": request.equity,
                    "positions": [
                        {
                            "code": position.code,
                            "name": position.name,
                            "quantity": position.quantity,
                            "available_quantity": position.available_quantity,
                            "avg_cost": position.avg_cost,
                            "market_price": position.market_price,
                            "market_value": position.market_value,
                            "pnl": position.pnl,
                        }
                        for position in request.positions
                    ],
                },
                account_alias=request.account_alias,
                as_of=request.as_of,
                source_file=request.source_file,
                content_hash=request.content_hash,
                ocr_engine=request.ocr_engine,
            )
            payload = store.get_account_snapshot(snapshot_id)
        except ScreenshotError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            store.close()
        return {
            "snapshot_id": snapshot_id,
            "snapshot": _account_snapshot_payload(payload or {}),
            "warnings": warnings,
        }

    @app.get("/api/account-snapshots/latest")
    def account_snapshot_latest(
        account_alias: Optional[str] = Query(default=None),
    ) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            snapshot = store.get_latest_account_snapshot(
                account_alias=account_alias, include_positions=True
            )
        finally:
            store.close()
        return {
            "snapshot": (
                _account_snapshot_payload(snapshot) if snapshot is not None else None
            )
        }

    @app.get("/api/account-snapshots")
    def account_snapshots(
        limit: int = Query(default=20, ge=1, le=200),
        account_alias: Optional[str] = Query(default=None),
    ) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            rows = store.list_account_snapshots(
                limit=limit, account_alias=account_alias
            )
        finally:
            store.close()
        return {"snapshots": _json_safe(rows)}

    # ------------------------------------------------------------------
    # Trade plans and portfolio risk
    # ------------------------------------------------------------------
    @app.get("/api/portfolio/risk")
    def portfolio_risk(
        account_alias: Optional[str] = Query(default=None),
    ) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            payload = analyze_portfolio_risk(
                store,
                account_alias=account_alias,
                benchmark_code=settings.backtest_benchmark or None,
                limits=_risk_limits(settings),
                today=date.today(),
            )
        finally:
            store.close()
        return _json_safe(payload)

    @app.post("/api/trade-plans/preview")
    def trade_plan_preview(request: TradePlanRequest) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            plan, preview = _preview_plan(settings, store, request)
        finally:
            store.close()
        return _json_safe(
            {
                "plan": plan_to_dict(plan),
                "preview": preview,
            }
        )

    @app.post("/api/trade-plans")
    def trade_plan_create(request: TradePlanRequest) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            plan, preview = _preview_plan(settings, store, request)
            _require_preview_saved(preview)
            plan = _plan_from_request(
                request,
                account_snapshot_id=int(preview["snapshot_id"]),
                preview_json=json.dumps(preview, ensure_ascii=False),
                default_risk_budget_pct=settings.risk_default_budget_pct,
            )
            plan_id = store.create_trade_plan(plan)
            payload = store.get_trade_plan(plan_id)
        except PlanValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            store.close()
        return {"plan": _json_safe(payload), "preview": _json_safe(preview)}

    @app.put("/api/trade-plans/{plan_id}")
    def trade_plan_update(
        plan_id: int, request: TradePlanRequest
    ) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            if store.get_trade_plan(plan_id) is None:
                raise HTTPException(status_code=404, detail="交易计划不存在")
            plan, preview = _preview_plan(settings, store, request)
            _require_preview_saved(preview)
            plan = _plan_from_request(
                request,
                account_snapshot_id=int(preview["snapshot_id"]),
                preview_json=json.dumps(preview, ensure_ascii=False),
                default_risk_budget_pct=settings.risk_default_budget_pct,
            )
            if not store.update_trade_plan(plan_id, plan):
                raise HTTPException(status_code=404, detail="交易计划不存在")
            payload = store.get_trade_plan(plan_id)
        except PlanValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            store.close()
        return {"plan": _json_safe(payload), "preview": _json_safe(preview)}

    @app.patch("/api/trade-plans/{plan_id}")
    def trade_plan_status(
        plan_id: int, request: PlanStatusRequest
    ) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            if not store.update_trade_plan_status(plan_id, request.status):
                raise HTTPException(status_code=404, detail="交易计划不存在")
            payload = store.get_trade_plan(plan_id)
        finally:
            store.close()
        return {"plan": _json_safe(payload)}

    @app.get("/api/trade-plans")
    def trade_plans(
        status_filter: Optional[str] = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            rows = store.list_trade_plans(status=status_filter, limit=limit)
        finally:
            store.close()
        return {"plans": _json_safe(rows)}

    @app.get("/api/trade-plans/{plan_id}")
    def trade_plan_detail(plan_id: int) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            payload = store.get_trade_plan(plan_id)
        finally:
            store.close()
        if payload is None:
            raise HTTPException(status_code=404, detail="交易计划不存在")
        return {"plan": _json_safe(payload)}

    # ------------------------------------------------------------------
    # Decision outcomes (逐笔交易结果)
    # ------------------------------------------------------------------
    @app.get("/api/journal/outcomes")
    def journal_outcomes(
        horizon: int = Query(default=20, ge=1, le=250),
        days: int = Query(default=365, ge=1, le=5000),
        code: Optional[str] = Query(default=None),
        side: Optional[str] = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            payload = evaluate_journal_outcomes(
                store,
                horizon=horizon,
                days=days,
                code=code,
                side=side,
                limit=limit,
                benchmark_code=settings.backtest_benchmark or None,
                adjust_mode=settings.backtest_adjust_mode,
                today=date.today(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            store.close()
        payload["available_horizons"] = list(HORIZONS)
        return _json_safe(payload)

    @app.get("/api/margin/stocks")
    def margin_stocks(
        days: int = Query(default=30, ge=1, le=1000),
        code: Optional[str] = Query(default=None),
    ) -> dict[str, Any]:
        """持仓股两融：latest snapshot per code + per-code rzye series."""
        store = PersonalStore(settings.personal_db)
        try:
            end = date.today()
            start = end - timedelta(days=days)
            rows = store.get_margin_stock(code=code, start=start, end=end)
        finally:
            store.close()
        by_code: dict[str, list[dict[str, Any]]] = {}
        names: dict[str, str] = {}
        for row in rows:
            names.setdefault(row.code, row.name or "")
            by_code.setdefault(row.code, []).append(
                {
                    "trade_date": row.trade_date.isoformat(),
                    "rzye": row.rzye,
                    "rzye_buy": row.rzye_buy,
                    "rqye": row.rqye,
                }
            )
        latest = []
        for code_value, series in sorted(by_code.items()):
            last = series[-1]
            change = None
            if len(series) >= 2 and series[-2]["rzye"] and last["rzye"]:
                change = round(
                    (last["rzye"] - series[-2]["rzye"]) / series[-2]["rzye"] * 100, 2
                )
            latest.append(
                {
                    "code": code_value,
                    "name": names.get(code_value, ""),
                    "trade_date": last["trade_date"],
                    "rzye": last["rzye"],
                    "rzye_buy": last["rzye_buy"],
                    "rqye": last["rqye"],
                    "rzye_chg_pct": change,
                    "series": series,
                }
            )
        return {"stocks": _json_safe(latest)}

    @app.get("/api/backtest/runs")
    def runs() -> dict[str, Any]:
        store = PersonalStore(settings.personal_db)
        try:
            return {"runs": store.list_backtest_runs(limit=30)}
        finally:
            store.close()

    @app.post("/api/backtest/demo")
    def demo(request: DemoRequest) -> dict[str, Any]:
        run = run_demo_backtest(settings, days=request.days)
        payload = _result_payload(run.result)
        payload.update(
            {
                "kind": "demo",
                "start": run.start.isoformat(),
                "end": run.end.isoformat(),
                "codes": list(run.codes),
                "signals": len(run.signals),
            }
        )
        if request.save:
            run_id = f"demo-{uuid.uuid4().hex[:12]}"
            store = PersonalStore(settings.personal_db)
            try:
                store.save_backtest_run(
                    run_id,
                    "demo",
                    run.start,
                    run.end,
                    {"codes": list(run.codes), "days": request.days},
                    payload["metrics"],
                )
                store.save_backtest_trades(run_id, run.result.trades)
            finally:
                store.close()
            payload["run_id"] = run_id
        return _json_safe(payload)

    @app.post("/api/backtest/replay")
    def replay(request: ReplayRequest) -> dict[str, Any]:
        end = _parse_date(request.end, date.today())
        start = _parse_date(request.start, end - timedelta(days=365))
        db = UpstreamDB(settings.upstream_db)
        if not db.available:
            raise HTTPException(
                status_code=400,
                detail=f"upstream database missing: {settings.upstream_db}",
            )
        store = PersonalStore(settings.personal_db)
        config = BacktestConfig(
            start=start,
            end=end,
            initial_cash=settings.backtest_initial_cash,
            benchmark=settings.backtest_benchmark or None,
            adjust_mode=request.adjust or settings.backtest_adjust_mode,
        )
        try:
            result, signals = replay_upstream(
                db,
                store,
                config,
                include_analyses=request.include in {"both", "analyses"},
                include_signals=request.include in {"both", "signals"},
                preferred_sources=settings.data_source_priority,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            db.close()
            store.close()

        payload = _result_payload(result)
        payload.update(
            {
                "kind": "replay",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "signals": len(signals),
            }
        )
        if request.save:
            run_id = f"replay-{uuid.uuid4().hex[:12]}"
            store = PersonalStore(settings.personal_db)
            try:
                store.save_backtest_run(
                    run_id,
                    "signal_replay",
                    start,
                    end,
                    {"include": request.include, "signals": len(signals)},
                    payload["metrics"],
                )
                store.save_backtest_trades(run_id, result.trades)
            finally:
                store.close()
            payload["run_id"] = run_id
        return _json_safe(payload)

    @app.get("/api/upstream/recent")
    def upstream_recent(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
        db = UpstreamDB(settings.upstream_db)
        if not db.available:
            return {
                "available": False,
                "missing": f"database missing: {settings.upstream_db}",
                "analyses": [],
                "signals": [],
            }
        try:
            analyses = db.recent_analyses(limit=limit)
            signals = db.recent_decision_signals(limit=limit)
        finally:
            db.close()
        return {
            "available": True,
            "analyses": [
                {
                    "id": item.id,
                    "code": item.code,
                    "name": item.name,
                    "advice": item.operation_advice,
                    "score": item.sentiment_score,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in analyses
            ],
            "signals": [
                {
                    "id": item.id,
                    "code": item.stock_code,
                    "action": item.action,
                    "score": item.score,
                    "confidence": item.confidence,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in signals
            ],
        }

    @app.get("/api/qmt/health")
    def qmt_health() -> dict[str, Any]:
        client = QmtBridgeClient(
            settings.qmt_bridge_url,
            token=settings.qmt_bridge_token,
            timeout=3.0,
        )
        try:
            return {"ok": True, "detail": client.health()}
        except QmtBridgeError as exc:
            return {"ok": False, "detail": str(exc)}

    return app


app = create_app()
