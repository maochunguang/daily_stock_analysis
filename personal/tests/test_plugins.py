from pathlib import Path

import pandas as pd
import pytest

from personal.plugins.builtin.obv import OBVIndicator
from personal.plugins.loader import load_plugins
from personal.plugins.manifest import ManifestError, load_manifest

ROOT = Path(__file__).resolve().parents[2]


def test_load_external_plugin_directory():
    registry, errors = load_plugins([ROOT / "plugins"])
    assert errors == []
    assert "obv" in registry.names()
    plugin = registry.get("obv")
    assert plugin is not None
    assert plugin.manifest.type == "indicator"


def test_obv_compute_and_summary():
    df = pd.DataFrame(
        {
            "close": [10, 11, 10.5, 12, 11.8],
            "volume": [1000, 1200, 900, 1500, 800],
        }
    )
    indicator = OBVIndicator()
    result = indicator.compute(df, {"window": 3})
    assert "obv" in result.columns
    assert "obv_ma" in result.columns
    summary = indicator.summarize(result, {"window": 3})
    assert summary["obv"] is not None
    assert isinstance(summary["above_ma"], bool)
    text = indicator.render(summary)
    assert "OBV" in text


def test_invalid_manifest_rejected(tmp_path):
    manifest = tmp_path / "plugin.yaml"
    manifest.write_text(
        "api_version: '9.9'\nname: bad\nversion: '1'\ntype: indicator\nentry: p:X\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError):
        load_manifest(manifest)
