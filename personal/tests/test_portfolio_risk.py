from __future__ import annotations

import math
from datetime import date, timedelta

from personal.analytics.portfolio_risk import RiskLimits, analyze_portfolio_risk
from personal.datahub.models import AccountPositionSnapshot, AccountSnapshot, DailyBar
from personal.datahub.store import PersonalStore


def _bars(code: str, start: date, closes: list[float]) -> list[DailyBar]:
    return [
        DailyBar(
            code=code,
            trade_date=start + timedelta(days=index),
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=10_000,
            amount=10_000_000,
            source="test",
        )
        for index, close in enumerate(closes)
    ]


def test_no_snapshot(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        report = analyze_portfolio_risk(store)
        assert report["available"] is False
        assert "账户快照" in report["reason"]
    finally:
        store.close()


def test_concentration_and_market_risk(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    today = date.today()
    start = today - timedelta(days=90)
    try:
        closes_a = [10 + math.sin(i / 3) * 0.2 for i in range(90)]
        closes_b = [20 + math.sin(i / 3 + 0.4) * 0.4 for i in range(90)]
        closes_c = [5 + math.sin(i / 2) * 0.1 for i in range(90)]
        benchmark = [3000 + math.sin(i / 3) * 20 for i in range(90)]
        store.upsert_bars(
            _bars("600519.SH", start, closes_a)
            + _bars("000001.SZ", start, closes_b)
            + _bars("510300.SH", start, closes_c)
            + _bars("000300.SH", start, benchmark)
        )
        store.upsert_account_snapshot(
            AccountSnapshot(
                account_alias="同花顺",
                as_of=today,
                cash=100_000,
                market_value=900_000,
                equity=1_000_000,
                positions=(
                    AccountPositionSnapshot(
                        code="600519.SH",
                        name="贵州茅台",
                        quantity=1000,
                        market_price=600,
                        market_value=600_000,
                    ),
                    AccountPositionSnapshot(
                        code="000001.SZ",
                        name="平安银行",
                        quantity=1000,
                        market_price=200,
                        market_value=200_000,
                    ),
                    AccountPositionSnapshot(
                        code="510300.SH",
                        name="沪深300ETF",
                        quantity=1000,
                        market_price=100,
                        market_value=100_000,
                    ),
                ),
            )
        )
        report = analyze_portfolio_risk(
            store,
            benchmark_code="000300.SH",
            limits=RiskLimits(
                max_single_pct=50,
                max_top5_pct=95,
                min_cash_pct=5,
            ),
            today=today,
        )
        assert report["available"] is True
        assert report["top1_pct"] == 60
        assert report["top5_pct"] == 90
        assert report["cash_pct"] == 10
        assert report["hhi"] > 4000
        assert report["etf_pct"] == 10
        assert report["market_data_coverage_pct"] == 100
        assert report["beta"] is not None
        assert report["volatility_pct"] is not None
        assert report["positions"][0]["liquidation_days"] is not None
        assert any("单票集中度" in item for item in report["warnings"])
    finally:
        store.close()


def test_stale_snapshot_and_missing_market_data(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        store.upsert_account_snapshot(
            AccountSnapshot(
                account_alias="同花顺",
                as_of=date(2026, 1, 1),
                cash=1000,
                market_value=9000,
                equity=10_000,
                positions=(
                    AccountPositionSnapshot(
                        code="600519.SH",
                        quantity=10,
                        market_price=900,
                        market_value=9000,
                    ),
                ),
            )
        )
        report = analyze_portfolio_risk(store, benchmark_code="000300.SH")
        assert report["stale"] is True
        assert report["market_data_coverage_pct"] == 0
        assert any("天未更新" in item for item in report["warnings"])
        assert any("本地行情" in item for item in report["warnings"])
    finally:
        store.close()
