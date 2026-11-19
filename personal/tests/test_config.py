from __future__ import annotations

import os

import personal.config as config_module
from personal.config import get_settings


def test_runtime_env_file_feeds_webui_stock_list(monkeypatch, tmp_path):
    runtime = tmp_path / "runtime.env"
    runtime.write_text("STOCK_LIST=600519,510300\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "ROOT", tmp_path)
    monkeypatch.setenv("ENV_FILE", str(runtime))
    monkeypatch.delenv("PERSONAL_STOCK_LIST", raising=False)
    monkeypatch.delenv("STOCK_LIST", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.stock_list == ("600519", "510300")
    finally:
        os.environ.pop("STOCK_LIST", None)
        get_settings.cache_clear()
