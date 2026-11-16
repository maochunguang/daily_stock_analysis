"""Portfolio accounting with FIFO lots and T+1 availability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, Optional


@dataclass
class Lot:
    quantity: float
    price: float
    buy_date: date


@dataclass
class Position:
    code: str
    lots: list[Lot] = field(default_factory=list)

    @property
    def quantity(self) -> float:
        return sum(lot.quantity for lot in self.lots)

    @property
    def cost_basis(self) -> float:
        return sum(lot.quantity * lot.price for lot in self.lots)

    @property
    def average_cost(self) -> float:
        quantity = self.quantity
        return self.cost_basis / quantity if quantity else 0.0

    def available(self, sell_date: date) -> float:
        return sum(lot.quantity for lot in self.lots if lot.buy_date < sell_date)

    def add(self, quantity: float, price: float, buy_date: date) -> None:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.lots.append(Lot(quantity=quantity, price=price, buy_date=buy_date))

    def remove_fifo(self, quantity: float, sell_date: date) -> float:
        """Remove ``quantity`` from lots available on ``sell_date``.

        Returns the cost basis of the removed shares.
        """

        if quantity <= 0:
            raise ValueError("quantity must be positive")
        remaining = quantity
        cost_basis = 0.0
        kept: list[Lot] = []
        for lot in self.lots:
            if remaining <= 0:
                kept.append(lot)
                continue
            if lot.buy_date >= sell_date:
                kept.append(lot)
                continue
            take = min(lot.quantity, remaining)
            cost_basis += take * lot.price
            remaining -= take
            if lot.quantity - take > 1e-9:
                kept.append(Lot(quantity=lot.quantity - take, price=lot.price, buy_date=lot.buy_date))
        if remaining > 1e-9:
            raise ValueError(f"insufficient T+1 available shares for {self.code}")
        self.lots = kept
        return cost_basis

    def market_value(self, price: float) -> float:
        return self.quantity * price


class Portfolio:
    def __init__(self, cash: float):
        if cash < 0:
            raise ValueError("initial cash must be non-negative")
        self.cash = float(cash)
        self.positions: Dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.fees_paid = 0.0

    def position(self, code: str) -> Optional[Position]:
        return self.positions.get(code)

    def quantity(self, code: str) -> float:
        position = self.positions.get(code)
        return position.quantity if position else 0.0

    def buy(
        self,
        code: str,
        price: float,
        quantity: float,
        fee: float,
        trade_date: date,
    ) -> None:
        total = price * quantity + fee
        if total > self.cash + 1e-6:
            raise ValueError(f"insufficient cash: need {total:.2f}, have {self.cash:.2f}")
        position = self.positions.setdefault(code, Position(code=code))
        position.add(quantity, price, trade_date)
        self.cash -= total
        self.fees_paid += fee

    def sell(
        self,
        code: str,
        price: float,
        quantity: float,
        fee: float,
        trade_date: date,
    ) -> float:
        position = self.positions.get(code)
        if position is None:
            raise ValueError(f"no position for {code}")
        cost_basis = position.remove_fifo(quantity, trade_date)
        gross = price * quantity
        realized = gross - cost_basis - fee
        self.cash += gross - fee
        self.realized_pnl += realized
        self.fees_paid += fee
        if position.quantity <= 1e-9:
            del self.positions[code]
        return realized

    def equity(self, prices: Dict[str, float]) -> float:
        value = self.cash
        for code, position in self.positions.items():
            value += position.market_value(prices.get(code, position.average_cost))
        return value

    def position_quantities(self) -> Dict[str, float]:
        return {code: position.quantity for code, position in self.positions.items()}
