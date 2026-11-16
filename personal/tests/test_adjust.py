from datetime import date

from personal.datahub.adjust import adjust_bars, factor_at
from personal.datahub.models import AdjustFactor, DailyBar


def _bar(day: int, close: float, open_price: float | None = None) -> DailyBar:
    open_price = open_price if open_price is not None else close
    return DailyBar(
        code="600519.SH",
        trade_date=date(2026, 1, day),
        open=open_price,
        high=max(open_price, close),
        low=min(open_price, close),
        close=close,
        volume=1000,
        amount=1000 * close,
    )


def test_factor_at_uses_latest_effective_factor():
    factors = [
        AdjustFactor("600519.SH", date(2026, 1, 2), 1.0),
        AdjustFactor("600519.SH", date(2026, 1, 3), 2.0),
    ]
    assert factor_at(factors, date(2026, 1, 1)) == 1.0
    assert factor_at(factors, date(2026, 1, 2)) == 1.0
    assert factor_at(factors, date(2026, 1, 3)) == 2.0


def test_forward_adjustment_removes_split_jump():
    bars = [_bar(1, 20.0), _bar(2, 10.0)]
    factors = [
        AdjustFactor("600519.SH", date(2026, 1, 1), 1.0),
        AdjustFactor("600519.SH", date(2026, 1, 2), 2.0),
    ]
    adjusted = adjust_bars(bars, factors, mode="qfq")
    assert [bar.close for bar in adjusted] == [10.0, 10.0]


def test_backward_adjustment_keeps_history_continuous():
    bars = [_bar(1, 20.0), _bar(2, 10.0)]
    factors = [
        AdjustFactor("600519.SH", date(2026, 1, 1), 1.0),
        AdjustFactor("600519.SH", date(2026, 1, 2), 2.0),
    ]
    adjusted = adjust_bars(bars, factors, mode="hfq")
    assert [bar.close for bar in adjusted] == [20.0, 20.0]
