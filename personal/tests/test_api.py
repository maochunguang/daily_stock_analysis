from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from personal.api.app import create_app
from personal.config import get_settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def client(tmp_path):
    base = get_settings()
    settings = replace(
        base,
        personal_db=tmp_path / "personal.db",
        upstream_db=tmp_path / "upstream.db",
        plugin_dirs=(ROOT / "plugins",),
        plugin_allowlist=frozenset(),
        stock_list=("600519",),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


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
