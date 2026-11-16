"""A-share tradability rules: T+1, lot size, suspension, price limits."""

from __future__ import annotations

from datetime import date
from math import floor
from typing import Optional

from .models import TradingStatus
from .normalize import is_etf_code

DEFAULT_LOT_SIZE = 100
PRICE_EPSILON = 1e-6


def round_lot(quantity: float, lot_size: int = DEFAULT_LOT_SIZE) -> float:
    """Round a buy quantity down to a whole lot."""

    if lot_size <= 1:
        return max(0.0, floor(quantity))
    return max(0.0, floor(quantity / lot_size) * lot_size)


def can_buy(status: Optional[TradingStatus], price: float) -> bool:
    if status is None:
        return True
    if status.is_suspended:
        return False
    if status.is_limit_up:
        return False
    if status.limit_up is not None and price >= status.limit_up - PRICE_EPSILON:
        return False
    return True


def can_sell(status: Optional[TradingStatus], price: float) -> bool:
    if status is None:
        return True
    if status.is_suspended:
        return False
    if status.is_limit_down:
        return False
    if status.limit_down is not None and price <= status.limit_down + PRICE_EPSILON:
        return False
    return True


def t_plus_one_ok(buy_date: date, sell_date: date) -> bool:
    """A-share stocks and most ETFs are T+1: same-day round trips are illegal."""

    return sell_date > buy_date


def lot_size_for(code: str) -> int:
    return DEFAULT_LOT_SIZE


def stamp_duty_applies(code: str) -> bool:
    return not is_etf_code(code)
