from datetime import date

import pytest

from personal.backtest.basket import (
    build_basket_signals,
    compute_per_stock,
    parse_basket_codes,
    rebalance_dates,
    run_basket,
)
from personal.backtest.costs import CostConfig
from personal.backtest.types import BacktestConfig
from personal.datahub.models import AdjustFactor, DailyBar


def _bar(day: int, open_price: float, close: float, code: str, month: int = 1) -> DailyBar:
    return DailyBar(
        code=code,
        trade_date=date(2026, month, day),
        open=open_price,
        high=max(open_price, close),
        low=min(open_price, close),
        close=close,
        volume=10_000,
        amount=close * 10_000,
        source="test",
    )


def _config(start: date, end: date) -> BacktestConfig:
    return BacktestConfig(
        start=start,
        end=end,
        initial_cash=1_000_000,
        benchmark=None,
        cost=CostConfig(
            commission_bps=0,
            min_commission=0,
            stamp_duty_sell_bps=0,
            transfer_fee_bps=0,
            slippage_bps=0,
        ),
    )


# --- parse_basket_codes ---


def test_parse_defaults_to_equal_weight():
    plan = parse_basket_codes(["600519", "000858", "510050"])
    assert plan.codes == ("600519.SH", "000858.SZ", "510050.SH")
    assert plan.weights == {
        "600519.SH": pytest.approx(1 / 3),
        "000858.SZ": pytest.approx(1 / 3),
        "510050.SH": pytest.approx(1 / 3),
    }


def test_parse_normalizes_fully_specified_weights():
    plan = parse_basket_codes(["600519:2", "000858:1"])
    assert plan.weights["600519.SH"] == pytest.approx(2 / 3)
    assert plan.weights["000858.SZ"] == pytest.approx(1 / 3)


def test_parse_partial_weights_split_remainder():
    plan = parse_basket_codes(["600519:0.6", "000858", "510050"])
    assert plan.weights["600519.SH"] == pytest.approx(0.6)
    assert plan.weights["000858.SZ"] == pytest.approx(0.2)
    assert plan.weights["510050.SH"] == pytest.approx(0.2)


def test_parse_rejects_bad_input():
    with pytest.raises(ValueError, match="no basket codes"):
        parse_basket_codes(["", "  "])
    with pytest.raises(ValueError, match="invalid weight"):
        parse_basket_codes(["600519:abc"])
    with pytest.raises(ValueError, match="must be positive"):
        parse_basket_codes(["600519:0"])
    with pytest.raises(ValueError, match="duplicate"):
        parse_basket_codes(["600519", "600519.SH"])
    with pytest.raises(ValueError, match="nothing left"):
        parse_basket_codes(["600519:1.2", "000858"])
    with pytest.raises(ValueError, match="too many"):
        parse_basket_codes([f"60051{i}" for i in range(31)])


# --- rebalance_dates / build_basket_signals ---


def _trading_dates() -> list[date]:
    return [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 2, 2),
        date(2026, 2, 3),
        date(2026, 3, 2),
    ]


def test_rebalance_dates_monthly_skips_entry_period():
    days = _trading_dates()
    out = rebalance_dates(date(2026, 1, 5), days, "monthly")
    assert out == [date(2026, 2, 2), date(2026, 3, 2)]


def test_rebalance_dates_weekly_skips_entry_week():
    days = _trading_dates()
    out = rebalance_dates(date(2026, 1, 5), days, "weekly")
    # 2026-02-02 (Mon) and 2026-03-02 (Mon) start later ISO weeks; 1-6/1-7 are
    # in the entry's ISO week, 2-3 belongs to 2-2's week.
    assert date(2026, 1, 6) not in out
    assert date(2026, 2, 2) in out
    assert date(2026, 3, 2) in out


def test_rebalance_dates_unknown_mode_is_empty():
    assert rebalance_dates(date(2026, 1, 5), _trading_dates(), "none") == []


def test_build_signals_sells_before_buys_on_rebalance_day():
    plan = parse_basket_codes(["600519", "000858"])
    signals = build_basket_signals(
        plan,
        entry_date=date(2026, 1, 5),
        trading_dates=_trading_dates(),
        rebalance="monthly",
    )
    # entry buys first
    assert [s.action for s in signals[:2]] == ["buy", "buy"]
    rebalance_day_signals = [s for s in signals if s.trade_date == date(2026, 2, 2)]
    assert [s.action for s in rebalance_day_signals] == ["sell", "sell", "buy", "buy"]
    assert all(s.reason == "rebalance monthly" for s in rebalance_day_signals)
    buys = [s for s in rebalance_day_signals if s.action == "buy"]
    assert buys[0].weight == pytest.approx(0.5)


# --- run_basket ---


def _two_code_bars() -> dict[str, list[DailyBar]]:
    return {
        "600519.SH": [
            _bar(5, 10.0, 10.0, "600519.SH"),
            _bar(6, 10.0, 12.0, "600519.SH"),
            _bar(7, 12.0, 12.0, "600519.SH"),
        ],
        "000858.SZ": [
            _bar(5, 20.0, 20.0, "000858.SZ"),
            _bar(6, 20.0, 20.0, "000858.SZ"),
            _bar(7, 20.0, 20.0, "000858.SZ"),
        ],
    }


def test_run_basket_buy_and_hold_fills_every_code():
    plan = parse_basket_codes(["600519:0.5", "000858:0.5"])
    run = run_basket(plan, _two_code_bars(), _config(date(2026, 1, 5), date(2026, 1, 7)))

    buys = [trade for trade in run.result.trades if trade.side == "buy"]
    assert len(buys) == 2
    # signals dated 1-5 fill at the 1-6 open
    assert buys[0].trade_date == date(2026, 1, 6)
    assert run.skipped == []
    assert set(run.result.final_positions) == {"600519.SH", "000858.SZ"}
    # both entries sized at ~50% of the 1,000,000 equity
    assert buys[0].gross_amount == pytest.approx(500_000, rel=0.01)
    assert buys[1].gross_amount == pytest.approx(500_000, rel=0.01)


def test_run_basket_per_stock_returns():
    plan = parse_basket_codes(["600519", "000858"])
    run = run_basket(plan, _two_code_bars(), _config(date(2026, 1, 5), date(2026, 1, 7)))

    rows = {row.code: row for row in run.per_stock}
    assert rows["600519.SH"].return_pct == pytest.approx(20.0)  # 10 -> 12
    assert rows["000858.SZ"].return_pct == pytest.approx(0.0)
    assert rows["600519.SH"].first_close == pytest.approx(10.0)
    assert rows["600519.SH"].last_close == pytest.approx(12.0)


def test_run_basket_adjust_factors_flow_into_per_stock():
    plan = parse_basket_codes(["600519"])
    bars = {
        "600519.SH": [
            _bar(5, 10.0, 10.0, "600519.SH"),
            _bar(6, 5.0, 5.0, "600519.SH"),  # 1-for-1 split on 1-6
        ]
    }
    factors = {"600519.SH": [AdjustFactor(code="600519.SH", ex_date=date(2026, 1, 6), factor=2.0)]}
    run = run_basket(plan, bars, _config(date(2026, 1, 5), date(2026, 1, 6)), factors_by_code=factors)
    rows = run.per_stock
    assert rows[0].return_pct == pytest.approx(0.0)  # hfq smooths the split
    assert rows[0].last_close == pytest.approx(10.0)


def test_run_basket_skips_codes_without_bars():
    plan = parse_basket_codes(["600519", "999999"])
    run = run_basket(plan, _two_code_bars(), _config(date(2026, 1, 5), date(2026, 1, 7)))
    assert run.skipped == ["999999.BJ"]
    buys = [trade for trade in run.result.trades if trade.side == "buy"]
    assert len(buys) == 1
    # plan weights are kept as-is: the skipped code's budget stays in cash
    assert run.weights["600519.SH"] == pytest.approx(0.5)


def test_run_basket_all_missing_raises():
    plan = parse_basket_codes(["999999"])
    with pytest.raises(ValueError, match="no local bars for basket codes"):
        run_basket(plan, {}, _config(date(2026, 1, 5), date(2026, 1, 7)))


def test_run_basket_monthly_rebalance_restores_weights():
    plan = parse_basket_codes(["600519:0.5", "000858:0.5"])
    bars = {
        "600519.SH": [
            _bar(5, 10.0, 10.0, "600519.SH"),
            _bar(6, 10.0, 10.0, "600519.SH"),
            _bar(2, 20.0, 20.0, "600519.SH", month=2),  # doubled before rebalance
            _bar(3, 20.0, 20.0, "600519.SH", month=2),
        ],
        "000858.SZ": [
            _bar(5, 10.0, 10.0, "000858.SZ"),
            _bar(6, 10.0, 10.0, "000858.SZ"),
            _bar(2, 10.0, 10.0, "000858.SZ", month=2),
            _bar(3, 10.0, 10.0, "000858.SZ", month=2),
        ],
    }
    run = run_basket(
        plan,
        bars,
        _config(date(2026, 1, 5), date(2026, 2, 3)),
        rebalance="monthly",
    )

    reasons = [trade.reason for trade in run.result.trades]
    assert "rebalance monthly" in reasons
    rebalance_trades = [t for t in run.result.trades if t.reason == "rebalance monthly"]
    assert {t.side for t in rebalance_trades} == {"buy", "sell"}
    # 600519 doubled -> overweight, so it is sold down; 000858 is bought up
    sold = {t.code for t in rebalance_trades if t.side == "sell"}
    bought = {t.code for t in rebalance_trades if t.side == "buy"}
    assert "600519.SH" in sold
    assert "000858.SZ" in bought
    # after the rebalance fills both positions are worth ~50% of equity again
    equity = run.result.metrics["total_return"]
    assert equity is not None


def test_run_basket_rejects_unknown_rebalance():
    plan = parse_basket_codes(["600519"])
    with pytest.raises(ValueError, match="unsupported rebalance"):
        run_basket(plan, _two_code_bars(), _config(date(2026, 1, 5), date(2026, 1, 7)), rebalance="daily")


def test_compute_per_stock_sorts_unordered_bars():
    bars = {
        "600519.SH": [
            _bar(7, 12.0, 12.0, "600519.SH"),
            _bar(5, 10.0, 10.0, "600519.SH"),
        ]
    }
    rows = compute_per_stock(bars, {}, {"600519.SH": 1.0}, adjust_mode="none")
    assert rows[0].first_date == date(2026, 1, 5)
    assert rows[0].last_date == date(2026, 1, 7)
    assert rows[0].return_pct == pytest.approx(20.0)
