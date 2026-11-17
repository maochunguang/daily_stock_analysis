"""Market-level syncs (index futures, margin balance) into the personal DB.

These datasets are market-wide aggregates, not per-code bars, so they use
their own service functions instead of ``DataSyncService``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..datahub.models import IndexFutures, MarginBalance
from ..datahub.sources.base import SourceUnavailable
from ..datahub.sources.futures_source import FuturesSource
from ..datahub.sources.margin_source import MarginSource
from ..datahub.store import PersonalStore

#: margin detail APIs are per-day; keep a sane upper bound per run
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
