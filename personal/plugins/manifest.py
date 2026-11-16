"""Plugin manifest parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .api import PLUGIN_API_VERSION

ALLOWED_TYPES = {
    "indicator",
    "fund_metric",
    "report_section",
    "data_source",
    "strategy",
    "execution_adapter",
    "journal_hook",
}


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class PluginManifest:
    api_version: str
    name: str
    version: str
    type: str
    entry: str
    path: Path
    display_name: str = ""
    description: str = ""
    requires: dict[str, str] = field(default_factory=dict)
    permissions: tuple[str, ...] = ()
    config_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def directory(self) -> Path:
        return self.path.parent


def load_manifest(path: str | Path) -> PluginManifest:
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "plugin.yaml"
    if not manifest_path.is_file():
        raise ManifestError(f"manifest not found: {manifest_path}")

    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ManifestError(f"manifest must be a mapping: {manifest_path}")

    required = ("api_version", "name", "version", "type", "entry")
    missing = [key for key in required if not str(data.get(key) or "").strip()]
    if missing:
        raise ManifestError(f"missing manifest fields: {', '.join(missing)}")

    api_version = str(data["api_version"]).strip()
    if api_version != PLUGIN_API_VERSION:
        raise ManifestError(
            f"unsupported plugin api_version {api_version!r}; "
            f"expected {PLUGIN_API_VERSION!r}"
        )

    plugin_type = str(data["type"]).strip()
    if plugin_type not in ALLOWED_TYPES:
        raise ManifestError(f"unsupported plugin type: {plugin_type}")

    entry = str(data["entry"]).strip()
    if ":" not in entry:
        raise ManifestError("entry must use 'module:Class' format")

    requires = data.get("requires") or {}
    if not isinstance(requires, dict):
        raise ManifestError("requires must be a mapping")

    permissions = data.get("permissions") or []
    if not isinstance(permissions, list):
        raise ManifestError("permissions must be a list")

    config_schema = data.get("config_schema") or {}
    if not isinstance(config_schema, dict):
        raise ManifestError("config_schema must be a mapping")

    return PluginManifest(
        api_version=api_version,
        name=str(data["name"]).strip(),
        version=str(data["version"]).strip(),
        type=plugin_type,
        entry=entry,
        path=manifest_path,
        display_name=str(data.get("display_name") or ""),
        description=str(data.get("description") or ""),
        requires={str(k): str(v) for k, v in requires.items()},
        permissions=tuple(str(item) for item in permissions),
        config_schema=config_schema,
    )
