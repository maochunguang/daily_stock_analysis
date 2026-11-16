"""Plugin registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .manifest import PluginManifest


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    instance: Any


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, LoadedPlugin] = {}

    def register(self, manifest: PluginManifest, instance: Any) -> None:
        if manifest.name in self._plugins:
            raise ValueError(f"plugin already registered: {manifest.name}")
        self._plugins[manifest.name] = LoadedPlugin(manifest=manifest, instance=instance)

    def get(self, name: str) -> Optional[LoadedPlugin]:
        return self._plugins.get(name)

    def all(self, type_: Optional[str] = None) -> list[LoadedPlugin]:
        plugins = list(self._plugins.values())
        if type_ is None:
            return plugins
        return [plugin for plugin in plugins if plugin.manifest.type == type_]

    def names(self) -> list[str]:
        return sorted(self._plugins)

    def __len__(self) -> int:
        return len(self._plugins)
