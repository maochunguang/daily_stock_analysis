import json
from dataclasses import replace
from datetime import date
import pytest
from unittest.mock import patch

from personal.datahub.market import (
    MARGIN_MAX_DAYS,
    MarketSyncResult,
    sync_index_futures,
    sync_margin_balance,
)
from personal.datahub.models import IndexFutures, MarginBalance, MarginStockRow
from personal.datahub.sources.margin_source import _stock_rows_sse, classify_board
from personal.datahub.store import PersonalStore


def _futures_row(day: str, symbol: str = "IF", close=4000.0, index_close=3980.0):
    return IndexFutures(
        trade_date=date.fromisoformat(day),
        symbol=symbol,
        close=close,
        volume=71500,
        open_interest=179066,
        oi_chg=-1482,
        index_close=index_close,
        basis=round(close - index_close, 4),
        basis_pct=round((close - index_close) / index_close * 100, 4),
        source="fake",
    )


class _FakeFuturesSource:
    def fetch_index_futures(self, start, end):
        return [
            _futures_row("2026-11-16"),
            _futures_row("2026-11-17", close=3918.2, index_close=3976.463),
        ]


class _FakeMarginSource:
    def fetch_margin_balance(self, start, end):
        rows, _ = self.fetch_margin_all(start, end, ())
        return rows

    def fetch_margin_all(self, start, end, stock_codes=()):
        return (
            [
                MarginBalance(
                    trade_date=date(2026, 11, 16),
                    scope_type="market",
                    scope="沪市",
                    rzye=1177935693951,
                    rqye=18743277821,
                    rzrqye=1196678971772,
                    rzye_buy=90323568835,
                    source="fake",
                ),
                MarginBalance(
                    trade_date=date(2026, 11, 16),
                    scope_type="board",
                    scope="科创板",
                    rzye=1_000_000_000_000,
                    source="fake",
                ),
            ],
            [],
        )


class TestBoardClassification:
    def test_sse_boards(self):
        assert classify_board("600519") == "沪主板"
        assert classify_board("601318") == "沪主板"
        assert classify_board("688806") == "科创板"
        assert classify_board("689009") == "科创板"

    def test_szse_boards(self):
        assert classify_board("000001") == "深主板"
        assert classify_board("002415") == "深主板"
        assert classify_board("300750") == "创业板"
        assert classify_board("301269") == "创业板"

    def test_non_stock_excluded(self):
        # ETF / 可转债 / 债券回购都不进板块行
        assert classify_board("510050") is None
        assert classify_board("113050") is None
        assert classify_board("204001") is None
        assert classify_board("") is None


def test_sse_stock_rows_fall_back_to_security_abbr():
    rows = _stock_rows_sse(
        [
            {
                "stockCode": "600519",
                "securityAbbr": "贵州茅台",
                "rzye": 14516424905,
                "rzmre": 205580374,
                "rqye": 123,
            }
        ],
        date(2026, 11, 18),
        {"600519"},
        "exchange_margin",
    )
    assert len(rows) == 1
    assert rows[0].name == "贵州茅台"


class TestMarketSync:
    def test_sync_futures_roundtrip(self, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            result = sync_index_futures(
                store,
                start=date(2026, 11, 15),
                end=date(2026, 11, 17),
                source=_FakeFuturesSource(),
            )
            assert isinstance(result, MarketSyncResult)
            assert result.rows == 2
            assert result.latest_date == date(2026, 11, 17)
            rows = store.get_index_futures()
            assert [r.symbol for r in rows] == ["IF", "IF"]
            basis_day = rows[-1]
            assert basis_day.basis == round(3918.2 - 3976.463, 4)
            assert basis_day.basis_pct < 0  # 贴水
            limited = store.get_index_futures(limit=1)
            assert [r.trade_date for r in limited] == [date(2026, 11, 17)]
            ih = store.get_index_futures(symbols=("IH",))
            assert ih == []
            assert store.stats()["index_futures"] == 2
        finally:
            store.close()

    def test_sync_margin_roundtrip(self, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            result = sync_margin_balance(
                store,
                start=date(2026, 11, 15),
                end=date(2026, 11, 17),
                source=_FakeMarginSource(),
            )
            assert result.rows == 2
            rows = store.get_margin_balance(scope_type="board")
            assert [r.scope for r in rows] == ["科创板"]
            market = store.get_margin_balance(scope_type="market")
            assert [r.scope for r in market] == ["沪市"]
            assert market[0].rzye == 1177935693951
            assert store.stats()["margin_balance"] == 2
        finally:
            store.close()

    def test_margin_range_is_capped(self, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            try:
                sync_margin_balance(
                    store,
                    start=date(2026, 1, 1),
                    end=date(2026, 12, 31),
                    source=_FakeMarginSource(),
                )
            except ValueError as exc:
                assert str(MARGIN_MAX_DAYS) in str(exc)
            else:
                raise AssertionError("expected ValueError for long margin range")
        finally:
            store.close()

    def test_api_market_sync_uses_injected_source(self, client):
        from personal.api.app import create_app  # noqa: F401  (client fixture shared)

        with patch(
            "personal.datahub.market.MarginSource", _FakeMarginSource
        ), patch(
            "personal.datahub.market.FuturesSource", _FakeFuturesSource
        ):
            futures = client.post(
                "/api/market/sync",
                json={"dataset": "futures", "start": "2026-11-15", "end": "2026-11-17"},
            )
            assert futures.status_code == 200
            assert futures.json()["dataset"] == "futures"

            margin = client.post(
                "/api/market/sync",
                json={"dataset": "margin", "start": "2026-11-15", "end": "2026-11-17"},
            )
            assert margin.status_code == 200

        listed = client.get("/api/market/futures")
        assert listed.status_code == 200
        assert listed.json()["rows"][0]["symbol"] == "IF"

        margin_rows = client.get("/api/market/margin")
        assert margin_rows.status_code == 200
        scopes = {row["scope"] for row in margin_rows.json()["rows"]}
        assert scopes == {"沪市", "科创板"}

        too_long = client.post(
            "/api/market/sync",
            json={"dataset": "margin", "start": "2026-01-01", "end": "2026-12-31"},
        )
        assert too_long.status_code == 400


# ---------------------------------------------------------------------------
# Tushare market sources (2000-point tier): margin / futures / release
# ---------------------------------------------------------------------------

def test_parse_tushare_margin_summary_filters_bse_and_sums_total():
    from personal.datahub.sources.margin_tushare_source import parse_margin_summary

    rows = [
        {"trade_date": "20261119", "exchange_id": "SSE", "rzye": 100.0, "rqye": 10.0, "rzrqye": 110.0, "rzmre": 5.0},
        {"trade_date": "20261119", "exchange_id": "SZSE", "rzye": 200.0, "rqye": 20.0, "rzrqye": 220.0, "rzmre": 6.0},
        {"trade_date": "20261119", "exchange_id": "BSE", "rzye": 999.0, "rqye": 1.0, "rzrqye": 1000.0, "rzmre": 1.0},
        {"trade_date": "bad-date", "exchange_id": "SSE", "rzye": 1.0},
    ]
    parsed = parse_margin_summary(rows)
    scopes = {(row.scope_type, row.scope): row for row in parsed}
    assert len(parsed) == 3
    assert scopes[("market", "沪市")].rzye == 100.0
    assert scopes[("market", "深市")].rzye_buy == 6.0
    total = scopes[("market", "总计")]
    assert total.rzye == 300.0 and total.rzrqye == 330.0 and total.rzye_buy == 11.0
    assert all(row.source == "tushare_margin" for row in parsed)


def test_parse_tushare_margin_detail_maps_rzmre_and_blank_name():
    from personal.datahub.sources.margin_tushare_source import parse_margin_detail

    rows = [
        {"trade_date": "20261119", "ts_code": "600519.SH", "rzye": 14.5e8, "rzmre": 3.3e8, "rqye": 3.3e6},
        {"trade_date": "bad", "ts_code": "600519.SH", "rzye": 1.0},
    ]
    parsed = parse_margin_detail(rows, code="600519.SH")
    assert len(parsed) == 1
    row = parsed[0]
    assert row.code == "600519.SH" and row.name == ""
    assert row.rzye == 14.5e8 and row.rzye_buy == 3.3e8 and row.rqye == 3.3e6
    assert row.source == "tushare_margin"


def test_tushare_margin_source_fetches_summary_and_per_code_detail():
    from types import SimpleNamespace

    from personal.datahub.sources.margin_tushare_source import TushareMarginSource

    class _Client:
        def __init__(self):
            self.summary_calls = []
            self.detail_calls = []

        def fetch_margin_summary(self, start, end):
            self.summary_calls.append((start, end))
            return [
                {"trade_date": "20261119", "exchange_id": "SSE", "rzye": 100.0,
                 "rqye": 10.0, "rzrqye": 110.0, "rzmre": 5.0},
                {"trade_date": "20261119", "exchange_id": "SZSE", "rzye": 200.0,
                 "rqye": 20.0, "rzrqye": 220.0, "rzmre": 6.0},
            ]

        def fetch_margin_detail(self, code, start, end):
            self.detail_calls.append(code)
            return [{"trade_date": "20261119", "rzye": 1.0, "rzmre": 0.5, "rqye": 0.1}]

    source = TushareMarginSource(client=_Client(), min_interval=0)
    balances = source.fetch_margin_balance(date(2026, 11, 1), date(2026, 11, 19))
    stocks = source.fetch_margin_stock_rows(["600519.SH", "510300.SH"], date(2026, 11, 1), date(2026, 11, 19))
    assert len(balances) == 3
    assert {row.code for row in stocks} == {"600519.SH", "510300.SH"}
    assert source.calls == 3

    class _Broken:
        def fetch_margin_summary(self, start, end):
            raise RuntimeError("network down")

    from personal.datahub.sources.base import SourceUnavailable

    with pytest.raises(SourceUnavailable):
        TushareMarginSource(client=_Broken(), min_interval=0).fetch_margin_balance(
            date(2026, 11, 1), date(2026, 11, 19)
        )


def test_tushare_futures_source_rebuilds_main_contract_and_basis():
    from personal.datahub.sources.futures_tushare_source import TushareFuturesSource

    class _Client:
        def __init__(self):
            self.fut_calls = []

        def fetch_fut_mapping(self, continuous, start, end):
            if continuous != "IF.CFX":
                return []  # other families return nothing in this fixture
            return [
                {"trade_date": "20261116", "mapping_ts_code": "IF2611.CFX"},
                {"trade_date": "20261117", "mapping_ts_code": "IF2612.CFX"},
                {"trade_date": "20261118", "mapping_ts_code": "IF2612.CFX"},
            ]

        def fetch_fut_daily(self, code, start, end):
            self.fut_calls.append(code)
            bars = {
                "IF2611.CFX": {"20261116": (4000.0, 84000.0, 185000.0)},
                "IF2612.CFX": {"20261117": (3990.0, 70000.0, 186000.0),
                               "20261118": (3995.0, 71000.0, 187000.0)},
            }
            return [
                {"trade_date": day, "close": close, "vol": vol, "oi": oi}
                for day, (close, vol, oi) in bars.get(code, {}).items()
            ]

        def fetch_index_daily(self, code, start, end):
            assert code == "000300.SH"
            return [
                {"trade_date": "20261116", "close": 3980.0},
                {"trade_date": "20261117", "close": 3976.5},
                {"trade_date": "20261118", "close": 3978.0},
            ]

    source = TushareFuturesSource(client=_Client(), min_interval=0)
    rows = source.fetch_index_futures(date(2026, 11, 16), date(2026, 11, 18))
    assert [row.trade_date.isoformat() for row in rows] == [
        "2026-11-16", "2026-11-17", "2026-11-18",
    ]
    assert rows[0].basis == 20.0 and rows[0].basis_pct == round(20.0 / 3980.0 * 100, 4)
    # First day and the roll day carry no continuous oi_chg; after the roll it resumes.
    assert rows[0].oi_chg is None
    assert rows[1].oi_chg is None  # 11-17 switches IF2611 -> IF2612
    assert rows[2].oi_chg == 1000.0
    assert rows[0].source == "tushare_futures"
    # 4 mappings + two contracts + one spot index (families without data cost 1 call each)
    assert source.calls == 7


def test_tushare_release_source_aggregates_and_estimates_market_value():
    from personal.datahub.sources.release_tushare_source import TushareReleaseSource

    class _Client:
        def fetch_share_float(self, start, end):
            # 30-day chunks: only the chunk containing the float dates has rows.
            if not (start <= date(2026, 12, 16) and end >= date(2026, 12, 15)):
                return []
            return [
                {"ts_code": "600345.SH", "float_date": "20261215", "float_share": 5845173.0},
                {"ts_code": "600345.SH", "float_date": "20261215", "float_share": 5711096.0},
                {"ts_code": "000001.SZ", "float_date": "20261215", "float_share": 1000000.0},
                {"ts_code": "300001.SZ", "float_date": "20261216", "float_share": 500000.0},
            ]

        def fetch_daily_close_map(self, day):
            # Missing close for 300001.SZ → 12-16 gets no market value estimate.
            return {"600345.SH": 10.0, "000001.SZ": 20.0, "300001.SZ": None} if day else {}

    client = _Client()
    client.fetch_daily_close_map = lambda day: {"600345.SH": 10.0, "000001.SZ": 20.0}
    source = TushareReleaseSource(client=client)
    rows = source.fetch_release_summary(date(2026, 12, 1), date(2026, 12, 31))
    assert len(rows) == 2
    first = rows[0]
    assert first.release_date == date(2026, 12, 15)
    assert first.company_count == 2
    assert first.shares == 5845173.0 + 5711096.0 + 1000000.0
    assert first.market_value_yi == round((5845173.0 + 5711096.0) * 10.0 / 1e8 + 1000000.0 * 20.0 / 1e8, 2)
    second = rows[1]
    assert second.company_count == 1
    assert second.market_value_yi is None  # close missing → never partial


def test_margin_falls_back_to_tushare_when_exchange_empty(tmp_path, monkeypatch):
    from types import SimpleNamespace

    store = PersonalStore(tmp_path / "personal.db")
    try:
        class _EmptyExchange:
            def fetch_margin_all(self, start, end, codes):
                return [], []

        class _FakeTushareMargin:
            def __init__(self, *args, **kwargs):
                pass

            def fetch_margin_balance(self, start, end):
                return [MarginBalance(
                    trade_date=date(2026, 11, 19), scope_type="market",
                    scope="沪市", rzye=1.0, source="tushare_margin",
                )]

            def fetch_margin_stock_rows(self, codes, start, end):
                return []

        monkeypatch.setattr(
            "personal.config.get_settings",
            lambda: SimpleNamespace(tushare_token="fake"),
        )
        monkeypatch.setattr(
            "personal.datahub.sources.margin_tushare_source.TushareMarginSource",
            _FakeTushareMargin,
        )
        monkeypatch.setattr(
            "personal.datahub.market.MarginSource",
            _EmptyExchange,
        )
        result = sync_margin_balance(
            store,
            start=date(2026, 11, 15),
            end=date(2026, 11, 19),
            stock_codes=("600519.SH",),
        )
        assert result.rows == 1
        rows = store.get_margin_balance(limit=5)
        assert rows[0].source == "tushare_margin"
    finally:
        store.close()


def test_margin_prefer_tushare_skips_range_cap(tmp_path, monkeypatch):
    from types import SimpleNamespace

    store = PersonalStore(tmp_path / "personal.db")
    try:
        class _FakeTushareMargin:
            def __init__(self, *args, **kwargs):
                pass

            def fetch_margin_balance(self, start, end):
                assert (end - start).days > MARGIN_MAX_DAYS
                return [MarginBalance(
                    trade_date=end, scope_type="market", scope="沪市",
                    rzye=2.0, source="tushare_margin",
                )]

            def fetch_margin_stock_rows(self, codes, start, end):
                return [
                    MarginStockRow(
                        trade_date=end, code="600519", name="",
                        rzye=3.0, source="tushare_margin",
                    )
                ]

        # A stored name from earlier exchange rows is prefilled into the
        # nameless Tushare detail rows.
        store.upsert_margin_stock([
            MarginStockRow(
                trade_date=date(2025, 1, 2), code="600519", name="贵州茅台",
                rzye=1.0, source="exchange_margin",
            )
        ])
        monkeypatch.setattr(
            "personal.config.get_settings",
            lambda: SimpleNamespace(tushare_token="fake"),
        )
        monkeypatch.setattr(
            "personal.datahub.sources.margin_tushare_source.TushareMarginSource",
            _FakeTushareMargin,
        )
        result = sync_margin_balance(
            store,
            start=date(2025, 1, 1),
            end=date(2026, 11, 19),
            stock_codes=("600519",),
            prefer_tushare=True,
        )
        assert result.rows == 2
        stored = store.get_margin_stock(code="600519", limit=1)
        assert stored[0].name == "贵州茅台"
    finally:
        store.close()


def test_futures_prefers_tushare_and_falls_back(tmp_path, monkeypatch):
    from types import SimpleNamespace

    store = PersonalStore(tmp_path / "personal.db")
    try:
        class _FakeTushareFutures:
            def __init__(self, *args, **kwargs):
                pass

            def fetch_index_futures(self, start, end):
                return [
                    replace(
                        _futures_row("2026-11-18", close=3900.0, index_close=3975.0),
                        source="tushare_futures",
                    )
                ]

        monkeypatch.setattr(
            "personal.config.get_settings",
            lambda: SimpleNamespace(tushare_token="fake"),
        )
        monkeypatch.setattr(
            "personal.datahub.sources.futures_tushare_source.TushareFuturesSource",
            _FakeTushareFutures,
        )
        result = sync_index_futures(
            store, start=date(2026, 11, 15), end=date(2026, 11, 19)
        )
        assert result.rows == 1
        stored = store.get_index_futures(limit=5)
        assert stored[0].source == "tushare_futures"
    finally:
        store.close()


def test_release_falls_back_to_tushare_when_eastmoney_fails(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from personal.datahub.market import sync_restricted_release
    from personal.datahub.models import RestrictedRelease
    from personal.datahub.sources.base import SourceUnavailable

    store = PersonalStore(tmp_path / "personal.db")
    try:
        class _BrokenEM:
            def fetch_release_summary(self, start, end):
                raise SourceUnavailable("em blocked")

        class _FakeTushareRelease:
            def __init__(self, *args, **kwargs):
                pass

            def fetch_release_summary(self, start, end):
                return [RestrictedRelease(release_date=date(2026, 12, 15), company_count=3, shares=1000.0)]

        monkeypatch.setattr(
            "personal.config.get_settings",
            lambda: SimpleNamespace(tushare_token="fake"),
        )
        monkeypatch.setattr(
            "personal.datahub.market.ReleaseSource",
            _BrokenEM,
        )
        monkeypatch.setattr(
            "personal.datahub.sources.release_tushare_source.TushareReleaseSource",
            _FakeTushareRelease,
        )
        result = sync_restricted_release(
            store,
            start=date(2026, 12, 1),
            end=date(2026, 12, 31),
        )
        assert result.rows == 1

        # Without a token the EM failure propagates (no silent downgrade).
        monkeypatch.setattr(
            "personal.config.get_settings",
            lambda: SimpleNamespace(tushare_token=""),
        )
        with pytest.raises(SourceUnavailable):
            sync_restricted_release(
                store,
                start=date(2026, 12, 1),
                end=date(2026, 12, 31),
            )
    finally:
        store.close()


def test_margin_stock_upsert_never_blanks_a_name(tmp_path):
    from personal.datahub.models import MarginStockRow

    store = PersonalStore(tmp_path / "personal.db")
    try:
        store.upsert_margin_stock([
            MarginStockRow(trade_date=date(2026, 11, 19), code="600519.SH",
                           name="贵州茅台", rzye=1.0, source="exchange_margin"),
        ])
        store.upsert_margin_stock([
            MarginStockRow(trade_date=date(2026, 11, 19), code="600519.SH",
                           name="", rzye=2.0, source="tushare_margin"),
        ])
        rows = store.get_margin_stock(code="600519.SH", limit=5)
        assert rows[0].name == "贵州茅台"
        assert rows[0].source == "tushare_margin"
    finally:
        store.close()


def test_cli_margin_via_tushare_flag_routes_to_market_sync(monkeypatch):
    from types import SimpleNamespace

    from personal.cli import main as cli

    captured: dict = {}
    monkeypatch.setattr(
        cli, "_sync_market",
        lambda settings, args: captured.update(via_tushare=args.via_tushare) or 0,
    )
    assert cli._sync(None, SimpleNamespace(dataset="margin", via_tushare=True)) == 0
    assert captured["via_tushare"] is True


# ---------------------------------------------------------------------------
# Market breadth (TRIN) from Tushare full-market daily (CHG-0035)
# ---------------------------------------------------------------------------

def test_aggregate_market_rows_units_universe_and_identity():
    from personal.datahub.sources.arms_source import aggregate_market_rows

    rows = [
        # 沪深主板上涨：vol 1,000,000 手 = 1 亿股；amount 500,000 千元 = 5 亿元
        {"ts_code": "600000.SH", "change": 0.5, "vol": 1_000_000.0, "amount": 500_000.0},
        # 深市下跌
        {"ts_code": "000001.SZ", "change": -0.3, "vol": 2_000_000.0, "amount": 1_000_000.0},
        # 平盘
        {"ts_code": "600004.SH", "change": 0.0, "vol": 10_000.0, "amount": 5_000.0},
        # 北交所剔除
        {"ts_code": "920000.BJ", "change": 0.9, "vol": 900_000.0, "amount": 4_000_000.0},
        # ST 剔除
        {"ts_code": "600001.SH", "change": 0.7, "vol": 800_000.0, "amount": 3_000_000.0},
        # 退市整理剔除
        {"ts_code": "600002.SH", "change": -0.8, "vol": 700_000.0, "amount": 2_000_000.0},
        # 停牌（无 change）不计入样本
        {"ts_code": "600003.SH", "vol": 0.0, "amount": 0.0},
    ]
    breadth = aggregate_market_rows(
        rows,
        trade_date=date(2026, 11, 20),
        name_map={"600001.SH": "*ST示例", "600002.SH": "退市示例"},
        index_close=3500.0,
        index_chg_pct=-0.5,
    )
    assert breadth is not None
    assert breadth.up_count == 1 and breadth.down_count == 1 and breadth.flat_count == 1
    assert breadth.sample_count == 3
    assert breadth.up_count + breadth.down_count + breadth.flat_count == breadth.sample_count
    assert breadth.up_vol_yi == 1.0 and breadth.down_vol_yi == 2.0
    assert breadth.up_amount_yi == 5.0 and breadth.down_amount_yi == 10.0
    expected_trin = round((1 / 1) / (1.0 / 2.0), 3)
    assert breadth.trin == expected_trin
    # 成交额口径 TRIN：涨跌家数比 ÷ 涨跌成交额比
    assert breadth.trin_amount == round((1 / 1) / (5.0 / 10.0), 3)
    assert breadth.adv_ratio == round(1 / 3 * 100, 2)
    assert breadth.index_close == 3500.0 and breadth.index_chg_pct == -0.5
    assert breadth.source == "tushare_arms"
    assert breadth.band and breadth.interpretation


def test_sync_market_breadth_stores_rows_with_percentile(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from personal.datahub.market import sync_market_breadth
    from personal.datahub.models import MarketBreadth

    store = PersonalStore(tmp_path / "personal.db")
    try:
        calendar_days = [date(2026, 11, 18), date(2026, 11, 19), date(2026, 11, 20)]
        store.upsert_trading_calendar(calendar_days)
        # Pre-existing imported history: TRIN sample well below the new value.
        store.upsert_market_breadth([
            MarketBreadth(trade_date=date(2026, 11, 17), trin=0.4,
                          up_count=1, down_count=1, flat_count=0, sample_count=2,
                          adv_ratio=50.0, source="easy_daily_trading"),
        ])

        produced = [
            MarketBreadth(trade_date=calendar_days[1], trin=0.8, up_count=2,
                          down_count=2, flat_count=0, sample_count=4, adv_ratio=50.0,
                          source="tushare_arms"),
            MarketBreadth(trade_date=calendar_days[2], trin=1.2, up_count=3,
                          down_count=1, flat_count=0, sample_count=4, adv_ratio=75.0,
                          source="tushare_arms"),
        ]

        class _FakeArms:
            def __init__(self, *args, **kwargs):
                pass

            def fetch_market_breadth(self, days):
                assert list(days) == calendar_days
                return produced

        monkeypatch.setattr(
            "personal.config.get_settings",
            lambda: SimpleNamespace(tushare_token="fake"),
        )
        monkeypatch.setattr(
            "personal.datahub.sources.arms_source.TushareArmsSource",
            _FakeArms,
        )
        result = sync_market_breadth(
            store, start=date(2026, 11, 18), end=date(2026, 11, 20)
        )
        assert result.rows == 2
        stored = {row.trade_date: row for row in store.get_market_breadth()}
        # The imported 11-17 row stays (different PK) until Tushare overwrites it.
        assert stored[date(2026, 11, 17)].source == "easy_daily_trading"
        assert stored[date(2026, 11, 19)].trin_pct is not None
        # percentile_of counts samples strictly below the value; the batch is
        # enriched against the *stored* history (0.4 from 11-17) plus itself.
        assert stored[date(2026, 11, 20)].trin_pct == 50.0
        assert stored[date(2026, 11, 19)].source == "tushare_arms"
    finally:
        store.close()


def test_sync_market_breadth_requires_token(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from personal.datahub.market import sync_market_breadth
    from personal.datahub.sources.base import SourceUnavailable

    store = PersonalStore(tmp_path / "personal.db")
    try:
        store.upsert_trading_calendar([date(2026, 11, 20)])
        monkeypatch.setattr(
            "personal.config.get_settings",
            lambda: SimpleNamespace(tushare_token=""),
        )
        with pytest.raises(SourceUnavailable, match="import-arms"):
            sync_market_breadth(
                store, start=date(2026, 11, 20), end=date(2026, 11, 20)
            )
    finally:
        store.close()


def test_cli_breadth_dataset_routes_to_market_sync(monkeypatch):
    from types import SimpleNamespace

    from personal.cli import main as cli

    calls: list[str] = []
    monkeypatch.setattr(
        cli, "_sync_market", lambda settings, args: calls.append(args.dataset) or 0
    )
    assert cli._sync(None, SimpleNamespace(dataset="breadth")) == 0
    assert calls == ["breadth"]


# ---------------------------------------------------------------------------
# 2020-01-01 统一回补：分块 + turnover Tushare 兜底 + valuation start
# ---------------------------------------------------------------------------

def test_tushare_margin_source_chunks_long_ranges():
    from personal.datahub.sources.margin_tushare_source import TushareMarginSource

    class _Client:
        def __init__(self):
            self.calls = []

        def fetch_margin_summary(self, start, end):
            self.calls.append((start, end))
            return [
                {"trade_date": start.strftime("%Y%m%d"), "exchange_id": "SSE",
                 "rzye": 1.0, "rqye": 0.1, "rzrqye": 1.1, "rzmre": 0.2},
            ]

    source = TushareMarginSource(client=_Client(), min_interval=0)
    rows = source.fetch_margin_balance(date(2020, 1, 1), date(2026, 11, 20))
    # 2020→2026 全区间必须分块（margin 接口 4000 行上限）
    assert len(source._client.calls) >= 6
    assert len(rows) >= 6  # one parsed row per chunk


def test_tushare_release_source_chunks_share_float():
    from personal.datahub.sources.release_tushare_source import TushareReleaseSource

    class _Client:
        def __init__(self):
            self.calls = []

        def fetch_share_float(self, start, end):
            self.calls.append((start, end))
            return [
                {"ts_code": "600345.SH", "float_date": start.strftime("%Y%m%d"),
                 "float_share": 1000.0},
            ]

        def fetch_daily_close_map(self, day):
            return {"600345.SH": 10.0}

    source = TushareReleaseSource(client=_Client(), min_interval=0)
    rows = source.fetch_release_summary(date(2020, 1, 1), date(2026, 11, 20))
    assert len(source._client.calls) >= 6  # 6000 行上限 → 按年分块
    assert len(rows) >= 6


def test_tushare_turnover_source_converts_units_and_joins_indexes():
    from personal.datahub.sources.turnover_tushare_source import TushareTurnoverSource

    class _Client:
        def fetch_index_daily(self, code, start, end):
            return [
                {"trade_date": "20261119", "close": 1.0, "pre_close": 1.0,
                 "amount": 500_000_000.0},  # 千元 → 5e11 元
            ]

    source = TushareTurnoverSource(client=_Client(), min_interval=0)
    rows = source.fetch_turnover(date(2026, 11, 19), date(2026, 11, 19))
    assert len(rows) == 1
    assert rows[0].sse_amount == 5e11
    assert rows[0].szse_amount == 5e11
    assert rows[0].total_amount == 1e12


def test_turnover_falls_back_to_tushare_when_exchange_empty(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from personal.datahub.market import sync_turnover

    store = PersonalStore(tmp_path / "personal.db")
    try:
        class _EmptyExchange:
            def fetch_turnover(self, start, end):
                return []

        class _FakeTushareTurnover:
            def __init__(self, *args, **kwargs):
                pass

            def fetch_turnover(self, start, end):
                from personal.datahub.models import MarketTurnover

                return [MarketTurnover(trade_date=end, sse_amount=5e11, szse_amount=5e11)]

        monkeypatch.setattr(
            "personal.config.get_settings",
            lambda: SimpleNamespace(tushare_token="fake"),
        )
        monkeypatch.setattr(
            "personal.datahub.market.TurnoverSource",
            _EmptyExchange,
        )
        monkeypatch.setattr(
            "personal.datahub.sources.turnover_tushare_source.TushareTurnoverSource",
            _FakeTushareTurnover,
        )
        result = sync_turnover(store, start=date(2026, 11, 15), end=date(2026, 11, 19))
        assert result.rows == 1
        stored = store.get_market_turnover(limit=1)
        assert stored[0].total_amount == 1e12
    finally:
        store.close()


def test_sync_index_valuation_passes_start_to_source(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from personal.datahub.market import sync_index_valuation
    from personal.datahub.models import IndexValuation

    store = PersonalStore(tmp_path / "personal.db")
    try:
        captured: dict = {}

        class _FakeTushareValuation:
            name = "tushare"
            is_daily = True

            def __init__(self, *args, **kwargs):
                captured["start"] = kwargs.get("start")

            def fetch_index_valuation(self, code):
                return [
                    IndexValuation(code=code, trade_date=date(2026, 11, 20) - timedelta(days=index),
                                   name="test", pe_ttm=12.0 + index * 0.01, source="tushare")
                    for index in range(300)
                ]

        monkeypatch.setattr(
            "personal.config.get_settings",
            lambda: SimpleNamespace(tushare_token="fake"),
        )
        monkeypatch.setattr(
            "personal.datahub.sources.valuation_tushare_source.TushareValuationSource",
            _FakeTushareValuation,
        )
        sync_index_valuation(store, start=date(2020, 1, 1))
        assert captured["start"] == date(2020, 1, 1)
    finally:
        store.close()
