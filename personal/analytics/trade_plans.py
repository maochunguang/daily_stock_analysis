"""Trade-plan risk sizing and what-if preview.

Pure calculation only: this module never writes to a database and never calls
QMT. The preview uses a confirmed account snapshot, so there is no hidden
account state or stale broker balance.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Mapping, Sequence

from ..backtest.costs import CostModel
from ..datahub.models import AccountPositionSnapshot, TradePlan
from ..datahub.normalize import is_etf_code, normalize_code
from ..datahub.tradability import DEFAULT_LOT_SIZE, round_lot
from .portfolio_risk import RiskLimits


class PlanValidationError(ValueError):
    """A plan is structurally invalid before risk preview."""


def preview_trade_plan(
    plan: TradePlan,
    snapshot: Mapping[str, Any],
    positions: Sequence[AccountPositionSnapshot],
    *,
    cost_model: CostModel | None = None,
    lot_size: int = DEFAULT_LOT_SIZE,
    limits: RiskLimits | None = None,
) -> dict[str, Any]:
    """Return a read-only risk preview for a trade plan."""

    limits = limits or RiskLimits()
    model = cost_model or CostModel()
    side = str(plan.side).strip().lower()
    if side not in {"buy", "sell"}:
        raise PlanValidationError("计划方向必须是 buy 或 sell")
    code = normalize_code(plan.code)
    _validate_prices(plan, side)
    if _number(snapshot.get("equity")) is None or float(snapshot["equity"]) <= 0:
        raise PlanValidationError("账户快照缺少有效总资产，无法做风险预演")
    equity = float(snapshot["equity"])
    cash = _number(snapshot.get("cash"))
    available_cash = _number(snapshot.get("available_cash"))
    usable_cash = available_cash if available_cash is not None else cash
    current = _position_map(positions)
    same = current.get(code)
    max_position_pct = (
        plan.max_position_pct
        if plan.max_position_pct is not None
        else limits.max_single_pct
    )
    warnings: list[str] = []
    blockers: list[str] = []

    if side == "buy":
        entry_price = plan.entry_high
        stop_price = plan.stop_loss
        if stop_price is None or stop_price <= 0:
            blockers.append("买入计划需要有效止损价")
            stop_price = 0.0
        elif stop_price >= entry_price:
            blockers.append("止损价必须低于买入价")
        budget = _risk_budget(plan, equity)
        if budget is None or budget <= 0:
            blockers.append("风险预算必须填写比例或金额（且大于 0）")
            budget = 0.0
        if usable_cash is None:
            blockers.append("账户快照缺少可用资金，无法计算可买数量")
            usable_cash = 0.0
        if max_position_pct <= 0:
            blockers.append("单票仓位上限必须大于 0")
        entry_fill = model.fill_price(entry_price, "buy")
        stop_fill = model.fill_price(stop_price, "sell") if stop_price > 0 else 0.0
        is_etf = is_etf_code(code)
        max_value = equity * max_position_pct / 100.0
        existing_value = float(same.get("market_value") or 0.0) if same else 0.0
        if existing_value >= max_value > 0:
            warnings.append("现有同代码持仓已达到或超过单票仓位上限")
        position_room = max(0.0, max_value - existing_value)
        max_by_risk = (
            round_lot(budget / max(entry_fill - stop_fill, 1e-9), lot_size)
            if budget > 0 and entry_fill > stop_fill
            else 0.0
        )
        max_by_position = round_lot(position_room / entry_fill, lot_size)
        max_by_cash = round_lot(usable_cash / entry_fill, lot_size)
        requested = (
            round_lot(plan.requested_quantity, lot_size)
            if plan.requested_quantity is not None
            else None
        )
        quantity = min(max_by_risk, max_by_position, max_by_cash)
        if requested is not None:
            quantity = min(quantity, requested)
        if quantity <= 0:
            blockers.append("按风险预算/仓位上限/可用资金计算，可买数量为 0")
        quantity = _fit_buy_quantity(
            quantity,
            entry_fill=entry_fill,
            stop_fill=stop_fill,
            budget=budget,
            usable_cash=usable_cash,
            max_value=max_value,
            is_etf=is_etf,
            cost_model=model,
            lot_size=lot_size,
        )
        if quantity <= 0:
            blockers.append("扣除费用后无法买入一个整手")
        gross = entry_fill * quantity
        entry_fee = model.buy_fee(gross, is_etf=is_etf) if quantity > 0 else 0.0
        stop_value = stop_fill * quantity
        stop_fee = (
            model.sell_fee(stop_value, is_etf=is_etf)
            if quantity > 0 and stop_value > 0
            else 0.0
        )
        planned_loss = max(0.0, gross + entry_fee - (stop_value - stop_fee))
        risk_used_pct = planned_loss / budget * 100.0 if budget > 0 else None
        if planned_loss > budget + 1e-6:
            warnings.append("计划亏损超过风险预算（费用导致），请减少数量")
        if requested is not None and quantity < requested:
            warnings.append(f"计划数量受风险/资金约束，从 {requested:g} 降至 {quantity:g}")
        if same is not None and same["quantity"] > 0:
            warnings.append("已有同代码持仓；本计划按增持后的单票集中度预演")
        post = _post_trade_weights(
            current,
            equity=equity,
            code=code,
            side="buy",
            gross=gross,
            cash=usable_cash,
            fee=entry_fee,
            sold_quantity=0.0,
        )
        reward_risk = None
        if plan.target_price is not None and entry_fill > stop_fill > 0:
            reward_risk = (plan.target_price - entry_fill) / (entry_fill - stop_fill)
        result = {
            "side": "buy",
            "code": code,
            "entry_price": entry_price,
            "entry_fill": round(entry_fill, 4),
            "stop_price": stop_price,
            "stop_fill": round(stop_fill, 4),
            "target_price": plan.target_price,
            "suggested_quantity": quantity,
            "lot_size": lot_size,
            "gross_amount": round(gross, 2),
            "entry_fee": round(entry_fee, 2),
            "stop_exit_fee": round(stop_fee, 2),
            "planned_loss": round(planned_loss, 2),
            "risk_budget_amount": round(budget, 2),
            "risk_used_pct": _round(risk_used_pct),
            "reward_risk": _round(reward_risk, 2),
            "max_by_risk": max_by_risk,
            "max_by_position": max_by_position,
            "max_by_cash": max_by_cash,
            "post_trade_cash": round(usable_cash - gross - entry_fee, 2),
            "post_trade_position_weight_pct": post["position_weight_pct"],
            "post_trade_top1_pct": post["top1_pct"],
            "post_trade_top5_pct": post["top5_pct"],
            "post_trade_cash_pct": post["cash_pct"],
            "warnings": warnings,
            "blockers": blockers,
            "assumptions": {
                "entry": "买入按区间上沿",
                "stop": "止损卖出按市价并计费用",
                "equity": "使用账户快照总资产",
            },
            "snapshot_id": snapshot.get("id"),
        }
    else:
        entry_price = plan.entry_low
        entry_fill = model.fill_price(entry_price, "sell")
        available = same.get("available_quantity") if same else None
        held = same.get("quantity") if same else 0.0
        if same is None or held <= 0:
            blockers.append("账户快照中没有该代码持仓")
            held = 0.0
            available = 0.0
        if available is None:
            available = held
            warnings.append("截图未提供可用数量，暂按全部持仓预演，请核对 T+1 可卖数量")
        requested = (
            plan.requested_quantity
            if plan.requested_quantity is not None
            else available
        )
        if requested is None or requested <= 0:
            blockers.append("卖出计划需要有效数量")
            requested = 0.0
        quantity = min(float(requested), float(available or 0.0))
        if quantity < requested:
            warnings.append(f"卖出数量受可用持仓限制，从 {requested:g} 降至 {quantity:g}")
        gross = entry_fill * quantity
        fee = model.sell_fee(gross, is_etf=is_etf_code(code)) if quantity > 0 else 0.0
        post = _post_trade_weights(
            current,
            equity=equity,
            code=code,
            side="sell",
            gross=gross,
            cash=usable_cash or 0.0,
            fee=fee,
            sold_quantity=quantity,
        )
        result = {
            "side": "sell",
            "code": code,
            "entry_price": entry_price,
            "entry_fill": round(entry_fill, 4),
            "stop_price": plan.stop_loss,
            "target_price": plan.target_price,
            "suggested_quantity": quantity,
            "lot_size": lot_size,
            "gross_amount": round(gross, 2),
            "entry_fee": round(fee, 2),
            "planned_loss": None,
            "risk_budget_amount": None,
            "risk_used_pct": None,
            "reward_risk": None,
            "post_trade_cash": (
                round((usable_cash or 0.0) + gross - fee, 2)
                if usable_cash is not None
                else None
            ),
            "post_trade_position_weight_pct": post["position_weight_pct"],
            "post_trade_top1_pct": post["top1_pct"],
            "post_trade_top5_pct": post["top5_pct"],
            "post_trade_cash_pct": post["cash_pct"],
            "remaining_quantity": max(0.0, held - quantity),
            "warnings": warnings,
            "blockers": blockers,
            "assumptions": {
                "entry": "卖出按区间下沿",
                "quantity": "不超过截图可用数量",
                "equity": "使用账户快照总资产",
            },
            "snapshot_id": snapshot.get("id"),
        }

    if post["top1_pct"] is not None and post["top1_pct"] > limits.max_single_pct:
        warnings.append(
            f"交易后单票集中度 {post['top1_pct']:.1f}% 超过上限 {limits.max_single_pct:.1f}%"
        )
    if post["top5_pct"] is not None and post["top5_pct"] > limits.max_top5_pct:
        warnings.append(
            f"交易后 Top5 集中度 {post['top5_pct']:.1f}% 超过上限 {limits.max_top5_pct:.1f}%"
        )
    if post["cash_pct"] is not None and post["cash_pct"] < limits.min_cash_pct:
        warnings.append(
            f"交易后现金 {post['cash_pct']:.1f}% 低于下限 {limits.min_cash_pct:.1f}%"
        )
    return result


def plan_to_dict(plan: TradePlan) -> dict[str, Any]:
    payload = asdict(plan)
    for key in ("plan_date", "valid_until"):
        value = payload.get(key)
        if value is not None:
            payload[key] = value.isoformat()
    return payload


def _validate_prices(plan: TradePlan, side: str) -> None:
    if plan.entry_low <= 0 or plan.entry_high <= 0:
        raise PlanValidationError("买入/卖出价格必须大于 0")
    if plan.entry_low > plan.entry_high:
        raise PlanValidationError("价格区间下限不能高于上限")
    if side == "buy":
        if plan.stop_loss is None:
            # Let preview return a structured blocker rather than a 500.
            return
        if plan.stop_loss >= plan.entry_high:
            return


def _risk_budget(plan: TradePlan, equity: float) -> float | None:
    pct = plan.risk_budget_pct
    amount = plan.risk_budget_amount
    if pct is not None and amount is not None:
        raise PlanValidationError("风险预算比例和金额只能填写一个")
    if pct is not None:
        if pct < 0:
            raise PlanValidationError("风险预算比例不能为负")
        return equity * pct / 100.0
    if amount is not None:
        if amount < 0:
            raise PlanValidationError("风险预算金额不能为负")
        return amount
    return None


def _fit_buy_quantity(
    quantity: float,
    *,
    entry_fill: float,
    stop_fill: float,
    budget: float,
    usable_cash: float,
    max_value: float,
    is_etf: bool,
    cost_model: CostModel,
    lot_size: int,
) -> float:
    """Decrease by whole lots until fee-aware loss and cash fit."""

    qty = max(0.0, quantity)
    while qty > 0:
        gross = entry_fill * qty
        entry_fee = cost_model.buy_fee(gross, is_etf=is_etf)
        stop_value = stop_fill * qty
        stop_fee = cost_model.sell_fee(stop_value, is_etf=is_etf) if stop_value > 0 else 0.0
        planned_loss = gross + entry_fee - (stop_value - stop_fee)
        if (
            planned_loss <= budget + 1e-6
            and gross + entry_fee <= usable_cash + 1e-6
            and gross <= max_value + 1e-6
        ):
            return qty
        qty -= lot_size
    return 0.0


def _position_map(
    positions: Sequence[AccountPositionSnapshot],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for position in positions:
        code = normalize_code(position.code)
        value = position.market_value
        if value is None and position.market_price is not None:
            value = position.quantity * position.market_price
        result[code] = {
            "code": code,
            "quantity": position.quantity,
            "available_quantity": position.available_quantity,
            "market_value": value or 0.0,
        }
    return result


def _post_trade_weights(
    positions: Mapping[str, Mapping[str, Any]],
    *,
    equity: float,
    code: str,
    side: str,
    gross: float,
    cash: float,
    fee: float,
    sold_quantity: float,
) -> dict[str, float | None]:
    values = {
        item_code: float(item.get("market_value") or 0.0)
        for item_code, item in positions.items()
    }
    if side == "buy":
        values[code] = values.get(code, 0.0) + gross
        post_cash = cash - gross - fee
        post_equity = max(equity - fee, 1e-9)
    else:
        current = positions.get(code)
        if current:
            quantity = float(current.get("quantity") or 0.0)
            ratio = max(0.0, (quantity - sold_quantity) / quantity) if quantity else 0.0
            values[code] = float(current.get("market_value") or 0.0) * ratio
        post_cash = cash + gross - fee
        post_equity = max(equity - fee, 1e-9)
    positive = sorted(
        (value for value in values.values() if value > 0), reverse=True
    )
    return {
        "position_weight_pct": _round(values.get(code, 0.0) / post_equity * 100.0),
        "top1_pct": _round(positive[0] / post_equity * 100.0) if positive else 0.0,
        "top5_pct": _round(sum(positive[:5]) / post_equity * 100.0),
        "cash_pct": _round(post_cash / post_equity * 100.0),
    }


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


__all__ = ["PlanValidationError", "plan_to_dict", "preview_trade_plan"]
