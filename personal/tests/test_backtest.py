from datetime import date

import pytest

from personal.backtest.costs import CostConfig
from personal.backtest.engine import run_backtest
from personal.backtest.types import BacktestConfig, Signal
from personal.datahub.models import DailyBar, TradingStatus


def _bar(day: int, open_price: float, close: float, code: str = "600519.SH") -> DailyBar:
    return DailyBar(
        code=code,
        trade_date=date(2026, 1, day),
        open=open_price,
        high=max(open_price, close),
        low=min(open_price, close),
        close=close,
        volume=10_000,
        amount=close * 10_000,
        source="test",
    )


def _config() -> BacktestConfig:
    return BacktestConfig(
        start=date(2026, 1, 5),
        end=date(2026, 1, 8),
        initial_cash=100_000,
        max_positions=2,
        max_position_pct=0.5,
        cost=CostConfig(
            commission_bps=0,
            min_commission=0,
            stamp_duty_sell_bps=0,
            transfer_fee_bps=0,
            slippage_bps=0,
        ),
    )


def test_signal_replay_buys_next_open_and_sells_next_open():
    bars = {
        "600519.SH": [
            _bar(5, 9.0, 9.5),
            _bar(6, 10.0, 10.5),
            _bar(7, 11.0, 11.5),
            _bar(8, 12.0, 12.5),
        ]
    }
    signals = [
        Signal(date(2026, 1, 5), "600519.SH", "buy", reason="entry"),
        Signal(date(2026, 1, 6), "600519.SH", "sell", reason="exit"),
    ]
    result = run_backtest(bars, signals, _config())

    assert len(result.trades) == 2
    buy, sell = result.trades
    assert buy.side == "buy" and buy.trade_date == date(2026, 1, 6)
    assert buy.price == 10.0
    assert buy.quantity == 5000
    assert sell.side == "sell" and sell.trade_date == date(2026, 1, 7)
    assert result.metrics["total_return"] == pytest.approx(0.05)
    assert result.final_cash == pytest.approx(105_000)
    assert result.final_positions == {}


def test_limit_up_blocks_buy():
    bars = {
        "600519.SH": [
            _bar(5, 9.0, 9.5),
            _bar(6, 10.0, 10.5),
            _bar(7, 11.0, 11.5),
        ]
    }
    signals = [Signal(date(2026, 1, 5), "600519.SH", "buy")]
    status = {
        "600519.SH": {
            date(2026, 1, 6): TradingStatus(
                code="600519.SH",
                trade_date=date(2026, 1, 6),
                limit_up=10.0,
                is_limit_up=True,
            )
        }
    }
    result = run_backtest(bars, signals, _config(), status_by_code=status)
    assert result.trades == []
    assert result.final_cash == pytest.approx(100_000)


def test_benchmark_curve_is_normalized():
    bars = {
        "600519.SH": [_bar(5, 9.0, 9.5), _bar(6, 10.0, 10.5)],
    }
    benchmark = [
        _bar(5, 100.0, 100.0, code="000300.SH"),
        _bar(6, 105.0, 105.0, code="000300.SH"),
    ]
    result = run_backtest(
        bars,
        [Signal(date(2026, 1, 5), "600519.SH", "buy")],
        _config(),
        benchmark_bars=benchmark,
    )
    assert result.benchmark_curve is not None
    assert result.benchmark_curve.iloc[0] == pytest.approx(1.0)
    assert result.benchmark_curve.iloc[-1] == pytest.approx(1.05)
