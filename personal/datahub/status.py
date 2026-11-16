"""Derive A-share trading status (suspension, ST, price limits) from bars.

Providers do not expose a uniform status API on the free tier, so the personal
layer derives what it can from daily bars, the trading calendar, adjustment
factors and an optional instrument name. The result is written to
``trading_status`` and consumed by the backtest engine.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Iterable, Optional, Sequence

from .adjust import factor_at
from .models import AdjustFactor, DailyBar, TradingStatus
from .normalize import is_etf_code

BSE_PREFIXES = ("4", "8", "9")
GROWTH_PREFIXES = ("300", "301", "688", "689")


def is_st_name(name: Optional[str]) -> bool:
    """Best-effort ST detection from a Chinese instrument name."""

    text = str(name or "").upper().replace(" ", "")
    return "ST" in text


def board_limit_pct(code: str, *, is_st: bool = False) -> float:
    """Daily price-limit percentage for the board."""

    body = code.split(".")[0]
    if is_etf_code(code):
        return 0.10
    if body.startswith(BSE_PREFIXES):
        return 0.30
    if body.startswith(GROWTH_PREFIXES):
        # ChiNext/STAR ST names keep the 20% limit.
        return 0.20
    return 0.05 if is_st else 0.10


def _tick_size(code: str) -> float:
    return 0.001 if is_etf_code(code) else 0.01


def _reference_close(
    prev_bar: DailyBar,
    prev_date: date,
    current_date: date,
    factors: Sequence[AdjustFactor],
) -> float:
    """Previous close adjusted for an ex-date between the two sessions."""

    reference = prev_bar.close
    if not factors:
        return reference
    factor_prev = factor_at(factors, prev_date)
    factor_now = factor_at(factors, current_date)
    if factor_prev > 0 and factor_now > 0 and factor_prev != factor_now:
        reference = reference * factor_prev / factor_now
    return reference


def derive_trading_statuses(
    code: str,
    bars: Iterable[DailyBar],
    trading_dates: Iterable[date] = (),
    *,
    name: Optional[str] = None,
    factors: Sequence[AdjustFactor] = (),
    source: str = "derived",
) -> list[TradingStatus]:
    """Build a status row for every calendar day in the bar range.

    - Days present in ``trading_dates`` but missing a bar are marked suspended.
    - Limit prices come from the previous close, board rules and ST state.
    - On ex-dates the previous close is adjusted by the factor ratio.
    """

    ordered = sorted(bars, key=lambda item: item.trade_date)
    if not ordered:
        return []

    by_date = {bar.trade_date: bar for bar in ordered}
    first_bar_date = ordered[0].trade_date
    last_bar_date = ordered[-1].trade_date
    # Only build rows inside the traded range: earlier calendar days are
    # pre-listing and later days may simply be un-downloaded data.
    dates = sorted(
        item
        for item in (set(trading_dates) | set(by_date))
        if first_bar_date <= item <= last_bar_date
    )
    if not dates:
        return []

    is_st = is_st_name(name)
    pct = board_limit_pct(code, is_st=is_st)
    tick = _tick_size(code)
    statuses: list[TradingStatus] = []
    prev_bar: Optional[DailyBar] = None
    prev_date: Optional[date] = None

    for current_date in dates:
        bar = by_date.get(current_date)
        if bar is None:
            statuses.append(
                TradingStatus(
                    code=code,
                    trade_date=current_date,
                    is_suspended=True,
                    is_st=is_st,
                    source=source,
                )
            )
            continue

        limit_up: Optional[float] = None
        limit_down: Optional[float] = None
        is_limit_up = False
        is_limit_down = False
        if prev_bar is not None and prev_date is not None:
            reference = _reference_close(prev_bar, prev_date, current_date, factors)
            limit_up = round(reference * (1.0 + pct), 3 if tick < 0.01 else 2)
            limit_down = round(reference * (1.0 - pct), 3 if tick < 0.01 else 2)
            is_limit_up = bar.close >= limit_up - 1e-6
            is_limit_down = bar.close <= limit_down + 1e-6

        statuses.append(
            TradingStatus(
                code=code,
                trade_date=current_date,
                is_suspended=False,
                is_st=is_st,
                limit_up=limit_up,
                limit_down=limit_down,
                is_limit_up=is_limit_up,
                is_limit_down=is_limit_down,
                source=source,
            )
        )
        prev_bar = bar
        prev_date = current_date

    return statuses


def scale_status_limits(status: TradingStatus, ratio: float) -> TradingStatus:
    """Scale stored (raw-price) limits into the backtest's adjusted price space."""

    if ratio == 1.0:
        return status
    return replace(
        status,
        limit_up=round(status.limit_up * ratio, 6) if status.limit_up is not None else None,
        limit_down=(
            round(status.limit_down * ratio, 6)
            if status.limit_down is not None
            else None
        ),
    )
