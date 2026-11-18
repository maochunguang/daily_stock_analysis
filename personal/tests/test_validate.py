from datetime import date, datetime, timedelta

import pytest

from personal.datahub.market import last_completed_trade_date
from personal.datahub.models import (
    MarginBalance,
    MarketTurnover,
    OptionPcr,
    SectorAmount,
)
from personal.datahub.sources.flows_source import EtfShareSource
from personal.datahub.store import PersonalStore
from personal.datahub.validate import (
    DATASETS,
    _online_futures,
    validate_store,
)


def _weekdays(start: date, end: date) -> list[date]:
    days = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


@pytest.fixture()
def store(tmp_path):
    db = PersonalStore(tmp_path / "personal.db")
    days = _weekdays(date(2026, 9, 1), date(2026, 12, 31))
    db.upsert_trading_calendar(days)
    try:
        yield db
    finally:
        db.close()


NOW = datetime(2026, 11, 18, 6, 0)
DAYS = _weekdays(date(2026, 10, 1), date(2026, 11, 17))


def _fill_turnover(store):
    store.upsert_market_turnover(
        [
            MarketTurnover(
                trade_date=day, sse_amount=5e11, szse_amount=5e11
            )
            for day in DAYS
        ]
    )


def _margin(scope_type, scope, day, rzye, rzye_buy=None):
    return MarginBalance(
        trade_date=day,
        scope_type=scope_type,
        scope=scope,
        rzye=rzye,
        rqye=1e10,
        rzrqye=rzye + 1e10,
        rzye_buy=rzye_buy if rzye_buy is not None else rzye * 0.06,
        source="fake",
    )


class TestValidateStore:
    def test_clean_turnover_is_ok(self, store):
        _fill_turnover(store)
        report = validate_store(
            store, days=60, datasets=["turnover"], now=NOW
        )
        assert report.datasets[0].status == "ok"
        assert report.score == 100
        assert report.status == "ok"

    def test_turnover_zero_amount_error(self, store):
        store.upsert_market_turnover(
            [
                MarketTurnover(
                    trade_date=DAYS[-1], sse_amount=0.0, szse_amount=0.0
                )
            ]
        )
        report = validate_store(
            store, days=60, datasets=["turnover"], now=NOW
        )
        rules = {item.rule for item in report.findings}
        assert "zero_amount" in rules
        assert report.datasets[0].status == "error"

    def test_margin_identity_and_buy_guard(self, store):
        day = DAYS[-1]
        store.upsert_margin_balance(
            [
                _margin("market", "沪市", day, 6e11),
                _margin("market", "深市", day, 5e11),
                _margin("market", "总计", day, 1.2e11),  # 不等于 沪+深
                _margin("board", "沪主板", day, 4e11),
                _margin("board", "科创板", day, 1e11),
                _margin("board", "深主板", day, 3.5e11),
                _margin("board", "创业板", day, 1.5e11),
            ]
        )
        report = validate_store(
            store, days=60, datasets=["margin"], now=NOW
        )
        rules = {item.rule for item in report.findings}
        assert "identity_market_total" in rules

    def test_pcr_recompute_error(self, store):
        store.upsert_option_pcr(
            [
                OptionPcr(
                    trade_date=DAYS[-1],
                    underlying="50ETF",
                    call_vol=1000,
                    put_vol=900,
                    pcr_vol=1.5,  # 应为 0.9
                    call_oi=2000,
                    put_oi=1800,
                    pcr_oi=0.9,
                )
            ]
        )
        report = validate_store(store, days=60, datasets=["pcr"], now=NOW)
        assert "pcr_recompute" in {item.rule for item in report.findings}

    def test_etf_share_unit_regression(self, store):
        # 历史 bug：把「份」直接写进 share_yi（应为亿份）
        from personal.datahub.models import EtfShare

        store.upsert_etf_share(
            [EtfShare(trade_date=DAYS[-1], code="510050", share_yi=16396866816.0)]
        )
        report = validate_store(
            store, days=60, datasets=["etf_share"], now=NOW
        )
        assert "share_range" in {item.rule for item in report.findings}
        assert report.datasets[0].status == "error"

    def test_sector_turnover_cross_check(self, store):
        _fill_turnover(store)
        day = DAYS[-1]
        boards = [f"行业{i}" for i in range(30)]
        share = 100 / len(boards)
        # 行业合计 2 倍于全市场成交额 → 日期错位/重复计算的典型信号
        store.upsert_sector_amount(
            [
                SectorAmount(
                    trade_date=day,
                    board=name,
                    amount_yi=2e12 / 1e8 / len(boards),
                    share_pct=share,
                    pct_chg=0.1,
                )
                for name in boards
            ]
        )
        report = validate_store(
            store, days=60, datasets=["sector"], now=NOW
        )
        assert "amount_vs_turnover" in {item.rule for item in report.findings}
        assert report.datasets[0].status == "error"

    def test_future_dated_snapshot_warns(self, store):
        day = date(2026, 11, 18)  # 06:00 抓取时仍是上一交易日数据
        store.upsert_sector_amount(
            [
                SectorAmount(
                    trade_date=day,
                    board=f"行业{i}",
                    amount_yi=10.0,
                    share_pct=100 / 90,
                    pct_chg=0.0,
                )
                for i in range(90)
            ]
        )
        report = validate_store(store, days=60, datasets=["sector"], now=NOW)
        assert "future_dated" in {item.rule for item in report.findings}

    def test_unknown_dataset_rejected(self, store):
        with pytest.raises(ValueError):
            validate_store(store, datasets=["nope"])

    def test_dataset_registry_covers_market_tables(self):
        for name in ("turnover", "margin", "futures", "cffex_rank", "pcr",
                     "zt", "sector", "etf_share", "bond", "breadth"):
            assert name in DATASETS


class TestSnapshotDate:
    def test_before_close_uses_previous_day(self, store):
        assert last_completed_trade_date(
            store, datetime(2026, 11, 18, 6, 0)
        ) == date(2026, 11, 17)

    def test_after_close_uses_today(self, store):
        assert last_completed_trade_date(
            store, datetime(2026, 11, 18, 16, 0)
        ) == date(2026, 11, 18)

    def test_weekend_falls_back(self, store):
        assert last_completed_trade_date(
            store, datetime(2026, 11, 21, 10, 0)
        ) == date(2026, 11, 20)


class TestEtfShareUnits:
    def test_raw_shares_converted_to_yi(self):
        import pandas as pd

        class FakeAk:
            @staticmethod
            def fund_etf_spot_em():
                return pd.DataFrame(
                    [
                        {"代码": "510050", "最新份额": 16396866816},
                        {"代码": "999999", "最新份额": 123},
                    ]
                )

        source = EtfShareSource.__new__(EtfShareSource)
        source._ak = lambda: FakeAk()
        rows = source.fetch_etf_share(date(2026, 11, 17))
        assert len(rows) == 1
        assert rows[0].share_yi == 163.97


class TestOnlineChecks:
    def test_futures_close_mismatch_flagged(self, store):
        import pandas as pd

        from personal.datahub.models import IndexFutures

        day = DAYS[-1]
        store.upsert_index_futures(
            [
                IndexFutures(
                    trade_date=day,
                    symbol="IF",
                    close=3900.0,
                    open_interest=100000,
                    index_close=3920.0,
                    basis_pct=-0.51,
                    source="sina",
                )
            ]
        )

        class FakeAk:
            @staticmethod
            def get_futures_daily(start_date, end_date, market):
                return pd.DataFrame(
                    [
                        {"variety": "IF", "symbol": "IF2612", "volume": 100,
                         "close": 4000.0},
                    ]
                )

        findings = _online_futures(store, FakeAk)
        assert any(item.rule == "online_close_mismatch" for item in findings)
