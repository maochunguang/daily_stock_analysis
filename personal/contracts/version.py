"""Upstream capability detection.

The personal layer branches on capabilities, not on hard-coded version numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .upstream_db import UpstreamDB


@dataclass(frozen=True)
class UpstreamCapabilities:
    available: bool
    has_analysis_history: bool
    has_portfolio: bool
    has_decision_signals: bool
    missing: tuple[str, ...]

    @property
    def degraded(self) -> bool:
        return not self.available or bool(self.missing)


def detect(db_path: str | Path) -> UpstreamCapabilities:
    db = UpstreamDB(db_path)
    if not db.available:
        return UpstreamCapabilities(
            available=False,
            has_analysis_history=False,
            has_portfolio=False,
            has_decision_signals=False,
            missing=(f"database missing: {db.path}",),
        )
    tables = set(db.list_tables())
    return UpstreamCapabilities(
        available=True,
        has_analysis_history="analysis_history" in tables,
        has_portfolio="portfolio_accounts" in tables
        and "portfolio_trades" in tables,
        has_decision_signals="decision_signals" in tables,
        missing=tuple(db.missing_contracts()),
    )
