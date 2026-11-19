from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from personal.analytics.journal_outcomes import (
    evaluate_journal_outcomes,
    summarize_outcomes,
)
from personal.datahub.models import AdjustFactor, DailyBar, TradePlan
from personal.datahub.store import PersonalStore


def _bars(code: str, start: date, closes: list[float], source: str = "test") -> list[DailyBar]:
    return [
        DailyBar(
            code=code,
            trade_date=start + timedelta(days=index),
            open=close - 1,
            high=close + 2,
            low=close - 5,
            close=close,
            volume=1000,
            amount=1_000_000,
            source=source,
        )
        for index, close in enumerate(closes)
    ]


def _store(tmp_path, *, benchmark: bool = True) -> PersonalStore:
    store = PersonalStore(tmp_path / "personal.db")
    start = date(2026, 1, 1)
    store.upsert_bars(_bars("600519.SH", start, [100 + i for i in range(20)]))
    if benchmark:
        store.upsert_bars(
            _bars("000300.SH", start, [100 + i * 0.5 for i in range(20)])
        )
    return store


def test_d_plus_n_selects_future_security_bars(tmp_path):
    store = _store(tmp_path)
    try:
        journal_id = store.add_journal_entry(
            date(2026, 1, 2), "600519.SH", "buy", 100, 100, 10000
        )
        payload = evaluate_journal_outcomes(
            store,
            horizon=5,
            days=365,
            benchmark_code="000300.SH",
            today=date(2026, 1, 30),
        )
        row = payload["rows"][0]
        assert row["journal_id"] == journal_id
        assert row["status"] == "completed"
        assert row["target_date"] == "2026-01-07"  # 5 bars after Jan 2
        assert row["end_close"] == pytest.approx(106.0)
        assert row["asset_return"] == pytest.approx(0.06)
        assert row["mae"] < 0
        assert row["mfe"] > 0
        assert row["benchmark_return"] is not None
        assert row["excess_return"] == pytest.approx(
            row["asset_return"] - row["benchmark_return"]
        )
        assert payload["summary"]["completed"] == 1
        assert payload["summary"]["sample_warning"] is True
    finally:
        store.close()


def test_sell_uses_aligned_direction(tmp_path):
    store = _store(tmp_path)
    try:
        store.add_journal_entry(
            date(2026, 1, 2), "600519.SH", "sell", 100, 100, 10000
        )
        payload = evaluate_journal_outcomes(
            store,
            horizon=5,
            days=365,
            benchmark_code=None,
            today=date(2026, 1, 30),
        )
        row = payload["rows"][0]
        assert row["asset_return"] == pytest.approx(0.06)
        assert row["aligned_return"] == pytest.approx(-0.06)
        assert row["mae"] < 0  # price rose after selling: exit was too early
        assert row["mfe"] > 0  # intraday lows still offered a better exit
        assert payload["summary"]["win_rate"] == 0
    finally:
        store.close()


def test_pending_and_unavailable_rows(tmp_path):
    store = _store(tmp_path, benchmark=False)
    try:
        store.add_journal_entry(
            date(2026, 1, 18), "600519.SH", "buy", 100, 100, 10000
        )
        store.add_journal_entry(
            date(2026, 1, 19), "999999.SH", "buy", 100, 10, 1000
        )
        store.add_journal_entry(
            date(2026, 1, 19), "600519.SH", "buy", 100, 0, 0
        )
        payload = evaluate_journal_outcomes(
            store,
            horizon=20,
            days=365,
            benchmark_code=None,
            today=date(2026, 1, 30),
        )
        statuses = {row["status"] for row in payload["rows"]}
        assert statuses == {"pending", "unavailable"}
        assert payload["summary"]["completed"] == 0
        assert payload["summary"]["pending"] >= 1
        assert payload["summary"]["unavailable"] >= 2
        assert any(
            "交易日不足" in (row["unable_reason"] or "")
            for row in payload["rows"]
            if row["status"] == "pending"
        )
    finally:
        store.close()


def test_split_is_adjusted_for_entry_and_bars(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        start = date(2026, 1, 1)
        bars = [
            DailyBar("600519.SH", start, 100, 100, 100, 100, 1, 1, "test"),
            DailyBar("600519.SH", start + timedelta(days=1), 110, 110, 110, 110, 1, 1, "test"),
            DailyBar("600519.SH", start + timedelta(days=2), 55, 55, 55, 55, 1, 1, "test"),
            DailyBar("600519.SH", start + timedelta(days=3), 56, 56, 56, 56, 1, 1, "test"),
        ]
        store.upsert_bars(bars)
        store.upsert_adjust_factors(
            [AdjustFactor("600519.SH", start + timedelta(days=2), 2.0, "split", "test")]
        )
        store.add_journal_entry(
            start + timedelta(days=1), "600519.SH", "buy", 100, 110, 11000
        )
        payload = evaluate_journal_outcomes(
            store,
            horizon=1,
            days=365,
            benchmark_code=None,
            adjust_mode="hfq",
            today=date(2026, 1, 30),
        )
        row = payload["rows"][0]
        # Jan 3 raw 55 becomes 110 after the 2x split: the entry at 110 is unchanged.
        assert row["status"] == "completed"
        assert row["end_close"] == pytest.approx(110.0)
        assert row["asset_return"] == pytest.approx(0.0)
    finally:
        store.close()


def test_plan_link_and_market_state_context(tmp_path):
    store = _store(tmp_path)
    try:
        snapshot = json.dumps(
            {"composite": {"state": "偏冷", "score": 32.0}, "breadth": {"trin": 0.5}}
        )
        plan_id = store.create_trade_plan(
            TradePlan(
                plan_date=date(2026, 1, 2),
                code="600519.SH",
                side="buy",
                entry_low=99,
                entry_high=102,
                stop_loss=95,
                target_price=110,
                risk_budget_pct=1,
                requested_quantity=100,
                status="active",
            )
        )
        store.add_journal_entry(
            date(2026, 1, 2),
            "600519.SH",
            "buy",
            100,
            100,
            10000,
            plan_id=plan_id,
            snapshot=snapshot,
        )
        payload = evaluate_journal_outcomes(
            store, horizon=5, days=365, benchmark_code=None, today=date(2026, 1, 30)
        )
        row = payload["rows"][0]
        assert row["plan_id"] == plan_id
        assert row["entry_in_plan_range"] is True
        assert row["plan_quantity_ratio"] == pytest.approx(1.0)
        assert row["composite_state"] == "偏冷"
        assert payload["summary"]["plan_linked"] == 1
        assert payload["summary"]["plan_entry_in_range_rate"] == 1.0
        assert "偏冷" in payload["summary"]["by_market_state"]
    finally:
        store.close()


def test_summary_uses_completed_only_and_wilson():
    rows = [
        {"status": "completed", "aligned_return": 0.1, "mae": -0.02, "mfe": 0.15, "side": "buy", "composite_state": "中性"},
        {"status": "completed", "aligned_return": -0.05, "mae": -0.1, "mfe": 0.01, "side": "sell", "composite_state": "中性"},
        {"status": "pending", "aligned_return": None, "mae": None, "mfe": None, "side": "buy"},
        {"status": "unavailable", "aligned_return": None, "mae": None, "mfe": None, "side": "buy"},
    ]
    summary = summarize_outcomes(rows, horizon=20)
    assert summary["completed"] == 2
    assert summary["pending"] == 1
    assert summary["unavailable"] == 1
    assert summary["win_rate"] == 0.5
    assert summary["win_rate_ci"][0] < 0.5 < summary["win_rate_ci"][1]
    assert summary["sample_warning"] is True
