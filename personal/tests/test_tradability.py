from datetime import date

from personal.datahub.models import TradingStatus
from personal.datahub.tradability import can_buy, can_sell, round_lot, t_plus_one_ok


def test_round_lot():
    assert round_lot(1234) == 1200
    assert round_lot(99) == 0
    assert round_lot(100) == 100


def test_price_limits_block_orders():
    status = TradingStatus(
        code="600519.SH",
        trade_date=date(2026, 1, 5),
        limit_up=11.0,
        limit_down=9.0,
        is_limit_up=True,
    )
    assert not can_buy(status, 11.0)
    assert can_sell(status, 10.5)

    status_down = TradingStatus(
        code="600519.SH",
        trade_date=date(2026, 1, 5),
        limit_up=11.0,
        limit_down=9.0,
        is_limit_down=True,
    )
    assert can_buy(status_down, 10.0)
    assert not can_sell(status_down, 9.0)


def test_suspension_blocks_both_sides():
    status = TradingStatus(
        code="600519.SH", trade_date=date(2026, 1, 5), is_suspended=True
    )
    assert not can_buy(status, 10.0)
    assert not can_sell(status, 10.0)


def test_t_plus_one():
    assert not t_plus_one_ok(date(2026, 1, 5), date(2026, 1, 5))
    assert t_plus_one_ok(date(2026, 1, 5), date(2026, 1, 6))
