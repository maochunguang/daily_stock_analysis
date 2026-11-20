"""Market-level syncs into the personal DB.

Market-wide aggregates, not per-code bars, so they use their own service
functions instead of ``DataSyncService``. Every sync records freshness into
``sync_state`` (RM-05) via the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
#: breadth sync costs one full-market ``daily`` request per trading day
BREADTH_MAX_DAYS = 450
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


def _tushare_margin_source():
    """Tushare margin adapter for the configured token, or ``None``."""

    from ..config import get_settings
    from .sources.margin_tushare_source import TushareMarginSource

    token = get_settings().tushare_token
    if not token:
        return None
    try:
        return TushareMarginSource(token=token)
    except SourceUnavailable:
        return None


def _tushare_futures_source():
    """Tushare CFFEX adapter for the configured token, or ``None``."""

    from ..config import get_settings
    from .sources.futures_tushare_source import TushareFuturesSource

    token = get_settings().tushare_token
    if not token:
        return None
    try:
        return TushareFuturesSource(token=token)
    except SourceUnavailable:
        return None


def _tushare_release_source():
    """Tushare share_float adapter for the configured token, or ``None``."""

    from ..config import get_settings
    from .sources.release_tushare_source import TushareReleaseSource

    token = get_settings().tushare_token
    if not token:
        return None
    try:
        return TushareReleaseSource(token=token)
    except SourceUnavailable:
        return None


def sync_index_futures(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source=None,
) -> MarketSyncResult:
    """Index futures: Tushare official CFFEX data primary, AkShare fallback.

    Tushare rebuilds the main-contract series from ``fut_mapping`` +
    ``fut_daily`` with spot closes from ``index_daily``; the Sina-based
    AkShare adapter stays as the fallback (both need the optional akshare
    package except Tushare, which is stdlib-only).
    """

    end = _default_end(store, end)
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    auto = source is None
    selected = source
    if auto:
        selected = _tushare_futures_source() or FuturesSource()
    try:
        rows = selected.fetch_index_futures(start, end)
    except SourceUnavailable:
        if not auto or isinstance(selected, FuturesSource):
            raise
        rows = FuturesSource().fetch_index_futures(start, end)
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
    start: date | None = None,
) -> MarketSyncResult:
    """Refresh PE history for the deep-review valuation card.

    Prefers Tushare ``index_dailybasic`` (daily series, needs a 2000-point
    token) and falls back to the weekly Legulegu endpoint per index when the
    token is missing, lacks permission, or fails. Every index is replaced
    atomically after a successful fetch; if one index fails the others stay
    updated but the run is reported as failed so the scheduler retries and the
    freshness table does not hide a partial series.
    """

    from ..config import get_settings
    from .sources.valuation_source import (
        INDEX_VALUATION_TARGETS,
        LeguleguValuationSource,
        keep_week_latest,
    )
    from .sources.valuation_tushare_source import TushareValuationSource

    legulegu = LeguleguValuationSource()
    # An explicitly injected source is used as-is (tests/forced runs); the
    # Legulegu fallback only applies to the auto-selected primary source.
    auto = source is None
    if source is not None:
        primary = source
    else:
        token = get_settings().tushare_token
        primary = None
        if token:
            try:
                primary = TushareValuationSource(token=token, start=start)
            except SourceUnavailable:
                primary = None
    if primary is None:
        primary = legulegu

    total = 0
    dates: list[date] = []
    errors: list[str] = []
    tushare_codes: list[str] = []
    for code, _name in INDEX_VALUATION_TARGETS:
        rows = None
        used_name = ""
        primary_error: Exception | None = None
        try:
            rows = primary.fetch_index_valuation(code)
            used_name = getattr(primary, "name", "legulegu")
        except Exception as exc:  # noqa: BLE001 - try the fallback source
            primary_error = exc
        if rows is None and auto and primary is not legulegu:
            try:
                rows = legulegu.fetch_index_valuation(code)
                used_name = "legulegu"
            except Exception as exc:  # noqa: BLE001 - keep other indexes moving
                errors.append(f"{code}: {primary_error}; fallback: {exc}")
                continue
        elif rows is None:
            errors.append(f"{code}: {primary_error}")
            continue

        daily = bool(getattr(primary, "is_daily", False)) and used_name == getattr(
            primary, "name", ""
        )
        if not daily:
            rows = keep_week_latest(rows)
        floor = 200 if daily else 52
        if len(rows) < floor:
            errors.append(
                f"{code}: only {len(rows)} observations; refusing to replace history"
            )
            continue
        total += store.replace_index_valuations(code, rows, source=used_name)
        dates.extend(row.trade_date for row in rows)
        if daily:
            tushare_codes.append(code)

    # The old Legulegu weekly rows would otherwise linger unused next to the
    # daily Tushare series; drop them once the full daily sync succeeded.
    for code in tushare_codes:
        total -= store.delete_index_valuations(code=code, source="legulegu")

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


def sync_market_breadth(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source=None,
) -> MarketSyncResult:
    """TRIN / Arms Index breadth computed from full-market daily data.

    Tushare ``daily`` (one request per trading day) is the primary source so
    the deep-review TRIN card no longer depends on the external
    ``easy-daily-trading`` snapshots; the free ``import-arms`` path stays
    available as a manual fallback and previously imported rows are kept until
    a Tushare row overwrites the same date. Trading days come from the local
    calendar, so backfill the calendar first when it is stale.
    """

    from .breadth import percentile_of
    from ..config import get_settings
    from .sources.arms_source import TushareArmsSource

    end = _default_end(store, end)
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    days = store.get_trading_dates(start=start, end=end)
    if len(days) > BREADTH_MAX_DAYS:
        raise ValueError(
            f"breadth sync range is capped at {BREADTH_MAX_DAYS} trading days "
            "per run (one full-market request per day); narrow --start/--end"
        )
    if not days:
        return MarketSyncResult(
            dataset="breadth",
            start=start,
            end=end,
            rows=0,
            latest_date=None,
            message="no trading days in range (sync the calendar first)",
        )
    if source is None:
        token = get_settings().tushare_token
        if not token:
            raise SourceUnavailable(
                "breadth sync needs TUSHARE_TOKEN; the free fallback is the "
                "manual `import-arms` snapshot import"
            )
        source = TushareArmsSource(token=token)
    rows = source.fetch_market_breadth(days)
    history = [row.trin for row in store.get_market_breadth()]
    enriched = [
        replace(row, trin_pct=percentile_of(row.trin, [*history, row.trin]))
        for row in rows
    ]
    count = store.upsert_market_breadth(enriched)
    latest = max((row.trade_date for row in enriched), default=None)
    return MarketSyncResult(
        dataset="breadth",
        start=start,
        end=end,
        rows=count,
        latest_date=latest,
        message="" if count else "no breadth rows returned for this range",
    )


def sync_margin_balance(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source=None,
    stock_codes: Sequence[str] = (),
    prefer_tushare: bool = False,
) -> MarketSyncResult:
    """Margin balance sync; with ``stock_codes`` also keeps per-stock rows.

    持仓股两融（RM-42）：代码列表通常为 自选股 ∪ 交割单持仓。The exchange
    scraper is primary (it also yields board splits); Tushare ``margin`` /
    ``margin_detail`` (2000-point token) takes over when the exchange scrape
    returns nothing, or when ``prefer_tushare`` is set — the latter has no
    120-day cap because per-code detail costs one request per code, which is
    how history backfills run.
    """

    end = _default_end(store, end)
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    codes = tuple(dict.fromkeys(code.strip() for code in stock_codes if code and code.strip()))
    tushare = _tushare_margin_source()
    if prefer_tushare:
        if tushare is None:
            raise SourceUnavailable("prefer_tushare requires TUSHARE_TOKEN")
        rows = tushare.fetch_margin_balance(start, end)
        stock_rows = (
            tushare.fetch_margin_stock_rows(codes, start, end) if codes else []
        )
        return _store_margin_rows(
            store, start, end, rows, _prefill_stock_names(store, stock_rows)
        )
    if (end - start).days > MARGIN_MAX_DAYS:
        raise ValueError(
            f"margin sync range is capped at {MARGIN_MAX_DAYS} days per run "
            "(per-day exchange detail requests); narrow --start/--end or use "
            "--via-tushare"
        )
    exchange = source or MarginSource()
    rows, stock_rows = exchange.fetch_margin_all(start, end, codes)
    if not rows and source is None and tushare is not None:
        rows = tushare.fetch_margin_balance(start, end)
        stock_rows = (
            tushare.fetch_margin_stock_rows(codes, start, end) if codes else []
        )
    return _store_margin_rows(
        store, start, end, rows, _prefill_stock_names(store, stock_rows)
    )


def _prefill_stock_names(store: PersonalStore, stock_rows: Sequence) -> Sequence:
    """Fill blank Tushare-detail names from the codes already in the store."""

    if not stock_rows:
        return stock_rows
    names = store.margin_stock_names()
    if not names:
        return stock_rows
    return [
        row
        if (row.name or "").strip()
        else replace(
            row, name=names.get(row.code) or row.name, source=row.source
        )
        for row in stock_rows
    ]


def _store_margin_rows(
    store: PersonalStore,
    start: date,
    end: date,
    rows: Sequence,
    stock_rows: Sequence,
) -> MarketSyncResult:
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


def _tushare_turnover_source():
    """Tushare turnover adapter for the configured token, or ``None``."""

    from ..config import get_settings
    from .sources.turnover_tushare_source import TushareTurnoverSource

    token = get_settings().tushare_token
    if not token:
        return None
    try:
        return TushareTurnoverSource(token=token)
    except SourceUnavailable:
        return None


def sync_turnover(
    store: PersonalStore,
    *,
    start: date | None = None,
    end: date | None = None,
    source: TurnoverSource | None = None,
    prefer_tushare: bool = False,
) -> MarketSyncResult:
    """Exchange turnover — the margin-trading-ratio denominator.

    The SSE interface returns full history in one call; SZSE costs one request
    per day in range. Tushare `index_daily` amounts (上证指数 + 深证综指 ≈ 全部
    沪深 A 股, ~0.1% deviation) backfill long ranges cheaply via
    ``prefer_tushare`` and act as the fallback when the exchange scrape
    returns nothing.
    """
    end = _default_end(store, end)
    start = start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    tushare = _tushare_turnover_source()
    if prefer_tushare:
        if tushare is None:
            raise SourceUnavailable("prefer_tushare requires TUSHARE_TOKEN")
        rows = tushare.fetch_turnover(start, end)
    else:
        _check_range(start, end)
        exchange = source or TurnoverSource()
        try:
            rows = exchange.fetch_turnover(start, end)
        except Exception:  # noqa: BLE001 - try the fallback source
            if tushare is None:
                raise
            rows = []
        if not rows and source is None and tushare is not None:
            rows = tushare.fetch_turnover(start, end)
    store.upsert_market_turnover(rows)
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
    source=None,
) -> MarketSyncResult:
    """Release calendar: Eastmoney primary (official MV), Tushare fallback.

    The Tushare ``share_float`` fallback aggregates per float-date and
    estimates market value from latest closes; it never produces a partial
    market-value estimate (missing price → None for that day).
    """

    start = start if start is not None else date.today()
    end = end if end is not None else date.today() + timedelta(days=45)
    _check_range(start, end)
    auto = source is None
    selected = source or ReleaseSource()
    tushare = _tushare_release_source() if auto else None
    rows = None
    selected_error: Exception | None = None
    try:
        rows = selected.fetch_release_summary(start, end)
    except Exception as exc:  # noqa: BLE001 - try the fallback source
        if tushare is None:
            raise
        rows = None
        selected_error = exc
    if not rows and tushare is not None:
        try:
            rows = tushare.fetch_release_summary(start, end)
        except Exception as exc:  # noqa: BLE001 - report the first failure
            raise SourceUnavailable(
                f"release sync failed: eastmoney={selected_error!r}; "
                f"tushare={exc}"
            ) from exc
    if rows is None:
        rows = []
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
