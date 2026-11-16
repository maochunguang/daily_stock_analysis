"""Backtest domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import pandas as pd

from .costs import CostConfig


@dataclass(frozen=True)
class Signal:
    """A signal generated after the close of ``trade_date``.

    Execution happens on the next trading day's open.
    """

    trade_date: date
    code: str
    action: str  # buy / sell
    weight: Optional[float] = None
    reason: str = ""


@dataclass
class Trade:
    trade_date: date
    code: str
    side: str
    quantity: float
    price: float
    gross_amount: float
    fee: float
    realized_pnl: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class BacktestConfig:
    start: date
    end: date
    initial_cash: float = 1_000_000.0
    benchmark: Optional[str] = None
    cost: CostConfig = field(default_factory=CostConfig)
    max_positions: int = 10
    max_position_pct: float = 0.10
    lot_size: int = 100
    exclude_st: bool = True
    exclude_suspended: bool = True


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    benchmark_curve: Optional[pd.Series]
    trades: list[Trade]
    metrics: dict[str, Any]
    final_cash: float
    final_positions: dict[str, float]
