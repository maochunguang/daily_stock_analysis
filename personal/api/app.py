"""Local Web console API for the personal extension layer."""

from __future__ import annotations

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
from personal.backtest.demo import run_demo_backtest
from personal.backtest.replay import replay_upstream
from personal.backtest.types import BacktestConfig, BacktestResult
from personal.config import Settings, get_settings
from personal.contracts.upstream_db import UpstreamDB
from personal.contracts.version import detect
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


class DemoRequest(BaseModel):
    days: int = Field(default=400, ge=60, le=3000)
    save: bool = False


class ReplayRequest(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    include: Literal["both", "analyses", "signals"] = "both"
    save: bool = False
    adjust: Optional[Literal["hfq", "qfq", "none"]] = None


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
