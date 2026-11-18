import json
from datetime import date
from unittest.mock import patch

from personal.datahub.market import (
    MARGIN_MAX_DAYS,
    MarketSyncResult,
    sync_index_futures,
    sync_margin_balance,
)
from personal.datahub.models import IndexFutures, MarginBalance
from personal.datahub.sources.margin_source import classify_board
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
