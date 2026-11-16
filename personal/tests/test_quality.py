from datetime import date

from personal.datahub.models import DailyBar
from personal.datahub.quality import check_bars, cross_source_diff


def _bar(day: int, close: float, source: str = "a", volume: float = 1000) -> DailyBar:
    return DailyBar(
        code="600519.SH",
        trade_date=date(2026, 1, day),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        amount=volume * close,
        source=source,
    )


def test_detects_duplicate_and_bad_ohlc():
    bars = [
        _bar(5, 10.0),
        _bar(5, 10.0),
        DailyBar(
            code="600519.SH",
            trade_date=date(2026, 1, 6),
            open=10.0,
            high=9.0,
            low=8.0,
            close=11.0,
            volume=1000,
            amount=11000,
        ),
    ]
    issues = check_bars(bars)
    rules = {issue.rule for issue in issues}
    assert "duplicate_date" in rules
    assert "ohlc_inconsistent" in rules


def test_detects_extreme_jump():
    bars = [_bar(5, 10.0), _bar(6, 15.0)]
    issues = check_bars(bars)
    assert any(issue.rule == "extreme_jump" for issue in issues)


def test_cross_source_mismatch():
    primary = [_bar(5, 10.0, source="tushare", volume=1000)]
    secondary = [_bar(5, 10.5, source="akshare", volume=2000)]
    issues = cross_source_diff(primary, secondary)
    rules = {issue.rule for issue in issues}
    assert "close_price_mismatch" in rules
    assert "volume_mismatch" in rules
