import io
import json
from datetime import date
from unittest.mock import patch

import pytest

from personal.datahub.composite import MIN_SAMPLES, composite_score, percentile_rank
from personal.datahub.models import (
    BondYield,
    EtfShare,
    FuturesRank,
    LimitUpStats,
    MarketTurnover,
    OptionPcr,
    RestrictedRelease,
    SectorAmount,
)
from personal.datahub.sources.cffex_source import CffexRankSource
from personal.datahub.sources.option_source import OptionPcrSource
from personal.datahub.store import PersonalStore


CFFEX_CSV = (
    "交易日,合约,排名,成交量排名,,,持买单量排名,,,持卖单量排名,,\n"
    ",,,会员简称,成交量,比上一交易日增减,会员简称,持买单量,比上一交易日增减,会员简称,持卖单量,比上一交易日增减\n"
    "20261117,IF2611,1,会员A,1000,-10,会员A,100,1,会员A,300,-5\n"
    "20261117,IF2611,2,会员B,900,-10,会员B,80,1,会员B,260,-5\n"
    "20261117,IF2612,1,会员A,800,-10,会员A,120,1,会员A,280,-5\n"
    "20261117,IF2612,2,会员B,700,-10,会员B,100,1,会员B,240,-5\n"
)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestCffexRankSource:
    def test_parses_csv_and_aggregates(self):
        source = CffexRankSource()
        with patch(
            "personal.datahub.sources.cffex_source.urllib.request.urlopen",
            return_value=_FakeResponse(CFFEX_CSV.encode("gbk")),
        ):
            summary = source._fetch_symbol("IF", date(2026, 11, 17))
        assert summary is not None
        assert summary.symbol == "IF"
        assert summary.contracts == 2
        # 持买单量 col7: 100+80+120+100 = 400
        assert summary.top20_buy == 400
        # 持卖单量 col10: 300+260+280+240 = 1080
        assert summary.top20_sell == 1080
        assert summary.net == 680
        assert summary.net_ratio == round(680 / (400 + 1080), 4)


class TestOptionPcrAggregation:
    def test_aggregate_by_underlying_and_type(self):
        source = OptionPcrSource.__new__(OptionPcrSource)
        contracts = [
            {"ts_code": "100001.SH", "name": "50ETF购12月3000", "call_put": "C"},
            {"ts_code": "100002.SH", "name": "50ETF沽12月3000", "call_put": "P"},
            {"ts_code": "100003.SH", "name": "300ETF购12月4000", "call_put": "C"},
            {"ts_code": "100004.SH", "name": "科创板50沽3月1200", "call_put": "P"},
        ]
        fields = ["ts_code", "trade_date", "exchange", "pre_settle", "pre_close",
                  "open", "high", "low", "close", "settle", "vol", "amount", "oi"]
        items = [
            ["100001.SH", "20261117", "SSE", 0, 0, 0, 0, 0, 0, 0, 500, 0, 2000],
            ["100002.SH", "20261117", "SSE", 0, 0, 0, 0, 0, 0, 0, 800, 0, 3000],
            ["100003.SH", "20261117", "SSE", 0, 0, 0, 0, 0, 0, 0, 300, 0, 1000],
            ["100004.SH", "20261117", "SSE", 0, 0, 0, 0, 0, 0, 0, 100, 0, 500],
        ]
        agg = source._aggregate(items, {c["ts_code"]: c for c in contracts})
        assert agg["50ETF"]["call_vol"] == 500
        assert agg["50ETF"]["put_vol"] == 800
        assert agg["50ETF"]["call_oi"] == 2000
        assert agg["300ETF"]["call_vol"] == 300
        assert "科创板50" not in agg  # 只聚合 PCR_UNDERLYINGS


class TestStoreRoundtrips:
    def test_indicator_tables(self, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            assert store.upsert_market_turnover(
                [MarketTurnover(trade_date=date(2026, 11, 17), sse_amount=6.76e11, szse_amount=7.68e11)]
            ) == 1
            assert store.upsert_limit_up_stats(
                [LimitUpStats(trade_date=date(2026, 11, 17), zt_count=37, first_board=20,
                              max_streak=7, zb_count=20, zb_rate=0.351,
                              prev_zt_mean=-1.2, prev_zt_up_ratio=31.2)]
            ) == 1
            assert store.upsert_option_pcr(
                [OptionPcr(trade_date=date(2026, 11, 17), underlying="50ETF",
                           call_vol=500, put_vol=800, pcr_vol=1.6,
                           call_oi=2000, put_oi=3000, pcr_oi=1.5)]
            ) == 1
            assert store.upsert_futures_rank(
                [FuturesRank(trade_date=date(2026, 11, 17), symbol="IF", contracts=4,
                             top20_buy=400, top20_sell=1080, net=680, net_ratio=0.4595)]
            ) == 1
            assert store.upsert_sector_amount(
                [SectorAmount(trade_date=date(2026, 11, 17), board="半导体",
                              amount_yi=235.7, share_pct=3.2, pct_chg=0.3)]
            ) == 1
            assert store.upsert_etf_share(
                [EtfShare(trade_date=date(2026, 11, 17), code="510300",
                          name="沪深300", share_yi=200.5)]
            ) == 1
            assert store.upsert_bond_yield(
                [BondYield(trade_date=date(2026, 11, 17), cn_2y=1.23, cn_10y=1.61,
                           us_2y=3.8, us_10y=4.1, spread_2y=-2.57, spread_10y=-2.49)]
            ) == 1
            assert store.upsert_restricted_release(
                [RestrictedRelease(release_date=date(2026, 11, 18), company_count=10,
                                   shares=912304102.0, market_value_yi=171.8)]
            ) == 1
            stats = store.stats()
            for table in ("market_turnover", "limit_up_stats", "option_pcr",
                          "futures_rank", "sector_amount", "etf_share",
                          "bond_yield", "restricted_summary"):
                assert stats[table] == 1, table
            assert len(store.get_option_pcr(underlying="300ETF")) == 0
            assert store.get_limit_up_stats(limit=1)[0].max_streak == 7
            assert store.get_restricted_release()[0].company_count == 10
        finally:
            store.close()


class TestComposite:
    def test_percentile_math(self):
        values = [1.0] * 30 + [2.0] * 70
        assert percentile_rank(values, 1.5) == 30.0
        assert percentile_rank([5, 5, 5], 5) == 0.0

    def test_composite_skips_sparse_metrics(self, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            # 样本不足 20 的指标应被跳过
            store.upsert_limit_up_stats(
                [LimitUpStats(trade_date=date(2026, 11, day), zt_count=30, zb_rate=0.3)
                 for day in range(1, 6)]
            )
            result = composite_score(store, end=date(2026, 11, 5))
            assert result.score is None
            assert result.state == "数据不足"
            assert all(c.percentile is None for c in result.components)
        finally:
            store.close()

    def test_composite_scores_direction(self, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            # 两融占比 30 天: 前 24 天 8%, 后 6 天 12% → 当前分位 = 80
            turnover = [
                MarketTurnover(trade_date=date(2026, 10, day), sse_amount=1e12, szse_amount=1e12)
                for day in range(1, 32)
            ]
            store.upsert_market_turnover(turnover)
            margin_rows = []
            for day in range(1, 25):
                margin_rows.append(_margin("总计", date(2026, 10, day), 0.08 * 2e12))
            for day in range(25, 31):
                margin_rows.append(_margin("总计", date(2026, 10, day), 0.12 * 2e12))
            store.upsert_margin_balance(margin_rows)
            result = composite_score(store, end=date(2026, 10, 31))
            component = {c.metric: c for c in result.components}["margin_buy_ratio"]
            assert component.percentile == 80.0
            assert result.score is not None  # 其他分量缺失时只用可用分量
        finally:
            store.close()

    def test_min_samples_constant(self):
        assert MIN_SAMPLES == 20


def _margin(scope, day, rzye_buy):
    from personal.datahub.models import MarginBalance

    return MarginBalance(
        trade_date=day, scope_type="market", scope=scope,
        rzye=1e12, rzrqye=1e12, rzye_buy=rzye_buy, source="fake",
    )
