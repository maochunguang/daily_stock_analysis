from datetime import date

from personal.datahub.models import AdjustFactor, DailyBar, TradingStatus
from personal.datahub.store import PersonalStore


def _bar(day: int, close: float = 10.0) -> DailyBar:
    return DailyBar(
        code="600519.SH",
        trade_date=date(2026, 1, day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        amount=close * 1000,
        source="test",
    )


def test_store_roundtrip(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        assert store.upsert_bars([_bar(5), _bar(6)]) == 2
        bars = store.get_bars("600519.SH")
        assert [bar.trade_date.day for bar in bars] == [5, 6]
        assert store.latest_bar_date("600519.SH") == date(2026, 1, 6)

        store.upsert_adjust_factors(
            [AdjustFactor("600519.SH", date(2026, 1, 6), 2.0, "split", "test")]
        )
        factors = store.get_adjust_factors("600519.SH")
        assert factors[0].factor == 2.0

        store.upsert_trading_status(
            [TradingStatus("600519.SH", date(2026, 1, 5), is_limit_up=True)]
        )
        status = store.get_trading_status("600519.SH", date(2026, 1, 5))
        assert status is not None and status.is_limit_up
    finally:
        store.close()


def test_get_bars_does_not_mix_sources(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        store.upsert_bars([_bar(5, 20.0)])
        store.upsert_bars(
            [
                DailyBar(
                    code="600519.SH",
                    trade_date=date(2026, 1, 5),
                    open=1500.0,
                    high=1500.0,
                    low=1500.0,
                    close=1500.0,
                    volume=1000,
                    amount=1_500_000,
                    source="baostock",
                )
            ]
        )
        preferred = store.get_bars(
            "600519.SH", preferred_sources=("baostock", "test")
        )
        assert len(preferred) == 1
        assert preferred[0].source == "baostock"
        assert preferred[0].close == 1500.0

        default = store.get_bars("600519.SH")
        assert len(default) == 1
        assert default[0].source in {"test", "baostock"}
    finally:
        store.close()


def test_upsert_is_idempotent(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        store.upsert_bars([_bar(5, 10.0)])
        store.upsert_bars([_bar(5, 11.0)])
        bars = store.get_bars("600519.SH")
        assert len(bars) == 1
        assert bars[0].close == 11.0
    finally:
        store.close()
