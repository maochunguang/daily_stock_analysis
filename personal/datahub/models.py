"""Canonical data models for the personal data hub."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DailyBar:
    code: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    source: str = "unknown"
    quality: str = "ok"

    def to_row(self) -> tuple:
        return (
            self.code,
            self.trade_date.isoformat(),
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
            self.amount,
            self.source,
            self.quality,
        )


@dataclass(frozen=True)
class AdjustFactor:
    code: str
    ex_date: date
    factor: float
    reason: str = ""
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.code,
            self.ex_date.isoformat(),
            self.factor,
            self.reason,
            self.source,
        )


@dataclass(frozen=True)
class TradingStatus:
    code: str
    trade_date: date
    is_suspended: bool = False
    is_st: bool = False
    limit_up: float | None = None
    limit_down: float | None = None
    is_limit_up: bool = False
    is_limit_down: bool = False
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.code,
            self.trade_date.isoformat(),
            int(self.is_suspended),
            int(self.is_st),
            self.limit_up,
            self.limit_down,
            int(self.is_limit_up),
            int(self.is_limit_down),
            self.source,
        )


@dataclass(frozen=True)
class FundNav:
    code: str
    nav_date: date
    nav: float | None = None
    acc_nav: float | None = None
    adj_nav: float | None = None
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.code,
            self.nav_date.isoformat(),
            self.nav,
            self.acc_nav,
            self.adj_nav,
            self.source,
        )


@dataclass(frozen=True)
class EtfSnapshot:
    code: str
    trade_date: date
    iopv: float | None = None
    close: float | None = None
    premium_pct: float | None = None
    volume: float | None = None
    amount: float | None = None
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.code,
            self.trade_date.isoformat(),
            self.iopv,
            self.close,
            self.premium_pct,
            self.volume,
            self.amount,
            self.source,
        )


@dataclass(frozen=True)
class QualityIssue:
    dataset: str
    rule: str
    severity: str
    code: str | None = None
    trade_date: date | None = None
    detail: str = ""
