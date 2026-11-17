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
class MarketBreadth:
    """One day of market-wide breadth aggregates (TRIN / Arms Index).

    Volume columns are in 亿股 and amount columns in 亿元 so every source
    (imported snapshots, full-market daily pulls) stores the same unit.
    """

    trade_date: date
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    sample_count: int = 0
    up_vol_yi: float | None = None
    down_vol_yi: float | None = None
    up_amount_yi: float | None = None
    down_amount_yi: float | None = None
    adv_ratio: float | None = None
    trin: float | None = None
    trin_amount: float | None = None
    trin_pct: float | None = None
    interpretation: str = ""
    band: str = ""
    index_close: float | None = None
    index_chg_pct: float | None = None
    index_pos: float | None = None
    divergence: int = 0
    signal_tag: str = ""
    signal_detail: str = ""
    source: str = "unknown"

    def to_row(self) -> tuple:
        return (
            self.trade_date.isoformat(),
            self.up_count,
            self.down_count,
            self.flat_count,
            self.sample_count,
            self.up_vol_yi,
            self.down_vol_yi,
            self.up_amount_yi,
            self.down_amount_yi,
            self.adv_ratio,
            self.trin,
            self.trin_amount,
            self.trin_pct,
            self.interpretation,
            self.band,
            self.index_close,
            self.index_chg_pct,
            self.index_pos,
            self.divergence,
            self.signal_tag,
            self.signal_detail,
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
