"""Portfolio risk from a confirmed account snapshot.

This module is read-only. It never reads the upstream database and never places
orders. Market-risk metrics are computed only for positions with local daily
bars; coverage is reported explicitly so a partial portfolio is not mistaken
for the whole account.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from ..datahub.adjust import adjust_bars
from ..datahub.models import AccountPositionSnapshot, DailyBar
from ..datahub.normalize import is_etf_code, normalize_code
from ..datahub.store import PersonalStore

TRADING_DAYS = 244
MIN_HISTORY_BARS = 21
LOOKBACK_DAYS = 200
LIQUIDITY_BARS = 20


@dataclass(frozen=True)
class RiskLimits:
    max_single_pct: float = 20.0
    max_top5_pct: float = 60.0
    min_cash_pct: float = 5.0
    max_liquidation_days: float = 5.0
    max_correlation: float = 0.85
    default_budget_pct: float = 1.0


def analyze_portfolio_risk(
    store: PersonalStore,
    *,
    account_alias: str | None = None,
    benchmark_code: str | None = None,
    limits: RiskLimits | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Return concentration and market-risk metrics for the latest snapshot."""

    snapshot = store.get_latest_account_snapshot(
        account_alias=account_alias, include_positions=True
    )
    if snapshot is None:
        return {
            "available": False,
            "reason": "尚未导入账户快照，请先在账本中录入同花顺截图",
            "positions": [],
            "warnings": [],
        }
    positions = list(snapshot.get("positions") or [])
    return _analyze_snapshot(
        store,
        snapshot,
        positions,
        benchmark_code=benchmark_code,
        limits=limits or RiskLimits(),
        today=today or date.today(),
    )


def _analyze_snapshot(
    store: PersonalStore,
    snapshot: Mapping[str, Any],
    positions: Sequence[AccountPositionSnapshot],
    *,
    benchmark_code: str | None,
    limits: RiskLimits,
    today: date,
) -> dict[str, Any]:
    warnings: list[str] = []
    as_of = date.fromisoformat(str(snapshot["as_of"]))
    age_days = max(0, (today - as_of).days)
    if age_days > 7:
        warnings.append(f"账户快照已 {age_days} 天未更新，请重新截图")

    priced: list[dict[str, Any]] = []
    unpriced: list[str] = []
    total_position_value = 0.0
    for position in positions:
        if position.quantity <= 0:
            continue
        value = position.market_value
        if value is None and position.market_price is not None:
            value = position.quantity * position.market_price
        if value is None or value <= 0:
            unpriced.append(position.code)
            continue
        total_position_value += float(value)
        priced.append(
            {
                "code": normalize_code(position.code),
                "name": position.name,
                "quantity": float(position.quantity),
                "available_quantity": position.available_quantity,
                "avg_cost": position.avg_cost,
                "market_price": position.market_price,
                "market_value": float(value),
                "pnl": position.pnl,
                "asset_type": "etf" if is_etf_code(position.code) else "stock",
            }
        )
    if unpriced:
        warnings.append("以下持仓缺少市值/现价，未计入集中度：" + ", ".join(unpriced))

    cash = _number(snapshot.get("cash"))
    equity = _number(snapshot.get("equity"))
    market_value = _number(snapshot.get("market_value"))
    if cash is None:
        warnings.append("截图未提供现金，现金比例未计算；请补充现金后再评估仓位")
    if equity is None or equity <= 0:
        if cash is not None:
            equity = cash + total_position_value
            warnings.append("总资产由现金 + 持仓市值计算得到")
        else:
            equity = total_position_value
            warnings.append("缺少总资产/现金，权重暂按持仓市值计算")
    if equity <= 0:
        return {
            "available": False,
            "reason": "账户快照总资产无效",
            "snapshot_id": snapshot["id"],
            "as_of": as_of.isoformat(),
            "positions": [],
            "warnings": warnings,
        }

    invested = total_position_value
    if market_value is not None and market_value > 0:
        # Prefer the account's own market value for coverage/asset allocation;
        # position rows are still the source for per-name weights.
        invested = min(total_position_value, market_value) if len(unpriced) == 0 else total_position_value
    invested_pct = invested / equity * 100.0
    cash_value = cash if cash is not None else max(0.0, equity - invested)
    cash_pct = cash_value / equity * 100.0 if cash is not None else None

    for item in priced:
        item["weight_pct"] = round(item["market_value"] / equity * 100.0, 2)

    priced.sort(key=lambda item: item["market_value"], reverse=True)
    weights = sorted(
        (item["weight_pct"] for item in priced), reverse=True
    )
    top1 = weights[0] if weights else 0.0
    top5 = sum(weights[:5])
    hhi = sum((weight / 100.0) ** 2 for weight in weights)
    etf_value = sum(item["market_value"] for item in priced if item["asset_type"] == "etf")

    if top1 > limits.max_single_pct:
        warnings.append(f"单票集中度 {top1:.1f}% 超过上限 {limits.max_single_pct:.1f}%")
    if top5 > limits.max_top5_pct:
        warnings.append(f"Top5 集中度 {top5:.1f}% 超过上限 {limits.max_top5_pct:.1f}%")
    if cash_pct is not None and cash_pct < limits.min_cash_pct:
        warnings.append(f"现金比例 {cash_pct:.1f}% 低于下限 {limits.min_cash_pct:.1f}%")

    history = _load_history(
        store,
        priced,
        as_of=as_of,
        equity=equity,
        benchmark_code=benchmark_code,
    )
    _attach_market_risk(priced, history, limits, warnings)

    covered_value = sum(
        item["market_value"]
        for item in priced
        if item.get("volatility_pct") is not None
    )
    coverage_pct = covered_value / invested * 100.0 if invested > 0 else 0.0
    if priced and coverage_pct < 80:
        warnings.append(
            f"本地行情仅覆盖 {coverage_pct:.0f}% 持仓市值；Beta/波动率不代表完整组合"
        )

    return {
        "available": True,
        "snapshot_id": snapshot["id"],
        "as_of": as_of.isoformat(),
        "age_days": age_days,
        "stale": age_days > 7,
        "account_alias": snapshot.get("account_alias") or "",
        "equity": round(equity, 2),
        "cash": round(cash_value, 2),
        "cash_pct": _round(cash_pct),
        "invested": round(invested, 2),
        "invested_pct": _round(invested_pct),
        "position_count": len([item for item in priced if item["market_value"] > 0]),
        "top1_pct": _round(top1),
        "top5_pct": _round(top5),
        "hhi": _round(hhi * 10_000.0),
        "etf_pct": _round(etf_value / equity * 100.0),
        "stock_pct": _round((invested - etf_value) / equity * 100.0),
        "market_data_coverage_pct": _round(coverage_pct),
        "beta": history.get("portfolio_beta"),
        "volatility_pct": history.get("portfolio_volatility_pct"),
        "correlations": history.get("correlations", []),
        "limits": {
            "max_single_pct": limits.max_single_pct,
            "max_top5_pct": limits.max_top5_pct,
            "min_cash_pct": limits.min_cash_pct,
            "max_liquidation_days": limits.max_liquidation_days,
            "max_correlation": limits.max_correlation,
            "default_budget_pct": limits.default_budget_pct,
        },
        "positions": [_compact_position(item) for item in priced],
        "warnings": warnings,
    }


def _load_history(
    store: PersonalStore,
    positions: Sequence[dict[str, Any]],
    *,
    as_of: date,
    equity: float,
    benchmark_code: str | None,
) -> dict[str, Any]:
    start = as_of - timedelta(days=LOOKBACK_DAYS)
    benchmark_returns: pd.Series | None = None
    if benchmark_code:
        try:
            benchmark_bars = store.get_bars(
                normalize_code(benchmark_code), start, as_of
            )
            benchmark_returns = _return_series(benchmark_bars)
        except ValueError:
            benchmark_returns = None

    series_by_code: dict[str, pd.Series] = {}
    bars_by_code: dict[str, Sequence[DailyBar]] = {}
    for item in positions:
        code = item["code"]
        try:
            bars = store.get_bars(code, start, as_of)
            if not bars:
                continue
            factors = store.get_adjust_factors(code)
            adjusted = adjust_bars(bars, factors, mode="hfq")
            returns = _return_series(adjusted)
            if len(returns) >= MIN_HISTORY_BARS - 1:
                series_by_code[code] = returns
                bars_by_code[code] = adjusted
        except (ValueError, RuntimeError):
            continue

    if not series_by_code:
        return {"correlations": []}

    frame = pd.DataFrame(series_by_code).sort_index()
    if benchmark_returns is not None and len(benchmark_returns) >= MIN_HISTORY_BARS - 1:
        frame = frame.join(
            benchmark_returns.rename("__benchmark__"), how="inner"
        )
    for code in series_by_code:
        item = next(entry for entry in positions if entry["code"] == code)
        stock = frame[code]
        if benchmark_returns is not None and "__benchmark__" in frame:
            bench = frame["__benchmark__"]
            variance = float(bench.var(ddof=0))
            beta = (
                float(stock.cov(bench, ddof=0)) / variance if variance > 0 else None
            )
            item["beta"] = _round(beta)
        item["volatility_pct"] = _round(
            float(stock.std(ddof=0) * math.sqrt(TRADING_DAYS) * 100.0)
        )
        bars = bars_by_code[code]
        average_amount = sum(bar.amount for bar in bars[-LIQUIDITY_BARS:]) / min(
            LIQUIDITY_BARS, len(bars)
        )
        item["liquidation_days"] = (
            _round(item["market_value"] / average_amount)
            if average_amount > 0
            else None
        )

    portfolio_beta = None
    covered = [item for item in positions if item["code"] in series_by_code]
    if benchmark_returns is not None:
        covered_value = sum(item["market_value"] for item in covered if item.get("beta") is not None)
        if covered_value > 0:
            portfolio_beta = sum(
                item["market_value"] * item["beta"]
                for item in covered
                if item.get("beta") is not None
            ) / covered_value

    portfolio_volatility = None
    if len(series_by_code) >= 1:
        codes = list(series_by_code)
        aligned = frame[codes].dropna()
        if len(aligned) >= MIN_HISTORY_BARS - 1:
            cov = aligned.cov(ddof=0) * TRADING_DAYS
            values = {item["code"]: item["market_value"] for item in positions}
            # Keep weights relative to total equity (cash has zero volatility).
            # The reported coverage tells the user how much of the portfolio
            # this partial-volatility number actually represents.
            weights = pd.Series(
                {code: values.get(code, 0.0) / equity for code in codes},
                dtype=float,
            )
            if float(weights.sum()) > 0:
                variance = float(weights @ cov @ weights)
                portfolio_volatility = (
                    math.sqrt(max(variance, 0.0)) * 100.0
                    if variance > 0
                    else None
                )

    correlations = _top_correlations(frame, positions)
    return {
        "portfolio_beta": _round(portfolio_beta),
        "portfolio_volatility_pct": _round(portfolio_volatility),
        "correlations": correlations,
    }


def _attach_market_risk(
    positions: Sequence[dict[str, Any]],
    history: Mapping[str, Any],
    limits: RiskLimits,
    warnings: list[str],
) -> None:
    for item in positions:
        liquidation_days = item.get("liquidation_days")
        if (
            liquidation_days is not None
            and liquidation_days > limits.max_liquidation_days
        ):
            warnings.append(
                f"{item['code']} 预计 {liquidation_days:.1f} 天才能退出，流动性不足"
            )
    for pair in history.get("correlations", []):
        if abs(pair["correlation"]) >= limits.max_correlation:
            warnings.append(
                f"{pair['code_a']} / {pair['code_b']} 相关性 {pair['correlation']:.2f} 偏高"
            )


def _top_correlations(
    frame: pd.DataFrame, positions: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    codes = [item["code"] for item in positions if item["code"] in frame.columns]
    if len(codes) < 2:
        return []
    corr = frame[codes].corr()
    pairs: list[dict[str, Any]] = []
    for index, code_a in enumerate(codes):
        for code_b in codes[index + 1 :]:
            value = corr.loc[code_a, code_b]
            if pd.isna(value):
                continue
            pairs.append(
                {
                    "code_a": code_a,
                    "code_b": code_b,
                    "correlation": round(float(value), 3),
                }
            )
    pairs.sort(key=lambda item: abs(item["correlation"]), reverse=True)
    return pairs[:5]


def _return_series(bars: Sequence[DailyBar]) -> pd.Series:
    series = pd.Series(
        {bar.trade_date: bar.close for bar in bars}, dtype=float
    ).sort_index()
    return series.pct_change(fill_method=None).dropna()


def _compact_position(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "code",
            "name",
            "quantity",
            "available_quantity",
            "avg_cost",
            "market_price",
            "market_value",
            "pnl",
            "asset_type",
            "weight_pct",
            "beta",
            "volatility_pct",
            "liquidation_days",
        )
    }


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


__all__ = ["RiskLimits", "analyze_portfolio_risk"]
