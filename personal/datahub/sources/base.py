"""Data source protocol and a deterministic synthetic source for demo/tests."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol, Sequence

from ..models import DailyBar
from ..normalize import normalize_code


class SourceUnavailable(RuntimeError):
    """Raised when a source dependency or credential is missing."""


class DailyBarSource(Protocol):
    name: str

    def fetch_daily_bars(
        self, code: str, start: date, end: date
    ) -> list[DailyBar]: ...


@dataclass
class SyntheticSource:
    """Deterministic random-walk source used by tests and the demo command."""

    name: str = "synthetic"
    seed: int = 7
    start_price: float = 20.0

    def fetch_daily_bars(
        self, code: str, start: date, end: date
    ) -> list[DailyBar]:
        rng = random.Random(f"{self.seed}:{code}")
        price = self.start_price
        bars: list[DailyBar] = []
        current = start
        index = 0
        while current <= end:
            # Skip weekends to keep the demo calendar realistic.
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue
            drift = 0.0006
            shock = rng.gauss(0, 0.018)
            price = max(1.0, price * math.exp(drift + shock))
            open_price = price * (1 + rng.gauss(0, 0.004))
            close = price
            high = max(open_price, close) * (1 + abs(rng.gauss(0, 0.006)))
            low = min(open_price, close) * (1 - abs(rng.gauss(0, 0.006)))
            volume = 1_000_000 * (1 + abs(rng.gauss(0, 0.3)))
            bars.append(
                DailyBar(
                    code=normalize_code(code),
                    trade_date=current,
                    open=round(open_price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=round(volume, 0),
                    amount=round(volume * close, 2),
                    source=self.name,
                )
            )
            current += timedelta(days=1)
            index += 1
        return bars


def weekday_dates(start: date, end: date) -> list[date]:
    dates: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates
