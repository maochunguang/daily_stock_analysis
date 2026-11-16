from datetime import date

import pandas as pd
import pytest

from personal.backtest.metrics import compute_metrics, wilson_interval


def _equity(values: list[float]) -> pd.Series:
    dates = [date(2026, 1, day) for day in range(1, len(values) + 1)]
    return pd.Series(values, index=pd.Index(dates, name="date"))


def test_total_return_and_drawdown():
    metrics = compute_metrics(_equity([100.0, 110.0, 121.0]))
    assert metrics["total_return"] == pytest.approx(0.21)
    assert metrics["max_drawdown"] == 0.0
    assert metrics["trade_count"] == 0


def test_drawdown_metrics():
    metrics = compute_metrics(_equity([100.0, 120.0, 90.0, 110.0]))
    assert metrics["max_drawdown"] == pytest.approx(-0.25)


def test_benchmark_excess_return():
    metrics = compute_metrics(
        _equity([100.0, 110.0]),
        benchmark=pd.Series(
            [1.0, 1.05], index=pd.Index([date(2026, 1, 1), date(2026, 1, 2)])
        ),
    )
    assert metrics["benchmark_return"] == pytest.approx(0.05)
    assert metrics["excess_return"] == pytest.approx(0.05)


def test_wilson_interval():
    low, high = wilson_interval(7, 10)
    assert 0 < low < high <= 1
    assert low < 0.7 < high
