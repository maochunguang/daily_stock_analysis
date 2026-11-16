"""Stable plugin API.

Plugins may import only this module. They must not import upstream modules or
personal business modules such as backtest/engine.py.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

import pandas as pd

PLUGIN_API_VERSION = "1.0"


class PluginContext(Protocol):
    settings: Any
    logger: Any

    def get_bars(self, code: str, days: int = 250) -> pd.DataFrame: ...


class IndicatorPlugin(Protocol):
    name: str
    version: str
    required_columns: tuple[str, ...]

    def compute(self, df: pd.DataFrame, params: Mapping[str, Any]) -> pd.DataFrame: ...

    def summarize(self, df: pd.DataFrame, params: Mapping[str, Any]) -> dict[str, Any]: ...

    def render(self, summary: dict[str, Any], *, language: str = "zh") -> str: ...


class StrategyPlugin(Protocol):
    name: str

    def generate_targets(self, ctx: PluginContext, trade_date: Any) -> dict[str, float]: ...
