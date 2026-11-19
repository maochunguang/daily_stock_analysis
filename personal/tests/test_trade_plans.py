from __future__ import annotations

from datetime import date

import pytest

from personal.analytics.trade_plans import PlanValidationError, preview_trade_plan
from personal.datahub.models import AccountPositionSnapshot, AccountSnapshot, TradePlan
from personal.datahub.store import PersonalStore


def snapshot(**overrides):
    payload = {
        "id": 7,
        "equity": 1_000_000.0,
        "cash": 300_000.0,
        "available_cash": 300_000.0,
    }
    payload.update(overrides)
    return payload


def plan(**overrides):
    payload = {
        "plan_date": date(2026, 11, 19),
        "code": "600519",
        "side": "buy",
        "entry_low": 100.0,
        "entry_high": 101.0,
        "stop_loss": 95.0,
        "target_price": 115.0,
        "risk_budget_pct": 1.0,
        "max_position_pct": 20.0,
    }
    payload.update(overrides)
    return TradePlan(**payload)


class TestBuyPreview:
    def test_sizes_by_risk_and_fees(self):
        preview = preview_trade_plan(plan(), snapshot(), [])
        assert preview["side"] == "buy"
        assert preview["entry_fill"] == pytest.approx(101.0505)
        assert preview["suggested_quantity"] % 100 == 0
        assert preview["suggested_quantity"] > 0
        assert preview["planned_loss"] <= preview["risk_budget_amount"] + 0.01
        assert preview["post_trade_cash"] >= 0
        assert preview["reward_risk"] > 1

    def test_position_cap_includes_existing_holding(self):
        positions = [
            AccountPositionSnapshot(
                code="600519.SH",
                quantity=100,
                market_price=1500,
                market_value=150_000,
            )
        ]
        preview = preview_trade_plan(
            plan(
                entry_low=1500,
                entry_high=1510,
                stop_loss=1400,
                risk_budget_pct=None,
                risk_budget_amount=100_000,
                max_position_pct=20,
            ),
            snapshot(),
            positions,
        )
        # 20% of equity is 200k; existing value is 150k, so at 1510 only one
        # additional lot would exceed the cap and must be reduced to zero.
        assert preview["suggested_quantity"] == 0
        assert preview["blockers"]

    def test_cash_constraint(self):
        preview = preview_trade_plan(
            plan(
                entry_low=100,
                entry_high=100,
                stop_loss=99,
                risk_budget_pct=None,
                risk_budget_amount=1_000_000,
                max_position_pct=100,
            ),
            snapshot(equity=100_000, cash=1_000, available_cash=1_000),
            [],
        )
        assert preview["max_by_cash"] == 0
        assert preview["suggested_quantity"] == 0

    def test_invalid_stop_is_blocked(self):
        preview = preview_trade_plan(
            plan(stop_loss=110), snapshot(), []
        )
        assert any("止损价必须低于买入价" in item for item in preview["blockers"])

    def test_two_risk_budgets_rejected(self):
        with pytest.raises(PlanValidationError):
            preview_trade_plan(
                plan(risk_budget_amount=5000), snapshot(), []
            )

    def test_missing_cash_blocks_buy(self):
        preview = preview_trade_plan(
            plan(), snapshot(cash=None, available_cash=None), []
        )
        assert any("可用资金" in item for item in preview["blockers"])

    def test_etf_has_no_stamp_duty_in_exit_fee(self):
        preview = preview_trade_plan(
            plan(code="510300", entry_high=4.0, entry_low=4.0, stop_loss=3.9),
            snapshot(),
            [],
        )
        assert preview["stop_exit_fee"] > 0
        # The fee is present, and the ETF branch must not add stamp duty.
        assert preview["stop_exit_fee"] < 100


class TestSellPreview:
    def test_caps_at_available_quantity(self):
        positions = [
            AccountPositionSnapshot(
                code="600519.SH",
                quantity=1000,
                available_quantity=300,
                market_price=100,
                market_value=100_000,
            )
        ]
        preview = preview_trade_plan(
            plan(
                side="sell",
                entry_low=99,
                entry_high=100,
                stop_loss=None,
                target_price=None,
                risk_budget_pct=None,
                requested_quantity=1000,
            ),
            snapshot(),
            positions,
        )
        assert preview["suggested_quantity"] == 300
        assert preview["remaining_quantity"] == 700
        assert any("可用持仓限制" in item for item in preview["warnings"])

    def test_no_position_blocked(self):
        preview = preview_trade_plan(
            plan(
                side="sell",
                entry_low=99,
                entry_high=100,
                stop_loss=None,
                target_price=None,
                risk_budget_pct=None,
            ),
            snapshot(),
            [],
        )
        assert any("没有该代码持仓" in item for item in preview["blockers"])

    def test_sell_without_available_uses_holding_with_warning(self):
        positions = [
            AccountPositionSnapshot(
                code="600519.SH",
                quantity=100,
                available_quantity=None,
                market_price=100,
                market_value=10_000,
            )
        ]
        preview = preview_trade_plan(
            plan(
                side="sell",
                entry_low=99,
                entry_high=100,
                stop_loss=None,
                target_price=None,
                risk_budget_pct=None,
            ),
            snapshot(),
            positions,
        )
        assert preview["suggested_quantity"] == 100
        assert any("T+1" in item for item in preview["warnings"])


class TestPlanStore:
    def test_crud_and_fill_progress(self, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            snapshot_id = store.upsert_account_snapshot(
                AccountSnapshot(
                    account_alias="同花顺",
                    as_of=date(2026, 11, 19),
                    equity=1_000_000,
                )
            )
            plan_id = store.create_trade_plan(
                TradePlan(
                    plan_date=date(2026, 11, 19),
                    code="600519.SH",
                    side="buy",
                    entry_low=100,
                    entry_high=101,
                    stop_loss=95,
                    risk_budget_pct=1,
                    account_snapshot_id=snapshot_id,
                    status="active",
                )
            )
            assert store.get_trade_plan(plan_id)["fill_count"] == 0
            store.add_journal_entry(
                date(2026, 11, 19),
                "600519.SH",
                "buy",
                200,
                100.5,
                20_100,
                plan_id=plan_id,
            )
            progress = store.get_trade_plan(plan_id)
            assert progress["fill_count"] == 1
            assert progress["filled_quantity"] == 200
            assert progress["fill_vwap"] == pytest.approx(100.5)
            updated = TradePlan(
                plan_date=date(2026, 11, 20),
                code="600519.SH",
                side="buy",
                entry_low=101,
                entry_high=102,
                stop_loss=96,
                target_price=112,
                risk_budget_pct=0.8,
                account_snapshot_id=snapshot_id,
                status="active",
                thesis="updated thesis",
            )
            assert store.update_trade_plan(plan_id, updated)
            reloaded = store.get_trade_plan(plan_id)
            assert reloaded["plan_date"] == "2026-11-20"
            assert reloaded["entry_low"] == 101
            assert reloaded["thesis"] == "updated thesis"
            assert reloaded["fill_count"] == 1
            assert store.update_trade_plan_status(plan_id, "closed")
            assert store.get_trade_plan(plan_id)["status"] == "closed"
        finally:
            store.close()
