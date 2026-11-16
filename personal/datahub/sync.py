"""Data synchronization orchestration with source fallback and quality checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional, Sequence

from .models import DailyBar
from .normalize import normalize_code
from .quality import check_bars, cross_source_diff, missing_dates
from .sources.base import DailyBarSource
from .status import derive_trading_statuses
from .store import PersonalStore


@dataclass
class SyncResult:
    code: str
    source: str | None = None
    rows: int = 0
    quality_issues: int = 0
    cross_source_issues: int = 0
    missing_days: int = 0
    suspended_days: int = 0
    errors: list[str] = field(default_factory=list)


class DataSyncService:
    def __init__(
        self,
        store: PersonalStore,
        sources: Sequence[DailyBarSource],
        *,
        cross_check: bool = False,
        preferred_sources: Sequence[str] = (),
    ):
        if not sources:
            raise ValueError("at least one data source is required")
        self.store = store
        self.sources = list(sources)
        self.cross_check = cross_check
        self.preferred_sources = tuple(preferred_sources)

    def sync_daily_bars(
        self, codes: Iterable[str], start: date, end: date
    ) -> list[SyncResult]:
        results: list[SyncResult] = []
        for raw_code in codes:
            code = normalize_code(raw_code)
            result = SyncResult(code=code)
            primary: Optional[DailyBarSource] = None
            bars: list[DailyBar] = []
            for source in self.sources:
                try:
                    bars = source.fetch_daily_bars(code, start, end)
                except Exception as exc:  # noqa: BLE001 - fallback to next source
                    result.errors.append(f"{source.name}: {exc}")
                    continue
                if not bars:
                    result.errors.append(f"{source.name}: no rows")
                    continue
                primary = source
                break

            if primary is None or not bars:
                results.append(result)
                continue

            issues = check_bars(bars)
            self.store.upsert_bars(bars)
            if issues:
                self.store.record_quality_events(issues)
            result.source = primary.name
            result.rows = len(bars)
            result.quality_issues = len(issues)

            self._check_missing_days(code, bars, start, end, result)
            if self.cross_check and primary.name != "synthetic":
                self._cross_check(code, bars, primary, start, end, result)
            results.append(result)
        return results

    def sync_adjust_factors(
        self, codes: Iterable[str], start: date, end: date
    ) -> list[SyncResult]:
        results: list[SyncResult] = []
        for raw_code in codes:
            code = normalize_code(raw_code)
            result = SyncResult(code=code)
            for source in self.sources:
                fetch = getattr(source, "fetch_adjust_factors", None)
                if fetch is None:
                    continue
                try:
                    factors = fetch(code, start, end)
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"{source.name}: {exc}")
                    continue
                if not factors:
                    result.errors.append(f"{source.name}: no rows")
                    continue
                self.store.upsert_adjust_factors(factors)
                result.source = source.name
                result.rows = len(factors)
                break
            results.append(result)
        return results

    def sync_calendar(self, start: date, end: date) -> SyncResult:
        """Sync the open-day calendar; fall back to dates seen in stored bars."""

        result = SyncResult(code="CALENDAR")
        for source in self.sources:
            fetch = getattr(source, "fetch_trade_calendar", None)
            if fetch is None:
                continue
            try:
                days = fetch(start, end)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{source.name}: {exc}")
                continue
            if not days:
                result.errors.append(f"{source.name}: no rows")
                continue
            self.store.upsert_trading_calendar(days, source.name)
            result.source = source.name
            result.rows = len(days)
            return result

        derived = self.store.get_bar_dates(start, end)
        if derived:
            self.store.upsert_trading_calendar(derived, "derived")
            result.source = "derived"
            result.rows = len(derived)
            return result

        result.errors.append(
            "no calendar source available and no stored bars to derive from"
        )
        return result

    def sync_trading_status(
        self, codes: Iterable[str], start: date, end: date
    ) -> list[SyncResult]:
        """Derive suspension/ST/price-limit rows for the requested codes."""

        calendar = self.store.get_trading_dates(start, end)
        if not calendar or calendar[0] > start or calendar[-1] < end:
            self.sync_calendar(start, end)
            calendar = self.store.get_trading_dates(start, end)
        if not calendar:
            derived = self.store.get_bar_dates(start, end)
            if derived:
                self.store.upsert_trading_calendar(derived, "derived")
                calendar = derived

        results: list[SyncResult] = []
        for raw_code in codes:
            code = normalize_code(raw_code)
            result = SyncResult(code=code)
            bars = self.store.get_bars(
                code,
                start,
                end,
                preferred_sources=self.preferred_sources or None,
            )
            if not bars:
                result.errors.append(
                    "no local bars; sync daily bars before trading status"
                )
                results.append(result)
                continue

            name = self._instrument_name(code)
            factors = self.store.get_adjust_factors(code)
            statuses = derive_trading_statuses(
                code,
                bars,
                calendar,
                name=name,
                factors=factors,
            )
            self.store.upsert_trading_status(statuses)
            result.source = "derived"
            result.rows = len(statuses)
            result.suspended_days = sum(1 for item in statuses if item.is_suspended)
            results.append(result)
        return results

    def _check_missing_days(
        self,
        code: str,
        bars: Sequence[DailyBar],
        start: date,
        end: date,
        result: SyncResult,
    ) -> None:
        calendar = self.store.get_trading_dates(start, end)
        if not calendar:
            return
        # Only check inside the traded range; days before the first bar are
        # pre-listing, not data gaps.
        check_start = max(start, min(bar.trade_date for bar in bars))
        check_end = min(end, max(bar.trade_date for bar in bars))
        expected = [
            day for day in calendar if check_start <= day <= check_end
        ]
        issues = missing_dates(bars, expected, code=code)
        if issues:
            self.store.record_quality_events(issues)
        result.missing_days = len(issues)

    def _cross_check(
        self,
        code: str,
        bars: Sequence[DailyBar],
        primary: DailyBarSource,
        start: date,
        end: date,
        result: SyncResult,
    ) -> None:
        for source in self.sources:
            if source is primary:
                continue
            fetch = getattr(source, "fetch_daily_bars", None)
            if fetch is None:
                continue
            try:
                other = fetch(code, start, end)
            except Exception:  # noqa: BLE001 - cross-check is optional
                continue
            if not other:
                continue
            issues = cross_source_diff(bars, other)
            if issues:
                self.store.record_quality_events(issues)
            result.cross_source_issues = len(issues)
            return

    def _instrument_name(self, code: str) -> str:
        for source in self.sources:
            fetch = getattr(source, "fetch_instrument_name", None)
            if fetch is None:
                continue
            try:
                name = fetch(code)
            except Exception:  # noqa: BLE001 - name is best-effort
                continue
            if name:
                return str(name)
        return ""


def build_sources(settings, requested: str = "auto") -> list[DailyBarSource]:
    """Build the source chain from settings.

    Optional dependencies are imported lazily inside the adapters, so building
    the chain never requires akshare/tushare/baostock to be installed.
    """

    requested = (requested or "auto").strip().lower()
    if requested == "synthetic":
        from .sources.base import SyntheticSource

        return [SyntheticSource()]

    from .sources.akshare_source import AkshareSource
    from .sources.baostock_source import BaostockSource
    from .sources.tushare_source import TushareSource

    registry = {
        "tushare": lambda: TushareSource(settings.tushare_token),
        "baostock": BaostockSource,
        "akshare": AkshareSource,
    }
    if requested in registry:
        return [registry[requested]()]

    sources: list[DailyBarSource] = []
    for name in settings.data_source_priority:
        factory = registry.get(name)
        if factory is None:
            continue
        if name == "tushare" and not settings.tushare_token:
            continue
        sources.append(factory())
    if not sources:
        # Free fallback chain; adapters still import lazily.
        sources = [BaostockSource(), AkshareSource()]
    return sources
