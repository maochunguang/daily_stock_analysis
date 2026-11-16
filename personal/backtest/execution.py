"""Execution simulator with A-share constraints and costs."""

from __future__ import annotations

from typing import Optional

from ..datahub.models import DailyBar, TradingStatus
from ..datahub.normalize import is_etf_code
from ..datahub.tradability import can_buy, can_sell, round_lot
from .costs import CostModel
from .portfolio import Portfolio
from .types import Trade


class ExecutionSimulator:
    def __init__(
        self,
        cost_model: CostModel,
        *,
        lot_size: int = 100,
        exclude_st: bool = True,
        exclude_suspended: bool = True,
    ):
        self.cost_model = cost_model
        self.lot_size = lot_size
        self.exclude_st = exclude_st
        self.exclude_suspended = exclude_suspended

    def buy(
        self,
        portfolio: Portfolio,
        code: str,
        target_weight: float,
        bar: DailyBar,
        status: Optional[TradingStatus],
        equity_before: float,
        reason: str = "",
    ) -> Optional[Trade]:
        if status is not None:
            if self.exclude_st and status.is_st:
                return None
            if self.exclude_suspended and status.is_suspended:
                return None
        if not can_buy(status, bar.open):
            return None
        if portfolio.quantity(code) > 0:
            return None

        price = self.cost_model.fill_price(bar.open, "buy")
        target_value = max(0.0, equity_before * target_weight)
        quantity = round_lot(target_value / price, self.lot_size)
        if quantity <= 0:
            return None

        is_etf = is_etf_code(code)
        fee = self.cost_model.buy_fee(price * quantity, is_etf=is_etf)
        if price * quantity + fee > portfolio.cash:
            # Reduce to the largest affordable whole lot.
            affordable = round_lot(
                max(0.0, (portfolio.cash - self.cost_model.config.min_commission) / price),
                self.lot_size,
            )
            quantity = min(quantity, affordable)
            if quantity <= 0:
                return None
            fee = self.cost_model.buy_fee(price * quantity, is_etf=is_etf)

        portfolio.buy(code, price, quantity, fee, bar.trade_date)
        return Trade(
            trade_date=bar.trade_date,
            code=code,
            side="buy",
            quantity=quantity,
            price=price,
            gross_amount=price * quantity,
            fee=fee,
            realized_pnl=0.0,
            reason=reason,
        )

    def sell(
        self,
        portfolio: Portfolio,
        code: str,
        bar: DailyBar,
        status: Optional[TradingStatus],
        reason: str = "",
    ) -> Optional[Trade]:
        position = portfolio.position(code)
        if position is None:
            return None
        if status is not None:
            if self.exclude_suspended and status.is_suspended:
                return None
        if not can_sell(status, bar.open):
            return None

        available = position.available(bar.trade_date)
        if available <= 0:
            return None

        price = self.cost_model.fill_price(bar.open, "sell")
        is_etf = is_etf_code(code)
        fee = self.cost_model.sell_fee(price * available, is_etf=is_etf)
        realized = portfolio.sell(code, price, available, fee, bar.trade_date)
        return Trade(
            trade_date=bar.trade_date,
            code=code,
            side="sell",
            quantity=available,
            price=price,
            gross_amount=price * available,
            fee=fee,
            realized_pnl=realized,
            reason=reason,
        )
