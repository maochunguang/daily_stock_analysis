"""Configuration for the personal extension layer.

Uses only the standard library so the personal layer stays dependency-light.
Secrets are read from environment variables or a local env file that must not
be committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE lines without overriding existing env vars."""

    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_path(name: str, default: Path) -> Path:
    raw = _env(name)
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (ROOT / path).resolve()


def _env_paths(name: str, default: tuple[Path, ...]) -> tuple[Path, ...]:
    raw = _env(name)
    if not raw:
        return default
    paths: list[Path] = []
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        path = Path(item).expanduser()
        paths.append(path if path.is_absolute() else (ROOT / path).resolve())
    return tuple(paths) or default


def _default_upstream_dir(root: Path) -> Path:
    """Support both layouts: dev workspace (upstream/) and self-contained fork."""

    nested = root / "upstream"
    return nested if nested.is_dir() else root


def _default_upstream_db(root: Path) -> Path:
    """Use the nested upstream DB in the dev workspace, direct DB in the fork."""

    if (root / "upstream").is_dir():
        return root / "upstream" / "data" / "stock_analysis.db"
    return root / "data" / "stock_analysis.db"


@dataclass(frozen=True)
class Settings:
    root: Path
    upstream_dir: Path
    upstream_db: Path
    upstream_api: str
    upstream_timeout: float
    personal_db: Path
    data_dir: Path
    tushare_token: str
    stock_list: tuple[str, ...]
    data_source_priority: tuple[str, ...]
    plugins_enabled: bool
    plugin_dirs: tuple[Path, ...]
    plugin_allowlist: frozenset[str]
    qmt_bridge_url: str
    qmt_bridge_token: str
    qmt_trading_enabled: bool
    qmt_require_confirm: bool
    backtest_benchmark: str
    backtest_initial_cash: float
    backtest_adjust_mode: str
    cross_source_check: bool
    log_level: str
    ocr_enabled: bool
    ocr_max_image_mb: float
    risk_default_budget_pct: float
    risk_max_single_pct: float
    risk_max_top5_pct: float
    risk_min_cash_pct: float
    risk_max_liquidation_days: float
    risk_max_correlation: float


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once. ``config/personal.env`` wins over ``.env`` only when
    the variable is not already present in the process environment."""

    _load_env_file(ROOT / "config" / "personal.env")
    _load_env_file(ROOT / ".env")

    allowlist = {
        item.strip()
        for item in _env("PERSONAL_PLUGIN_ALLOWLIST").replace(";", ",").split(",")
        if item.strip()
    }
    priority = tuple(
        item.strip()
        for item in _env(
            "PERSONAL_DATA_SOURCE_PRIORITY", "tushare,baostock,akshare,tencent"
        ).split(",")
        if item.strip()
    )
    adjust_mode = _env("PERSONAL_BACKTEST_ADJUST", "hfq").lower() or "hfq"
    if adjust_mode not in {"hfq", "qfq", "none"}:
        adjust_mode = "hfq"

    return Settings(
        root=ROOT,
        upstream_dir=_env_path("PERSONAL_UPSTREAM_DIR", _default_upstream_dir(ROOT)),
        upstream_db=_env_path("PERSONAL_UPSTREAM_DB", _default_upstream_db(ROOT)),
        upstream_api=_env("PERSONAL_UPSTREAM_API", "http://127.0.0.1:8000"),
        upstream_timeout=_env_float("PERSONAL_UPSTREAM_TIMEOUT", 30.0),
        personal_db=_env_path("PERSONAL_DB", ROOT / "data" / "personal.db"),
        data_dir=_env_path("PERSONAL_DATA_DIR", ROOT / "data"),
        tushare_token=_env("TUSHARE_TOKEN"),
        stock_list=tuple(
            item.strip()
            for item in _env("PERSONAL_STOCK_LIST").replace(";", ",").split(",")
            if item.strip()
        ),
        data_source_priority=priority,
        plugins_enabled=_env_bool("PERSONAL_PLUGINS_ENABLED", True),
        plugin_dirs=_env_paths("PERSONAL_PLUGIN_DIRS", (ROOT / "plugins",)),
        plugin_allowlist=frozenset(allowlist),
        qmt_bridge_url=_env("QMT_BRIDGE_URL", "http://127.0.0.1:8710"),
        qmt_bridge_token=_env("QMT_BRIDGE_TOKEN"),
        qmt_trading_enabled=_env_bool("QMT_TRADING_ENABLED", False),
        qmt_require_confirm=_env_bool("QMT_REQUIRE_CONFIRM", True),
        backtest_benchmark=_env("PERSONAL_BACKTEST_BENCHMARK", "000300.SH"),
        backtest_initial_cash=_env_float("PERSONAL_BACKTEST_INITIAL_CASH", 1_000_000.0),
        backtest_adjust_mode=adjust_mode,
        cross_source_check=_env_bool("PERSONAL_CROSS_SOURCE_CHECK", True),
        log_level=_env("PERSONAL_LOG_LEVEL", "INFO").upper(),
        ocr_enabled=_env_bool("PERSONAL_OCR_ENABLED", True),
        ocr_max_image_mb=_env_float("PERSONAL_OCR_MAX_IMAGE_MB", 8.0),
        risk_default_budget_pct=_env_float(
            "PERSONAL_RISK_DEFAULT_BUDGET_PCT", 1.0
        ),
        risk_max_single_pct=_env_float("PERSONAL_RISK_MAX_SINGLE_PCT", 20.0),
        risk_max_top5_pct=_env_float("PERSONAL_RISK_MAX_TOP5_PCT", 60.0),
        risk_min_cash_pct=_env_float("PERSONAL_RISK_MIN_CASH_PCT", 5.0),
        risk_max_liquidation_days=_env_float(
            "PERSONAL_RISK_MAX_LIQUIDATION_DAYS", 5.0
        ),
        risk_max_correlation=_env_float("PERSONAL_RISK_MAX_CORRELATION", 0.85),
    )
