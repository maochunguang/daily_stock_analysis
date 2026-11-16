"""Contract models shared across the personal layer.

These models are the anti-corruption boundary between upstream data and personal
business logic. They must not import upstream modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


@dataclass(frozen=True)
class AnalysisRecord:
    id: int
    code: str
    name: Optional[str] = None
    report_type: Optional[str] = None
    sentiment_score: Optional[int] = None
    operation_advice: Optional[str] = None
    trend_prediction: Optional[str] = None
    analysis_summary: Optional[str] = None
    raw_result: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    ideal_buy: Optional[float] = None
    secondary_buy: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass(frozen=True)
class PortfolioAccount:
    id: int
    name: str
    market: str = "cn"
    base_currency: str = "CNY"
    is_active: bool = True
    broker: Optional[str] = None


@dataclass(frozen=True)
class PortfolioTradeRecord:
    id: int
    account_id: int
    symbol: str
    trade_date: date
    side: str
    quantity: float
    price: float
    fee: float = 0.0
    tax: float = 0.0
    currency: str = "CNY"
    note: Optional[str] = None


@dataclass(frozen=True)
class DecisionSignalRecord:
    id: int
    stock_code: str
    market: str
    action: str
    created_at: Optional[datetime] = None
    score: Optional[int] = None
    confidence: Optional[float] = None
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    horizon: Optional[str] = None
    reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
