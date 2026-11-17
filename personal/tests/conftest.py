from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(tmp_path):
    from fastapi.testclient import TestClient

    from personal.api.app import create_app
    from personal.config import get_settings

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
