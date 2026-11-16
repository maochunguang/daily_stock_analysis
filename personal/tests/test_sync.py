from datetime import date

from personal.datahub.models import AdjustFactor, DailyBar
from personal.datahub.sources.base import SourceUnavailable
from personal.datahub.store import PersonalStore
from personal.datahub.sync import DataSyncService


def _bars(code: str, day: int = 5) -> list[DailyBar]:
    return [
        DailyBar(
            code=code,
            trade_date=date(2026, 1, day),
            open=10.0,
            high=10.5,
            low=9.5,
            close=10.0,
            volume=1000,
            amount=10_000,
            source="fake",
        )
    ]


class _FakeSource:
    def __init__(self, name: str, bars=None, error: Exception | None = None):
        self.name = name
        self._bars = bars or []
        self._error = error

    def fetch_daily_bars(self, code, start, end):
        if self._error:
            raise self._error
        return self._bars


class _FakeAdjustSource:
    name = "fake_adjust"

    def fetch_adjust_factors(self, code, start, end):
        return [
            AdjustFactor("600519.SH", date(2026, 1, 1), 1.0, source=self.name),
            AdjustFactor("600519.SH", date(2026, 1, 15), 2.0, source=self.name),
        ]


def test_sync_falls_back_to_next_source(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        service = DataSyncService(
            store,
            [
                _FakeSource("broken", error=SourceUnavailable("no token")),
                _FakeSource("working", bars=_bars("600519.SH")),
            ],
        )
        results = service.sync_daily_bars(["600519"], date(2026, 1, 1), date(2026, 1, 31))
        assert len(results) == 1
        assert results[0].source == "working"
        assert results[0].rows == 1
        assert any("broken" in error for error in results[0].errors)
        assert len(store.get_bars("600519.SH")) == 1
    finally:
        store.close()


def test_sync_records_quality_issues(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        duplicate = _bars("600519.SH") * 2
        service = DataSyncService(store, [_FakeSource("fake", bars=duplicate)])
        results = service.sync_daily_bars(["600519"], date(2026, 1, 1), date(2026, 1, 31))
        assert results[0].quality_issues >= 1
        assert store.list_quality_events()
    finally:
        store.close()


def test_sync_adjust_factors(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        service = DataSyncService(
            store,
            [
                _FakeSource("no_adjust_support", bars=[]),
                _FakeAdjustSource(),
            ],
        )
        results = service.sync_adjust_factors(
            ["600519"], date(2026, 1, 1), date(2026, 1, 31)
        )
        assert results[0].source == "fake_adjust"
        assert results[0].rows == 2
        assert len(store.get_adjust_factors("600519.SH")) == 2
    finally:
        store.close()


def test_sync_all_sources_fail(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        service = DataSyncService(
            store,
            [
                _FakeSource("a", error=RuntimeError("boom")),
                _FakeSource("b", bars=[]),
            ],
        )
        results = service.sync_daily_bars(["600519"], date(2026, 1, 1), date(2026, 1, 31))
        assert results[0].rows == 0
        assert results[0].source is None
        assert len(results[0].errors) == 2
    finally:
        store.close()
