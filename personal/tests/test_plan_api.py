from __future__ import annotations

import base64
from datetime import date, timedelta


def _snapshot_payload(day: str | None = None) -> dict:
    return {
        "account_alias": "同花顺",
        "as_of": day or date.today().isoformat(),
        "cash": 500_000,
        "available_cash": 500_000,
        "market_value": 500_000,
        "equity": 1_000_000,
        "positions": [
            {
                "code": "510300",
                "name": "沪深300ETF",
                "quantity": 10000,
                "available_quantity": 10000,
                "avg_cost": 4.0,
                "market_price": 5.0,
                "market_value": 50000,
            }
        ],
    }


def _plan_payload(snapshot_id: int | None = None) -> dict:
    return {
        "plan_date": date.today().isoformat(),
        "code": "600519",
        "name": "贵州茅台",
        "side": "buy",
        "entry_low": 10.0,
        "entry_high": 10.1,
        "stop_loss": 9.5,
        "target_price": 12.0,
        "risk_budget_pct": 1.0,
        "max_position_pct": 20.0,
        "account_snapshot_id": snapshot_id,
        "status": "active",
        "thesis": "test thesis",
        "invalidation": "test invalidation",
    }


def test_account_snapshot_and_plan_flow(client):
    created = client.post("/api/account-snapshots", json=_snapshot_payload())
    assert created.status_code == 200
    snapshot_id = created.json()["snapshot_id"]
    latest = client.get("/api/account-snapshots/latest")
    assert latest.status_code == 200
    assert latest.json()["snapshot"]["positions"][0]["code"] == "510300.SH"

    preview = client.post("/api/trade-plans/preview", json=_plan_payload(snapshot_id))
    assert preview.status_code == 200
    preview_payload = preview.json()["preview"]
    assert preview_payload["suggested_quantity"] > 0
    assert not preview_payload["blockers"]

    plan = client.post("/api/trade-plans", json=_plan_payload(snapshot_id))
    assert plan.status_code == 200
    plan_payload = plan.json()["plan"]
    assert plan_payload["code"] == "600519.SH"
    assert plan_payload["fill_count"] == 0
    plan_id = plan_payload["id"]

    plans = client.get("/api/trade-plans?status=active")
    assert plans.status_code == 200
    assert plans.json()["plans"][0]["id"] == plan_id

    update_payload = _plan_payload(snapshot_id)
    update_payload["entry_high"] = 10.4
    update_payload["thesis"] = "updated thesis"
    updated = client.put(f"/api/trade-plans/{plan_id}", json=update_payload)
    assert updated.status_code == 200
    assert updated.json()["plan"]["entry_high"] == 10.4
    assert updated.json()["plan"]["thesis"] == "updated thesis"

    patched = client.patch(
        f"/api/trade-plans/{plan_id}", json={"status": "draft"}
    )
    assert patched.status_code == 200
    assert patched.json()["plan"]["status"] == "draft"

    risk = client.get("/api/portfolio/risk")
    assert risk.status_code == 200
    assert risk.json()["available"] is True
    assert risk.json()["top1_pct"] > 0


def test_plan_requires_snapshot(client):
    response = client.post("/api/trade-plans/preview", json=_plan_payload())
    assert response.status_code == 400
    assert "账户快照" in response.json()["detail"]


def test_screenshot_parse_mock_and_size_limit(client, monkeypatch):
    import personal.api.app as app_module

    def fake_parse(content, filename="", max_mb=8, enabled=True):
        assert filename == "ths.png"
        return {
            "filename": filename,
            "content_hash": "abc",
            "ocr_engine": "fake",
            "draft": {
                "account_alias": "同花顺",
                "as_of": date.today().isoformat(),
                "equity": 100000,
                "positions": [],
            },
            "warnings": [],
            "line_count": 3,
        }

    monkeypatch.setattr(app_module, "parse_account_screenshot", fake_parse)
    response = client.post(
        "/api/account-snapshots/parse",
        json={"filename": "ths.png", "content_b64": base64.b64encode(b"png").decode()},
    )
    assert response.status_code == 200
    assert response.json()["draft"]["equity"] == 100000

    oversized = "A" * (12 * 1024 * 1024)
    response = client.post(
        "/api/account-snapshots/parse",
        json={"filename": "big.png", "content_b64": oversized},
    )
    assert response.status_code == 400
    assert "8MB" in response.json()["detail"]


def test_import_with_plan_and_outcomes(client):
    snapshot = client.post("/api/account-snapshots", json=_snapshot_payload())
    snapshot_id = snapshot.json()["snapshot_id"]
    plan = client.post("/api/trade-plans", json=_plan_payload(snapshot_id))
    plan_id = plan.json()["plan"]["id"]

    today = date.today()
    sync = client.post(
        "/api/data/sync",
        json={
            "dataset": "bars",
            "source": "synthetic",
            "codes": ["600519"],
            "start": (today - timedelta(days=140)).isoformat(),
            "end": today.isoformat(),
        },
    )
    assert sync.status_code == 200
    trade_date = (today - timedelta(days=60)).isoformat()
    statement = (
        "交易日期,证券代码,证券名称,业务名称,成交数量,成交价格,成交金额,手续费\n"
        f"{trade_date},600519,贵州茅台,证券买入,100,10.00,1000.00,5.00\n"
    )
    imported = client.post(
        "/api/broker/import",
        json={
            "filename": "deal.csv",
            "content_b64": base64.b64encode(statement.encode("utf-8")).decode(),
            "plan_id": plan_id,
        },
    )
    assert imported.status_code == 200
    assert imported.json()["plan_linked"] == 1
    plan_detail = client.get(f"/api/trade-plans/{plan_id}").json()["plan"]
    assert plan_detail["fill_count"] == 1
    assert plan_detail["filled_quantity"] == 100

    outcomes = client.get("/api/journal/outcomes?horizon=20&days=365")
    assert outcomes.status_code == 200
    payload = outcomes.json()
    assert payload["rows"]
    assert payload["rows"][0]["plan_id"] == plan_id
    assert payload["rows"][0]["status"] == "completed"
    assert payload["summary"]["horizon"] == 20
    assert payload["available_horizons"] == [1, 5, 20, 60]
