import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from personal.config import get_settings
from personal.datahub.schedule import (
    DEFAULT_DATASETS,
    next_run_at,
    parse_at,
    run_scheduled_sync,
)
from personal.datahub.store import PersonalStore


class TestParseAt:
    def test_valid(self):
        assert parse_at("06:00") == datetime.strptime("06:00", "%H:%M").time()
        assert parse_at("5") == datetime.strptime("05:00", "%H:%M").time()

    def test_invalid(self):
        for value in ("", "25:00", "6:70", "a:b", "1:2:3"):
            with pytest.raises(ValueError):
                parse_at(value)


class TestNextRunAt:
    def test_before_today_slot(self):
        now = datetime(2026, 11, 17, 2, 30)
        target = next_run_at(now, parse_at("06:00"))
        assert target == datetime(2026, 11, 17, 6, 0)

    def test_after_today_slot_rolls_to_tomorrow(self):
        now = datetime(2026, 11, 17, 6, 1)
        target = next_run_at(now, parse_at("06:00"))
        assert target == datetime(2026, 11, 18, 6, 0)


class TestRunScheduledSync:
    @pytest.fixture()
    def settings(self, tmp_path):
        from dataclasses import replace

        base = get_settings()
        return replace(
            base,
            personal_db=tmp_path / "personal.db",
            upstream_db=tmp_path / "upstream.db",
            stock_list=("600519",),
        )

    def test_market_datasets_record_state(self, settings, tmp_path, monkeypatch):
        from personal.datahub.market import MarketSyncResult

        def fake_futures(store, *, start, end):
            return MarketSyncResult(
                dataset="futures", start=start, end=end, rows=40,
                latest_date=date(2026, 11, 17), message="",
            )

        def fake_margin(store, *, start, end, stock_codes=()):
            return MarketSyncResult(
                dataset="margin", start=start, end=end, rows=35,
                latest_date=date(2026, 11, 16), message="",
            )

        monkeypatch.setattr("personal.datahub.schedule.sync_index_futures", fake_futures)
        monkeypatch.setattr("personal.datahub.schedule.sync_margin_balance", fake_margin)

        store = PersonalStore(tmp_path / "personal.db")
        try:
            results = run_scheduled_sync(
                settings,
                datasets=("futures", "margin"),
                store=store,
                log=lambda _msg: None,
            )
            assert [r.ok for r in results] == [True, True]
            assert [r.rows for r in results] == [40, 35]
            state = {row["dataset"]: row for row in store.get_sync_state()}
            assert state["futures"]["last_ok_date"] == date.today().isoformat()
            assert state["margin"]["rows"] == 35
            assert state["margin"]["last_error"] in (None, "")
        finally:
            store.close()

    def test_failure_keeps_error_and_previous_ok(self, settings, tmp_path, monkeypatch):
        def failing_futures(store, *, start, end):
            raise RuntimeError("akshare is not installed")

        monkeypatch.setattr(
            "personal.datahub.schedule.sync_index_futures", failing_futures
        )
        store = PersonalStore(tmp_path / "personal.db")
        try:
            store.record_sync_state(
                "futures", ok=True, rows=40, ok_date=date(2026, 11, 16)
            )
            results = run_scheduled_sync(
                settings,
                datasets=("futures",),
                store=store,
                log=lambda _msg: None,
            )
            assert results[0].ok is False
            assert "akshare" in results[0].message
            state = {row["dataset"]: row for row in store.get_sync_state()}["futures"]
            # 失败不清空上一次成功记录
            assert state["last_ok_date"] == date(2026, 11, 16).isoformat()
            assert "akshare" in (state["last_error"] or "")
        finally:
            store.close()

    def test_unknown_dataset_is_recorded_as_failed(self, settings, tmp_path):
        store = PersonalStore(tmp_path / "personal.db")
        try:
            results = run_scheduled_sync(
                settings,
                datasets=("nope",),
                store=store,
                log=lambda _msg: None,
            )
            assert results[0].ok is False
            assert "unknown dataset" in results[0].message
        finally:
            store.close()

    def test_calendar_dataset_uses_injected_service(self, settings, tmp_path, monkeypatch):
        fake_service = SimpleNamespace(
            sync_calendar=lambda start, end: SimpleNamespace(rows=56, errors=[]),
        )
        monkeypatch.setattr(
            "personal.datahub.schedule.build_sources", lambda settings, source: {}
        )
        monkeypatch.setattr(
            "personal.datahub.schedule.DataSyncService",
            lambda store, sources, **kwargs: fake_service,
        )
        store = PersonalStore(tmp_path / "personal.db")
        try:
            results = run_scheduled_sync(
                settings,
                datasets=("calendar",),
                store=store,
                log=lambda _msg: None,
            )
            assert results[0].ok is True
            assert results[0].rows == 56
        finally:
            store.close()

    def test_default_datasets_cover_market(self):
        assert set(DEFAULT_DATASETS) >= {
            "futures",
            "valuation",
            "margin",
            "bars",
            "calendar",
            "breadth",
        }
