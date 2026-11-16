from personal.backtest.costs import CostConfig, CostModel


def test_buy_fee_uses_minimum_commission():
    model = CostModel()
    # 10,000 CNY * 2.5bp = 2.5, but minimum commission is 5.
    assert model.buy_fee(10_000) == 5.1


def test_sell_fee_includes_stamp_duty_for_stocks():
    model = CostModel()
    assert model.sell_fee(10_000) == 10.1


def test_sell_fee_excludes_stamp_duty_for_etf():
    model = CostModel()
    assert model.sell_fee(10_000, is_etf=True) == 5.1


def test_dividend_tax_by_holding_period():
    assert CostModel.dividend_tax(1000, 10) == 200.0
    assert CostModel.dividend_tax(1000, 100) == 100.0
    assert CostModel.dividend_tax(1000, 400) == 0.0


def test_slippage_price():
    model = CostModel(CostConfig(slippage_bps=10))
    assert model.fill_price(10.0, "buy") == 10.01
    assert model.fill_price(10.0, "sell") == 9.99
