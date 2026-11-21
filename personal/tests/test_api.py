from dataclasses import replace
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from personal.api.app import create_app
from personal.config import get_settings

ROOT = Path(__file__).resolve().parents[2]


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "DSA Personal Console" in response.text


def test_status_and_plugins(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["upstream"]["available"] is False
    assert any(item["name"] == "obv" for item in payload["plugins"])
    assert "storage" in payload

    plugins = client.get("/api/plugins").json()
    assert any(item["name"] == "obv" for item in plugins["plugins"])


def test_sync_and_coverage(client):
    response = client.post(
        "/api/data/sync",
        json={
            "dataset": "bars",
            "source": "synthetic",
            "codes": ["600519"],
            "start": "2026-01-01",
            "end": "2026-03-01",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["rows"] > 0

    coverage = client.get("/api/data/coverage").json()
    assert coverage["stats"]["daily_bar"] > 0
    assert any(row["code"] == "600519.SH" for row in coverage["coverage"])


def test_demo_backtest(client):
    response = client.post("/api/backtest/demo", json={"days": 120, "save": False})
    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "demo"
    assert len(payload["equity"]) > 0
    assert "total_return" in payload["metrics"]


def test_replay_requires_upstream(client):
    response = client.post("/api/backtest/replay", json={"include": "both"})
    assert response.status_code == 400
    assert "upstream database missing" in response.json()["detail"]


def test_upstream_recent_missing(client):
    response = client.get("/api/upstream/recent")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["analyses"] == []


def test_market_breadth_endpoint(client, tmp_path):
    empty = client.get("/api/market/breadth")
    assert empty.status_code == 200
    assert empty.json()["rows"] == []

    from personal.datahub.breadth import load_easy_daily_snapshots
    from personal.datahub.store import PersonalStore

    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    snapshot = {
        "date": "2026-11-17",
        "up": 1192,
        "down": 3717,
        "flat": 117,
        "total": 5026,
        "up_vol_yi": 306.61,
        "down_vol_yi": 623.52,
        "trin": 0.652,
        "adv_ratio": 23.7,
        "band": "中低位",
        "signal": "中低位｜普跌+量能尚可 → 弱势整理",
        "pct": 32.6,
        "index": 3584.58,
        "index_chg": -0.5,
        "signal_tag": "—",
        "divergence": 0,
    }
    (daily_dir / "2026-11-17.json").write_text(json.dumps(snapshot), encoding="utf-8")
    store = PersonalStore(tmp_path / "personal.db")
    try:
        store.upsert_market_breadth(list(load_easy_daily_snapshots(daily_dir)))
    finally:
        store.close()

    response = client.get("/api/market/breadth")
    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["trade_date"] == "2026-11-17"
    assert rows[0]["trin"] == 0.652
    assert rows[0]["down_count"] == 3717

    bounded = client.get("/api/market/breadth", params={"days": 0})
    assert bounded.status_code == 422


def test_can_be_mounted_under_upstream_prefix(tmp_path):
    base = get_settings()
    settings = replace(
        base,
        personal_db=tmp_path / "personal.db",
        upstream_db=tmp_path / "upstream.db",
        plugin_dirs=(ROOT / "plugins",),
        plugin_allowlist=frozenset(),
    )
    parent = FastAPI()
    parent.mount("/personal-api", create_app(settings))
    with TestClient(parent) as test_client:
        response = test_client.get("/personal-api/api/status")
        assert response.status_code == 200
        assert response.json()["app"]["version"]


def test_calendar_and_status_sync(client):
    bars = client.post(
        "/api/data/sync",
        json={
            "dataset": "bars",
            "source": "synthetic",
            "codes": ["600519"],
            "start": "2026-01-01",
            "end": "2026-03-01",
        },
    )
    assert bars.status_code == 200

    calendar = client.post(
        "/api/data/sync",
        json={
            "dataset": "calendar",
            "source": "synthetic",
            "start": "2026-01-01",
            "end": "2026-03-01",
        },
    )
    assert calendar.status_code == 200
    assert calendar.json()["results"][0]["rows"] > 0

    status = client.post(
        "/api/data/sync",
        json={
            "dataset": "status",
            "source": "synthetic",
            "codes": ["600519"],
            "start": "2026-01-01",
            "end": "2026-03-01",
        },
    )
    assert status.status_code == 200
    assert status.json()["results"][0]["rows"] > 0

    stats = client.get("/api/status").json()["storage"]
    assert stats["trading_calendar"] > 0
    assert stats["trading_status"] > 0


def test_market_validate_endpoint(client):
    response = client.get("/api/market/validate?days=30")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "empty"
    assert payload["score"] == 50
    assert {item["dataset"] for item in payload["datasets"]} >= {
        "turnover", "margin", "futures", "pcr", "sector", "etf_share", "bond",
    }
    assert all(item["status"] == "empty" for item in payload["datasets"])


def _sync_basket_bars(client) -> None:
    response = client.post(
        "/api/data/sync",
        json={
            "dataset": "bars",
            "source": "synthetic",
            "codes": ["600519", "000858"],
            "start": "2025-06-02",
            "end": "2025-08-29",
        },
    )
    assert response.status_code == 200
    assert response.json()["results"][0]["rows"] > 0


def test_basket_backtest_runs_and_reports_per_stock(client):
    _sync_basket_bars(client)
    response = client.post(
        "/api/backtest/basket",
        json={
            "codes": ["600519:0.6", "000858"],
            "start": "2025-06-02",
            "end": "2025-08-29",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "basket"
    assert payload["codes"] == ["600519.SH", "000858.SZ"]
    assert payload["weights"]["600519.SH"] == pytest.approx(0.6)
    assert payload["weights"]["000858.SZ"] == pytest.approx(0.4)
    assert payload["skipped"] == []
    assert payload["rebalance"] == "none"
    assert len(payload["per_stock"]) == 2
    assert {row["code"] for row in payload["per_stock"]} == {"600519.SH", "000858.SZ"}
    assert all("return_pct" in row for row in payload["per_stock"])
    assert len(payload["equity"]) > 1
    assert any(trade["reason"] == "basket entry" for trade in payload["trades"])


def test_basket_backtest_save_persists_run(client):
    _sync_basket_bars(client)
    response = client.post(
        "/api/backtest/basket",
        json={
            "codes": ["600519", "000858"],
            "start": "2025-06-02",
            "end": "2025-08-29",
            "rebalance": "monthly",
            "save": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"].startswith("basket-")
    assert payload["rebalance"] == "monthly"

    runs = client.get("/api/backtest/runs").json()["runs"]
    assert any(run["run_id"] == payload["run_id"] and run["mode"] == "basket" for run in runs)


def test_basket_backtest_rejects_empty_and_unsyncable_codes(client, monkeypatch):
    response = client.post("/api/backtest/basket", json={"codes": []})
    assert response.status_code == 400
    assert "no basket codes" in response.json()["detail"]

    # Auto-sync runs before the "all missing" verdict; keep it offline and
    # empty so the basket still reports the codes as missing.
    monkeypatch.setattr(
        "personal.api.app.build_sources", lambda settings, requested="auto": []
    )
    response = client.post(
        "/api/backtest/basket",
        json={"codes": ["999999"], "start": "2025-06-02", "end": "2025-08-29"},
    )
    assert response.status_code == 400
    assert "no local bars for basket codes" in response.json()["detail"]


def test_basket_auto_syncs_missing_codes(client, monkeypatch):
    from personal.datahub.sources.base import SyntheticSource

    monkeypatch.setattr(
        "personal.api.app.build_sources",
        lambda settings, requested="auto": [SyntheticSource()],
    )
    response = client.post(
        "/api/backtest/basket",
        json={"codes": ["600519"], "start": "2025-06-02", "end": "2025-08-29"},
    )
    assert response.status_code == 200
    payload = response.json()
    # the benchmark (000300.SH) is probed and auto-synced alongside the codes
    assert payload["auto_synced"] == ["600519.SH", "000300.SH"]
    assert payload["skipped"] == []
    assert len(payload["per_stock"]) == 1
    assert payload["per_stock"][0]["code"] == "600519.SH"
    assert payload["per_stock"][0]["first_date"] == "2025-06-02"
    assert len(payload["equity"]) > 1
    assert payload["benchmark"] is not None
    assert payload["metrics"]["benchmark_return"] is not None
    assert payload["metrics"]["excess_return"] is not None


def test_basket_top_ups_stale_window(client, monkeypatch):
    from personal.datahub.sources.base import SyntheticSource

    # Seed only the tail of the requested window (like the scheduled sync).
    tail = client.post(
        "/api/data/sync",
        json={
            "dataset": "bars",
            "source": "synthetic",
            "codes": ["600519"],
            "start": "2025-07-01",
            "end": "2025-08-29",
        },
    )
    assert tail.status_code == 200

    monkeypatch.setattr(
        "personal.api.app.build_sources",
        lambda settings, requested="auto": [SyntheticSource()],
    )
    response = client.post(
        "/api/backtest/basket",
        json={"codes": ["600519"], "start": "2025-06-02", "end": "2025-08-29"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["auto_synced"] == ["600519.SH", "000300.SH"]
    assert payload["per_stock"][0]["first_date"] == "2025-06-02"
    # full window now covered (Jun+Jul+Aug weekdays), not just the July tail
    assert len(payload["equity"]) > 60


def test_basket_backtest_rejects_bad_weight(client):
    response = client.post("/api/backtest/basket", json={"codes": ["600519:abc"]})
    assert response.status_code == 400
    assert "invalid weight" in response.json()["detail"]
