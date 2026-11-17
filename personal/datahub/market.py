"""Market-level syncs into the personal DB.

Market-wide aggregates, not per-code bars, so they use their own service
functions instead of ``DataSyncService``. Every sync records freshness into
``sync_state`` (RM-05) via the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..config import get_settings
from .models import (
    BondYield,
    EtfShare,
    FuturesRank,
    IndexFutures,
    LimitUpStats,
    MarginBalance,
    MarketTurnover,
    OptionPcr,
    RestrictedRelease,
    SectorAmount,
)
from .sources.base import SourceUnavailable
from .sources.rates_source import BondSource, ReleaseSource
from .sources.cffex_source import CffexRankSource
from .sources.flows_source import EtfShareSource, SectorSource, TurnoverSource
from .sources.futures_source import FuturesSource
from .sources.margin_source import MarginSource
from .sources.option_source import OptionPcrSource
from .sources.sentiment_source import LimitUpSource
from .store import PersonalStore

#: per-day exchange APIs; keep a sane upper bound per run
MARGIN_MAX_DAYS = 120
DEFAULT_LOOKBACK_DAYS = 10


@dataclass(frozen=True)
class MarketSyncResult:
    dataset: str
    start: date
    end: date
    rows: int
    latest_date: date | None
    message: str = ""

    def as_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "start": self.start,
            "end": self.end,
            "rows": self.rows,
            "latest_date": self.latest_date,
            "message": self.message,
        }


def sync_index_futures(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source: FuturesSource | None = None,
) -> MarketSyncResult:
    end = end or date.today()
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    source = source or FuturesSource()
    try:
        rows = source.fetch_index_futures(start, end)
    except SourceUnavailable:
        raise
    count = store.upsert_index_futures(rows)
    latest = max((row.trade_date for row in rows), default=None)
    return MarketSyncResult(
        dataset="futures",
        start=start,
        end=end,
        rows=count,
        latest_date=latest,
        message="" if count else "no futures rows returned for this range",
    )


def sync_margin_balance(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source: MarginSource | None = None,
) -> MarketSyncResult:
    end = end or date.today()
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    if (end - start).days > MARGIN_MAX_DAYS:
        raise ValueError(
            f"margin sync range is capped at {MARGIN_MAX_DAYS} days per run "
            "(per-day exchange detail requests); narrow --start/--end"
        )
    source = source or MarginSource()
    rows = source.fetch_margin_balance(start, end)
    count = store.upsert_margin_balance(rows)
    latest = max((row.trade_date for row in rows), default=None)
    return MarketSyncResult(
        dataset="margin",
        start=start,
        end=end,
        rows=count,
        latest_date=latest,
        message="" if count else "no margin rows returned for this range (T+1 publishing)",
    )


def sync_turnover(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source: TurnoverSource | None = None,
) -> MarketSyncResult:
    """Exchange turnover — the margin-trading-ratio denominator.

    The SSE interface returns full history in one call; SZSE costs one request
    per day in range.
    """
    end = end or date.today()
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    _check_range(start, end)
    source = source or TurnoverSource()
    rows = source.fetch_turnover(start, end)
    count = store.upsert_market_turnover(rows)
    return _result("turnover", start, end, rows)


def sync_limit_up(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source: LimitUpSource | None = None,
) -> MarketSyncResult:
    end = end or date.today()
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    _check_range(start, end)
    source = source or LimitUpSource()
    rows = source.fetch_limit_up_stats(start, end)
    count = store.upsert_limit_up_stats(rows)
    return _result("zt", start, end, rows)


def sync_option_pcr(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source: OptionPcrSource | None = None,
) -> MarketSyncResult:
    """ETF-option PCR (volume basis). opt_daily is rate-limited to 1/min."""
    end = end or date.today()
    start = start or end - timedelta(days=3)
    _check_range(start, end)
    if source is None:
        settings = get_settings()
        source = OptionPcrSource(token=settings.tushare_token, cache_dir=settings.data_dir)
    rows = source.fetch_option_pcr(start, end)
    count = store.upsert_option_pcr(rows)
    return _result("pcr", start, end, rows)


def sync_futures_rank(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source: CffexRankSource | None = None,
) -> MarketSyncResult:
    end = end or date.today()
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    _check_range(start, end)
    source = source or CffexRankSource()
    rows = source.fetch_rank_summary(start, end)
    count = store.upsert_futures_rank(rows)
    return _result("cffex_rank", start, end, rows)


def sync_sector_amount(
    store: PersonalStore,
    *,
    trade_date: date | None = None,
    source: SectorSource | None = None,
) -> MarketSyncResult:
    """Daily industry-turnover snapshot (crowding series accumulates from now)."""
    day = trade_date or date.today()
    source = source or SectorSource()
    rows = source.fetch_sector_amounts(day)
    count = store.upsert_sector_amount(rows)
    return _result("sector", day, day, rows)


def sync_etf_share(
    store: PersonalStore,
    *,
    trade_date: date | None = None,
    source: EtfShareSource | None = None,
) -> MarketSyncResult:
    """Daily broad-ETF share snapshot (share history accumulates from now)."""
    day = trade_date or date.today()
    source = source or EtfShareSource()
    rows = source.fetch_etf_share(day)
    count = store.upsert_etf_share(rows)
    return _result("etf_share", day, day, rows)


def sync_bond_yield(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source: BondSource | None = None,
) -> MarketSyncResult:
    """CN/US yields — upstream returns full history in one call."""
    end = end or date.today()
    start = start or end - timedelta(days=3650)
    source = source or BondSource()
    rows = source.fetch_bond_yield(start, end)
    count = store.upsert_bond_yield(rows)
    return _result("bond", start, end, rows)


def sync_restricted_release(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source: ReleaseSource | None = None,
) -> MarketSyncResult:
    start = start if start is not None else date.today()
    end = end if end is not None else date.today() + timedelta(days=45)
    _check_range(start, end)
    source = source or ReleaseSource()
    rows = source.fetch_release_summary(start, end)
    count = store.upsert_restricted_release(rows)
    latest = max((row.release_date for row in rows), default=None)
    return MarketSyncResult(
        dataset="release",
        start=start,
        end=end,
        rows=count,
        latest_date=latest,
        message="" if count else "no release rows returned for this range",
    )


def _check_range(start: date, end: date) -> None:
    if (end - start).days > MARGIN_MAX_DAYS:
        raise ValueError(
            f"sync range is capped at {MARGIN_MAX_DAYS} days per run "
            "(per-day exchange requests); narrow --start/--end"
        )


def _result(dataset: str, start: date, end: date, rows) -> MarketSyncResult:
    latest = max((row.trade_date for row in rows), default=None)
    return MarketSyncResult(
        dataset=dataset,
        start=start,
        end=end,
        rows=len(rows),
        latest_date=latest,
        message="" if rows else "no rows returned for this range",
    )
