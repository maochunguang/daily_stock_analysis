"""Data synchronization orchestration with source fallback and quality checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Sequence

from .models import AdjustFactor, DailyBar
from .normalize import normalize_code
from .quality import check_bars
from .sources.base import DailyBarSource
from .store import PersonalStore


@dataclass
class SyncResult:
    code: str
    source: str | None = None
    rows: int = 0
    quality_issues: int = 0
    errors: list[str] = field(default_factory=list)


class DataSyncService:
    def __init__(self, store: PersonalStore, sources: Sequence[DailyBarSource]):
        if not sources:
            raise ValueError("at least one data source is required")
        self.store = store
        self.sources = list(sources)

    def sync_daily_bars(
        self, codes: Iterable[str], start: date, end: date
    ) -> list[SyncResult]:
        results: list[SyncResult] = []
        for raw_code in codes:
            code = normalize_code(raw_code)
            result = SyncResult(code=code)
            for source in self.sources:
                try:
                    bars = source.fetch_daily_bars(code, start, end)
                except Exception as exc:  # noqa: BLE001 - fallback to next source
                    result.errors.append(f"{source.name}: {exc}")
                    continue
                if not bars:
                    result.errors.append(f"{source.name}: no rows")
                    continue
                issues = check_bars(bars)
                self.store.upsert_bars(bars)
                if issues:
                    self.store.record_quality_events(issues)
                result.source = source.name
                result.rows = len(bars)
                result.quality_issues = len(issues)
                break
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
