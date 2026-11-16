"""Performance and trade metrics."""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

import pandas as pd

from .types import Trade

TRADING_DAYS = 244


def compute_metrics(
    equity: pd.Series,
    benchmark: Optional[pd.Series] = None,
    trades: Optional[Sequence[Trade]] = None,
    *,
    risk_free_rate: float = 0.0,
) -> dict[str, Any]:
    series = equity.dropna().astype(float)
    if len(series) < 2 or series.iloc[0] <= 0:
        return _empty_metrics()

    total_return = series.iloc[-1] / series.iloc[0] - 1.0
    days = (series.index[-1] - series.index[0]).days
    years = days / 365.25 if days > 0 else 0.0
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 and total_return > -1 else math.nan

    returns = series.pct_change(fill_method=None).dropna()
    annual_vol = float(returns.std(ddof=0) * math.sqrt(TRADING_DAYS)) if len(returns) else math.nan
    sharpe = (
        float((returns.mean() - risk_free_rate / TRADING_DAYS) * TRADING_DAYS / annual_vol)
        if annual_vol and annual_vol > 0
        else math.nan
    )

    running_max = series.cummax()
    drawdown = series / running_max - 1.0
    max_drawdown = float(drawdown.min())
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 and not math.isnan(cagr) else math.nan

    metrics: dict[str, Any] = {
        "total_return": float(total_return),
        "cagr": float(cagr),
        "annual_vol": annual_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "calmar": float(calmar) if not isinstance(calmar, float) or not math.isnan(calmar) else math.nan,
        "start": series.index[0].isoformat() if hasattr(series.index[0], "isoformat") else str(series.index[0]),
        "end": series.index[-1].isoformat() if hasattr(series.index[-1], "isoformat") else str(series.index[-1]),
        "days": int(len(series)),
    }

    if benchmark is not None and len(benchmark.dropna()) >= 2:
        bench = benchmark.dropna().astype(float)
        bench_return = bench.iloc[-1] / bench.iloc[0] - 1.0
        metrics["benchmark_return"] = float(bench_return)
        metrics["excess_return"] = float(total_return - bench_return)

    trade_metrics = _trade_metrics(trades or [], series)
    metrics.update(trade_metrics)
    return metrics


def _trade_metrics(trades: Sequence[Trade], equity: pd.Series) -> dict[str, Any]:
    sells = [trade for trade in trades if trade.side == "sell"]
    wins = [trade.realized_pnl for trade in sells if trade.realized_pnl > 0]
    losses = [trade.realized_pnl for trade in sells if trade.realized_pnl < 0]
    gross_turnover = sum(abs(trade.gross_amount) for trade in trades)
    average_equity = float(equity.mean()) if len(equity) else 0.0
    return {
        "trade_count": len(trades),
        "closed_trade_count": len(sells),
        "win_rate": float(len(wins) / len(sells)) if sells else None,
        "profit_factor": float(sum(wins) / abs(sum(losses))) if losses else None,
        "average_win": float(sum(wins) / len(wins)) if wins else None,
        "average_loss": float(sum(losses) / len(losses)) if losses else None,
        "turnover": float(gross_turnover / average_equity) if average_equity > 0 else None,
        "total_fees": float(sum(trade.fee for trade in trades)),
    }


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""

    if total <= 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _empty_metrics() -> dict[str, Any]:
    keys = (
        "total_return",
        "cagr",
        "annual_vol",
        "sharpe",
        "max_drawdown",
        "calmar",
        "trade_count",
        "closed_trade_count",
        "win_rate",
        "profit_factor",
        "turnover",
        "total_fees",
    )
    return {key: math.nan for key in keys}
