"""Market-level syncs into the personal DB.

Market-wide aggregates, not per-code bars, so they use their own service
functions instead of ``DataSyncService``. Every sync records freshness into
``sync_state`` (RM-05) via the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Sequence

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
#: A-share afternoon close; snapshot APIs before this still carry the prior close
MARKET_CLOSE = time(15, 0)


def last_completed_trade_date(
    store: PersonalStore, now: datetime | None = None
) -> date:
    """Most recent trading day whose *close* data is final at ``now``.

    Snapshot-only sources (ETF share, THS industry boards) return "latest"
    values with no date parameter. Fetched at 06:00 they still hold the
    previous session's close, so stamping ``date.today()`` shifts the series
    one day forward. Use the trading calendar when available, otherwise fall
    back to weekdays.
    """
    now = now or datetime.now()
    today = now.date()
    days = [
        day
        for day in store.get_trading_dates(
            start=today - timedelta(days=20), end=today
        )
        if day <= today
    ]
    if not days:
        day = today
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        days = [day]
    if days[-1] == today and now.time() < MARKET_CLOSE:
        days = days[:-1]
    return days[-1] if days else today


def _default_end(store: PersonalStore, end: date | None) -> date:
    """Never pull an unfinished session: cap implicit end at last close.

    Eastmoney 涨停池 ignores future dates and returns the latest pool, which
    would otherwise duplicate yesterday's data under today's date.
    """
    return end or last_completed_trade_date(store)


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
    end = _default_end(store, end)
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


def sync_index_valuation(
    store: PersonalStore,
    *,
    source=None,
) -> MarketSyncResult:
    """Refresh weekly PE history for the deep-review valuation card.

    Every index is replaced atomically after a successful fetch.  If one
    index fails, already-fetched indexes stay updated but the run is reported
    as failed so the scheduler retries and the freshness table does not hide
    a partial series.
    """

    from .sources.valuation_source import (
        INDEX_VALUATION_TARGETS,
        LeguleguValuationSource,
        keep_week_latest,
    )

    source = source or LeguleguValuationSource()
    total = 0
    dates: list[date] = []
    errors: list[str] = []
    for code, _name in INDEX_VALUATION_TARGETS:
        try:
            rows = keep_week_latest(source.fetch_index_valuation(code))
            if len(rows) < 52:
                raise SourceUnavailable(
                    f"only {len(rows)} weekly observations; refusing to replace history"
                )
            total += store.replace_index_valuations(
                code, rows, source=getattr(source, "name", "legulegu")
            )
            dates.extend(row.trade_date for row in rows)
        except Exception as exc:  # noqa: BLE001 - keep other indexes moving
            errors.append(f"{code}: {exc}")

    if not dates:
        raise SourceUnavailable(
            "no index valuation rows fetched"
            + (f" ({'; '.join(errors)})" if errors else "")
        )
    result = MarketSyncResult(
        dataset="valuation",
        start=min(dates),
        end=max(dates),
        rows=total,
        latest_date=max(dates),
        message="; ".join(errors),
    )
    if errors:
        raise SourceUnavailable(
            f"partial valuation sync ({total} rows): {'; '.join(errors)}"
        )
    return result


def sync_margin_balance(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source: MarginSource | None = None,
    stock_codes: Sequence[str] = (),
) -> MarketSyncResult:
    """Margin balance sync; with ``stock_codes`` also keeps per-stock rows.

    持仓股两融（RM-42）：代码列表通常为 自选股 ∪ 交割单持仓，与市场行共用
    同一次逐日请求。
    """
    end = _default_end(store, end)
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    if (end - start).days > MARGIN_MAX_DAYS:
        raise ValueError(
            f"margin sync range is capped at {MARGIN_MAX_DAYS} days per run "
            "(per-day exchange detail requests); narrow --start/--end"
        )
    source = source or MarginSource()
    codes = tuple(dict.fromkeys(code.strip() for code in stock_codes if code and code.strip()))
    rows, stock_rows = source.fetch_margin_all(start, end, codes)
    count = store.upsert_margin_balance(rows)
    if stock_rows:
        count += store.upsert_margin_stock(stock_rows)
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
    end = _default_end(store, end)
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
    end = _default_end(store, end)
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
    """ETF-option PCR — SSE official daily statistics (complete OI basis)."""
    end = _default_end(store, end)
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    _check_range(start, end)
    source = source or OptionPcrSource()
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
    end = _default_end(store, end)
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
    """Daily industry-turnover snapshot (crowding series accumulates from now).

    Snapshot API: before the 15:00 close it still serves the prior session, so
    the default trade_date is the last *completed* trading day.
    """
    day = trade_date or last_completed_trade_date(store)
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
    """Daily broad-ETF share snapshot (share history accumulates from now).

    Same snapshot-date rule as ``sync_sector_amount``.
    """
    day = trade_date or last_completed_trade_date(store)
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
    end = _default_end(store, end)
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
