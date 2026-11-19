from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from personal.analytics.index_valuation import (
    index_valuation_report,
    valuation_cross_check,
)
from personal.datahub.market import sync_index_valuation
from personal.datahub.models import IndexValuation
from personal.datahub.sources.valuation_source import (
    LeguleguValuationSource,
    keep_week_latest,
    parse_legulegu_payload,
)
from personal.datahub.store import PersonalStore


def _weekly_rows(
    code: str,
    *,
    end: date,
    count: int,
    start_pe: float,
    step: float,
    source: str = "legulegu",
) -> list[IndexValuation]:
    rows: list[IndexValuation] = []
    for index in range(count):
        day = end - timedelta(weeks=count - 1 - index)
        rows.append(
            IndexValuation(
                code=code,
                trade_date=day,
                name="test",
                pe_ttm=start_pe + index * step,
                pe_ttm_equal=start_pe + index * step + 10,
                source=source,
            )
        )
    return rows


class _Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return _Response(self.status_code, self.payload)


def _payload(dates: list[str], values: list[float]) -> dict:
    return {
        "vip": False,
        "data": [
            {
                "date": day,
                "addTtmPe": value,
                "ttmPe": value + 10,
                "addLyrPe": value + 1,
                "middleTtmPe": value + 2,
                "close": 4000,
            }
            for day, value in zip(dates, values)
        ],
    }


def test_parse_payload_and_keep_latest_per_week():
    payload = _payload(
        ["2026-11-13", "2026-11-18", "2026-11-19", "2026-11-20"],
        [12.6, 12.7, 12.8, 12.9],
    )
    rows = parse_legulegu_payload(payload, code="000300.SH", name="沪深300")
    assert [row.pe_ttm for row in rows] == [12.6, 12.7, 12.8, 12.9]

    weekly = keep_week_latest(rows)
    # 11-18/11-19/11-20 are in the same ISO week; keep the latest date.
    assert [row.trade_date.isoformat() for row in weekly] == [
        "2026-11-13",
        "2026-11-20",
    ]


def test_parse_skips_invalid_and_non_positive_rows():
    payload = {
        "data": [
            {"date": "not-a-date", "addTtmPe": 10},
            {"date": "2026-11-01", "addTtmPe": 0},
            {"date": "2026-11-02", "addTtmPe": None},
            {"date": "2026-11-03", "addTtmPe": "12.3", "ttmPe": "20.1"},
        ]
    }
    rows = parse_legulegu_payload(payload, code="000300.SH")
    assert len(rows) == 1
    assert rows[0].pe_ttm == 12.3
    assert rows[0].pe_ttm_equal == 20.1


def test_source_requests_weekly_history_with_cookie_page():
    payload = _payload(["2026-11-13", "2026-11-19"], [12.6, 12.69])
    session = _Session(payload)
    source = LeguleguValuationSource(session=session, min_interval=0)
    rows = source.fetch_index_valuation("000300.SH")
    assert len(rows) == 2
    assert rows[-1].name == "沪深300"
    assert session.calls[0][0] == "https://legulegu.com/stockdata/hs300-ttm-lyr"
    assert session.calls[1][1]["freq"] == "week"
    assert session.calls[1][1]["indexCode"] == "000300.SH"
    assert len(session.calls[1][1]["token"]) == 32

    with pytest.raises(Exception):
        source.fetch_index_valuation("000001.SH")


def test_store_replace_keeps_sources_isolated(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    try:
        end = date(2026, 11, 19)
        store.replace_index_valuations(
            "000300.SH", _weekly_rows("000300.SH", end=end, count=100, start_pe=10, step=0.1)
        )
        store.replace_index_valuations(
            "000300.SH",
            _weekly_rows(
                "000300.SH",
                end=end,
                count=52,
                start_pe=20,
                step=0.1,
                source="other",
            ),
            source="other",
        )
        rows = store.get_index_valuations(code="000300.SH", source="legulegu")
        assert len(rows) == 100
        assert rows[-1].pe_ttm == pytest.approx(19.9)
        other = store.get_index_valuations(code="000300.SH", source="other")
        assert len(other) == 52
    finally:
        store.close()


def test_report_percentiles_cheap_and_expensive(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    end = date(2026, 11, 19)
    try:
        # Rising series ends at the top of every window.
        store.replace_index_valuations(
            "000300.SH",
            _weekly_rows("000300.SH", end=end, count=300, start_pe=10, step=0.01),
        )
        # Falling series ends near the bottom of every window.
        store.replace_index_valuations(
            "399006.SZ",
            _weekly_rows("399006.SZ", end=end, count=300, start_pe=60, step=-0.01),
        )
        report = index_valuation_report(store, as_of=end)
        by_code = {row["code"]: row for row in report["rows"]}
        hs300 = by_code["000300.SH"]
        cyb = by_code["399006.SZ"]
        assert hs300["available"] is True
        assert hs300["sample_freq"] == "weekly"
        assert hs300["stale_days"] == 0
        assert hs300["windows"]["1y"]["samples"] == 53
        assert hs300["windows"]["1y"]["percentile"] == 100.0
        assert hs300["windows"]["5y"]["percentile"] == 100.0
        assert cyb["windows"]["1y"]["percentile"] < 5.0
        assert cyb["windows"]["5y"]["percentile"] < 5.0

        # Missing indexes still appear, with an explicit unavailable state.
        assert by_code["000688.SH"]["available"] is False
        assert by_code["000688.SH"]["windows"] == {}

        stale = index_valuation_report(store, as_of=end + timedelta(days=10))
        assert stale["rows"][0]["stale_days"] == 10
    finally:
        store.close()


def test_sync_replaces_partial_failure(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    end = date(2026, 11, 19)

    class _FakeSource:
        name = "fake"

        def __init__(self):
            self.calls: list[str] = []

        def fetch_index_valuation(self, code):
            self.calls.append(code)
            if code == "399673.SZ":
                raise RuntimeError("rate limited")
            return _weekly_rows(code, end=end, count=60, start_pe=10, step=0.1)

    source = _FakeSource()
    try:
        with pytest.raises(Exception, match="partial valuation sync"):
            sync_index_valuation(store, source=source)
        assert source.calls == ["000300.SH", "399006.SZ", "399673.SZ", "000688.SH"]
        assert len(store.get_index_valuations(code="000300.SH", source="fake")) == 60
        assert store.get_index_valuations(code="399673.SZ") == []
    finally:
        store.close()


def test_sync_all_success(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    end = date(2026, 11, 19)

    class _FakeSource:
        name = "fake"

        def fetch_index_valuation(self, code):
            return _weekly_rows(code, end=end, count=60, start_pe=10, step=0.1)

    try:
        result = sync_index_valuation(store, source=_FakeSource())
        assert result.dataset == "valuation"
        assert result.rows == 240
        assert result.latest_date == end
        assert result.message == ""
        assert len(store.get_index_valuations(source="fake")) == 240
    finally:
        store.close()


def test_cli_routes_valuation_to_market_sync(monkeypatch):
    from types import SimpleNamespace

    from personal.cli import main as cli

    calls: list[str] = []
    monkeypatch.setattr(
        cli, "_sync_market", lambda settings, args: calls.append(args.dataset) or 0
    )
    assert cli._sync(None, SimpleNamespace(dataset="valuation")) == 0
    assert calls == ["valuation"]


def test_api_market_sync_valuation(client, monkeypatch):
    from personal.datahub.market import MarketSyncResult

    def fake_sync(store):
        return MarketSyncResult(
            dataset="valuation",
            start=date(2026, 11, 19),
            end=date(2026, 11, 19),
            rows=4,
            latest_date=date(2026, 11, 19),
        )

    monkeypatch.setattr(
        "personal.datahub.market.sync_index_valuation", fake_sync
    )
    response = client.post("/api/market/sync", json={"dataset": "valuation"})
    assert response.status_code == 200
    assert response.json()["dataset"] == "valuation"
    assert response.json()["rows"] == 4


def test_parse_csi_frame_selects_pe1_total_share():
    import pandas as pd

    from personal.datahub.sources.valuation_check_source import (
        OFFICIAL_VALUATION_TARGETS,
        _parse_csindex_frame,
    )

    frame = pd.DataFrame(
        {
            "日期Date": [20261118, 20261119],
            "市盈率1（总股本）P/E1": [13.7, 13.77],
            "市盈率2（计算用股本）P/E2": [14.9, 15.0],
        }
    )
    result = _parse_csindex_frame(frame, OFFICIAL_VALUATION_TARGETS["000300.SH"])
    assert result["official_pe"] == 13.77
    assert result["official_date"] == "2026-11-19"
    assert result["official_source"] == "中证指数"


def test_cross_check_compares_matching_metrics(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    end = date(2026, 11, 19)
    try:
        store.replace_index_valuations(
            "000300.SH",
            [IndexValuation("000300.SH", end, "沪深300", pe_ttm=12.69, pe_static=13.25)],
        )
        store.replace_index_valuations(
            "000688.SH",
            [IndexValuation("000688.SH", end, "科创50", pe_ttm=60.19, pe_static=95.85)],
        )
        store.replace_index_valuations(
            "399006.SZ",
            [IndexValuation("399006.SZ", end, "创业板指", pe_ttm=22.12, pe_static=28.7)],
        )
        store.replace_index_valuations(
            "399673.SZ",
            [IndexValuation("399673.SZ", end, "创业板50", pe_ttm=20.94, pe_static=27.53)],
        )
        official = {
            "000300.SH": {
                "official_pe": 13.8,
                "official_date": "2026-11-19",
                "official_source": "中证指数",
                "official_metric": "中证 PE1（总股本）",
            },
            "000688.SH": {
                "official_pe": 60.0,
                "official_date": "2026-11-19",
                "official_source": "中证指数",
                "official_metric": "中证 PE1（总股本）",
            },
            "399006.SZ": {
                "official_pe": 22.69,
                "official_date": None,
                "official_source": "国证指数",
                "official_metric": "国证 PE滚动（TTM）",
            },
            "399673.SZ": {
                "official_pe": 25.0,
                "official_date": None,
                "official_source": "国证指数",
                "official_metric": "国证 PE滚动（TTM）",
            },
        }
        report = valuation_cross_check(
            store,
            official,
            checked_at=datetime(2026, 11, 19, 20, 0),
        )
        by_code = {row["code"]: row for row in report["rows"]}
        assert by_code["000300.SH"]["status"] == "ok"
        assert by_code["000300.SH"]["diff_pct"] == pytest.approx(-4.0, abs=0.1)
        assert by_code["399006.SZ"]["status"] == "ok"
        assert by_code["000688.SH"]["status"] == "error"
        assert by_code["399673.SZ"]["status"] == "error"
        assert len(report["warnings"]) == 2
        assert "口径" in report["note"]
    finally:
        store.close()


def test_cross_check_marks_unavailable_source(tmp_path):
    store = PersonalStore(tmp_path / "personal.db")
    end = date(2026, 11, 19)
    try:
        store.replace_index_valuations(
            "000300.SH",
            [IndexValuation("000300.SH", end, "沪深300", pe_ttm=12.69, pe_static=13.25)],
        )
        report = valuation_cross_check(
            store,
            {"000300.SH": {"error": "official timeout"}},
        )
        row = report["rows"][0]
        assert row["status"] == "unavailable"
        assert "timeout" in row["detail"]
        assert report["warnings"]
    finally:
        store.close()


def test_api_index_valuation_check(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from personal.api.app import create_app
    from personal.config import get_settings

    base = get_settings()
    settings = replace(
        base,
        personal_db=tmp_path / "personal.db",
        upstream_db=tmp_path / "upstream.db",
        plugin_dirs=(),
        plugin_allowlist=frozenset(),
        stock_list=("600519",),
    )
    end = date(2026, 11, 19)
    store = PersonalStore(settings.personal_db)
    try:
        store.replace_index_valuations(
            "000300.SH",
            [IndexValuation("000300.SH", end, "沪深300", pe_ttm=12.69, pe_static=13.25)],
        )
    finally:
        store.close()

    monkeypatch.setattr(
        "personal.datahub.sources.valuation_check_source.fetch_official_valuations",
        lambda: {
            "000300.SH": {
                "official_pe": 13.8,
                "official_date": "2026-11-19",
                "official_source": "中证指数",
                "official_metric": "中证 PE1（总股本）",
            }
        },
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/market/index-valuation/check")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["rows"]) == 4
        assert payload["rows"][0]["status"] == "ok"


def test_api_index_valuation(tmp_path):
    from fastapi.testclient import TestClient

    from personal.api.app import create_app
    from personal.config import get_settings

    base = get_settings()
    settings = replace(
        base,
        personal_db=tmp_path / "personal.db",
        upstream_db=tmp_path / "upstream.db",
        plugin_dirs=(),
        plugin_allowlist=frozenset(),
        stock_list=("600519",),
    )
    end = date(2026, 11, 19)
    store = PersonalStore(settings.personal_db)
    try:
        store.replace_index_valuations(
            "000300.SH",
            _weekly_rows("000300.SH", end=end, count=260, start_pe=10, step=0.01),
        )
    finally:
        store.close()

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/market/index-valuation")
        assert response.status_code == 200
        payload = response.json()
        assert payload["available"] is True
        assert len(payload["rows"]) == 4
        hs300 = payload["rows"][0]
        assert hs300["code"] == "000300.SH"
        assert hs300["pe_ttm"] is not None
        assert hs300["windows"]["1y"]["percentile"] is not None
