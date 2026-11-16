"""A-share transaction cost model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostConfig:
    commission_bps: float = 2.5
    min_commission: float = 5.0
    stamp_duty_sell_bps: float = 5.0  # 0.05% on sell only
    transfer_fee_bps: float = 0.1     # 0.001% both sides
    slippage_bps: float = 5.0


class CostModel:
    def __init__(self, config: CostConfig | None = None):
        self.config = config or CostConfig()

    def fill_price(self, price: float, side: str) -> float:
        adjustment = self.config.slippage_bps / 10_000.0
        if side == "buy":
            return round(price * (1.0 + adjustment), 4)
        if side == "sell":
            return round(price * (1.0 - adjustment), 4)
        raise ValueError(f"unsupported side: {side}")

    def buy_fee(self, amount: float, *, is_etf: bool = False) -> float:
        return round(
            max(amount * self.config.commission_bps / 10_000.0, self.config.min_commission)
            + amount * self.config.transfer_fee_bps / 10_000.0,
            4,
        )

    def sell_fee(
        self, amount: float, *, is_etf: bool = False, holding_days: int = 0
    ) -> float:
        fee = max(
            amount * self.config.commission_bps / 10_000.0,
            self.config.min_commission,
        ) + amount * self.config.transfer_fee_bps / 10_000.0
        if not is_etf:
            fee += amount * self.config.stamp_duty_sell_bps / 10_000.0
        return round(fee, 4)

    @staticmethod
    def dividend_tax(gross_dividend: float, holding_days: int) -> float:
        """A-share dividend tax for individual investors."""

        if gross_dividend <= 0:
            return 0.0
        if holding_days <= 30:
            rate = 0.20
        elif holding_days <= 365:
            rate = 0.10
        else:
            rate = 0.0
        return round(gross_dividend * rate, 4)
