from datetime import date

import pytest

from personal.backtest.portfolio import Portfolio


def test_buy_and_sell_fifo():
    portfolio = Portfolio(100_000)
    portfolio.buy("600519.SH", 10.0, 1000, fee=5.0, trade_date=date(2026, 1, 5))
    assert portfolio.quantity("600519.SH") == 1000
    assert portfolio.cash == pytest.approx(100_000 - 10_000 - 5.0)

    realized = portfolio.sell(
        "600519.SH", 11.0, 1000, fee=10.0, trade_date=date(2026, 1, 6)
    )
    assert realized == pytest.approx(11_000 - 10_000 - 10.0)
    assert portfolio.quantity("600519.SH") == 0
    assert portfolio.realized_pnl == pytest.approx(990.0)


def test_t_plus_one_blocks_same_day_sell():
    portfolio = Portfolio(100_000)
    portfolio.buy("600519.SH", 10.0, 1000, fee=5.0, trade_date=date(2026, 1, 5))
    assert portfolio.position("600519.SH").available(date(2026, 1, 5)) == 0
    with pytest.raises(ValueError, match="insufficient T\\+1"):
        portfolio.sell(
            "600519.SH", 10.5, 1000, fee=5.0, trade_date=date(2026, 1, 5)
        )


def test_insufficient_cash_rejected():
    portfolio = Portfolio(1000)
    with pytest.raises(ValueError, match="insufficient cash"):
        portfolio.buy("600519.SH", 10.0, 1000, fee=5.0, trade_date=date(2026, 1, 5))


def test_equity_accounting():
    portfolio = Portfolio(100_000)
    portfolio.buy("600519.SH", 10.0, 1000, fee=5.0, trade_date=date(2026, 1, 5))
    equity = portfolio.equity({"600519.SH": 12.0})
    assert equity == pytest.approx(100_000 - 10_005 + 12_000)
