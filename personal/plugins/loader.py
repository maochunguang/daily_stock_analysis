"""Plugin discovery and isolated loading."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Iterable, Optional

from .manifest import PluginManifest, load_manifest
from .registry import PluginRegistry

REQUIRED_ATTRIBUTES = {
    "indicator": ("name", "version", "compute", "summarize", "render"),
    "strategy": ("name", "generate_targets"),
}


def discover(
    plugin_dirs: Iterable[str | Path], allowlist: Optional[frozenset[str]] = None
) -> list[PluginManifest]:
    manifests: list[PluginManifest] = []
    for raw_dir in plugin_dirs:
        directory = Path(raw_dir)
        if not directory.is_dir():
            continue
        for manifest_path in sorted(directory.glob("*/plugin.yaml")):
            try:
                manifest = load_manifest(manifest_path)
            except Exception:
                continue
            if allowlist and manifest.name not in allowlist:
                continue
            manifests.append(manifest)
    return manifests


def load_plugins(
    plugin_dirs: Iterable[str | Path],
    allowlist: Optional[frozenset[str]] = None,
) -> tuple[PluginRegistry, list[str]]:
    registry = PluginRegistry()
    errors: list[str] = []
    for manifest in discover(plugin_dirs, allowlist):
        try:
            instance = _load_instance(manifest)
            _validate_instance(manifest, instance)
            registry.register(manifest, instance)
        except Exception as exc:  # noqa: BLE001 - one bad plugin must not stop the rest
            errors.append(f"{manifest.name}: {exc}")
    return registry, errors


def _load_instance(manifest: PluginManifest) -> object:
    module_name, class_name = manifest.entry.split(":", 1)
    module_path = manifest.directory / f"{module_name}.py"
    if not module_path.is_file():
        raise FileNotFoundError(f"plugin entry not found: {module_path}")
    module_spec = importlib.util.spec_from_file_location(
        f"dsa_personal_plugin_{manifest.name}", module_path
    )
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"cannot load plugin module: {module_path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    target = getattr(module, class_name, None)
    if target is None:
        raise AttributeError(f"plugin class not found: {class_name}")
    return target()


def _validate_instance(manifest: PluginManifest, instance: object) -> None:
    for attribute in REQUIRED_ATTRIBUTES.get(manifest.type, ()):
        if not hasattr(instance, attribute):
            raise AttributeError(
                f"{manifest.type} plugin {manifest.name} missing attribute: {attribute}"
            )
