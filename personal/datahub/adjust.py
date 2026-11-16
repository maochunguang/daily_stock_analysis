"""Adjustment factors and forward/backward adjusted price series.

Convention: ``AdjustFactor.factor`` is the cumulative share multiplier (the same
convention as Tushare's ``adj_factor``). A 10-for-10 split changes the factor
from 1.0 to 2.0.

- Forward adjusted (qfq): ``raw * factor_at(date) / factor_latest``
- Backward adjusted (hfq): ``raw * factor_at(date) / factor_first``
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Iterable, Sequence

from .models import AdjustFactor, DailyBar


def factor_at(factors: Sequence[AdjustFactor], on_date: date) -> float:
    """Return the cumulative factor effective on ``on_date``."""

    current = 1.0
    for factor in sorted(factors, key=lambda item: item.ex_date):
        if factor.ex_date <= on_date:
            current = factor.factor
        else:
            break
    return current


def adjust_bars(
    bars: Sequence[DailyBar],
    factors: Iterable[AdjustFactor],
    mode: str = "qfq",
) -> list[DailyBar]:
    """Return price-adjusted bars.

    Volume is left unchanged: it is still the traded volume for that day. Use a
    separate volume-adjustment step if a strategy needs share-equivalent volume.
    """

    if mode not in {"qfq", "hfq", "none"}:
        raise ValueError(f"unsupported adjustment mode: {mode}")
    ordered = sorted(bars, key=lambda bar: bar.trade_date)
    if not ordered or mode == "none":
        return list(ordered)

    factor_list = sorted(factors, key=lambda item: item.ex_date)
    if not factor_list:
        return list(ordered)

    if mode == "qfq":
        base = factor_at(factor_list, ordered[-1].trade_date)
    else:
        base = factor_at(factor_list, ordered[0].trade_date)
    if base == 0:
        raise ValueError("adjustment factor must be non-zero")

    adjusted: list[DailyBar] = []
    for bar in ordered:
        ratio = factor_at(factor_list, bar.trade_date) / base
        adjusted.append(
            replace(
                bar,
                open=round(bar.open * ratio, 4),
                high=round(bar.high * ratio, 4),
                low=round(bar.low * ratio, 4),
                close=round(bar.close * ratio, 4),
            )
        )
    return adjusted
