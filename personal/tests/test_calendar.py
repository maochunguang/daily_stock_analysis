from datetime import date

from personal.datahub.models import AdjustFactor, DailyBar
from personal.datahub.status import derive_trading_statuses
from personal.datahub.store import PersonalStore
from personal.datahub.sync import DataSyncService


class _CalendarSource:
    name = "fake_calendar"

    def fetch_daily_bars(self, code, start, end):
        return []

    def fetch_trade_calendar(self, start, end):
        return [
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
        ]


class _NameSource:
    name = "fake_name"

    def fetch_daily_bars(self, code, start, end):
        return []

    def fetch_instrument_name(self, code):
        return "ST测试"


class _NoCalendarSource:
    name = "bars_only"

    def fetch_daily_bars(self, code, start, end):
        return []


def _bar(day: int, close: float) -> DailyBar:
    return DailyBar(
        code="600519.SH",
        trade_date=date(2026, 1, day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        amount=close * 1000,
        source="fake",
    )


def test_store_calendar_roundtrip(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        store.upsert_trading_calendar(
            [date(2026, 1, 5), date(2026, 1, 6)], "test"
        )
        assert store.get_trading_dates(
            date(2026, 1, 1), date(2026, 1, 31)
        ) == [date(2026, 1, 5), date(2026, 1, 6)]
        assert store.stats()["trading_calendar"] == 2
    finally:
        store.close()


def test_derive_status_marks_suspension_and_price_limits():
    bars = [_bar(5, 10.0), _bar(7, 11.0)]
    statuses = derive_trading_statuses(
        "600519.SH",
        bars,
        [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)],
    )
    by_date = {item.trade_date: item for item in statuses}

    assert by_date[date(2026, 1, 5)].limit_up is None
    assert by_date[date(2026, 1, 6)].is_suspended is True
    assert by_date[date(2026, 1, 7)].limit_up == 11.0
    assert by_date[date(2026, 1, 7)].is_limit_up is True


def test_derive_status_uses_st_five_percent_limit():
    bars = [_bar(5, 10.0), _bar(6, 10.5)]
    statuses = derive_trading_statuses(
        "600519.SH",
        bars,
        [date(2026, 1, 5), date(2026, 1, 6)],
        name="ST测试",
    )
    assert statuses[-1].is_st is True
    assert statuses[-1].limit_up == 10.5
    assert statuses[-1].is_limit_up is True


def test_derive_status_adjusts_reference_close_on_ex_date():
    bars = [_bar(5, 100.0), _bar(6, 50.0)]
    factors = [AdjustFactor("600519.SH", date(2026, 1, 6), 2.0, source="test")]
    statuses = derive_trading_statuses(
        "600519.SH",
        bars,
        [date(2026, 1, 5), date(2026, 1, 6)],
        factors=factors,
    )
    # The 2-for-1 split makes 50 the new 100, so it is not a limit-down day.
    assert statuses[-1].limit_down == 45.0
    assert statuses[-1].is_limit_down is False


def test_sync_calendar_falls_back_to_bars(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        store.upsert_bars([_bar(5, 10.0), _bar(6, 10.2)])
        service = DataSyncService(store, [_NoCalendarSource()])
        result = service.sync_calendar(date(2026, 1, 1), date(2026, 1, 31))
        assert result.source == "derived"
        assert result.rows == 2
    finally:
        store.close()


def test_sync_trading_status_writes_rows(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        store.upsert_bars([_bar(5, 10.0), _bar(7, 11.0)])
        service = DataSyncService(
            store,
            [_CalendarSource(), _NameSource()],
            preferred_sources=("fake",),
        )
        service.sync_calendar(date(2026, 1, 1), date(2026, 1, 31))
        results = service.sync_trading_status(
            ["600519"], date(2026, 1, 1), date(2026, 1, 31)
        )
        assert results[0].rows == 3
        statuses = store.get_trading_statuses(
            "600519.SH", date(2026, 1, 1), date(2026, 1, 31)
        )
        assert statuses[date(2026, 1, 5)].is_st is True
        assert statuses[date(2026, 1, 6)].is_suspended is True
    finally:
        store.close()
