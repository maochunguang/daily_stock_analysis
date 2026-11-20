"""Tushare turnover adapter (2000-point token).

Fallback for the exchange-turnover scraper: the 上证指数 (``000001.SH``) and
深证综指 (``399106.SZ``) cover every listed stock of their exchange, so their
``index_daily`` amounts equal the SSE/SZSE stock turnover. Cross-check on
2026-11-19: index amounts differ from the stored exchange figures by ~0.1%.

Units: Tushare ``amount`` is 千元 → the model stores yuan (×1000). Chunked
``index_daily`` calls (the interface returns ~1700 rows for 6.7 years in one
call, chunked anyway for safety).
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

from ..models import MarketTurnover
from .base import SourceUnavailable, date_chunks

#: 沪市/深市全市场对应指数
EXCHANGE_INDEXES: dict[str, str] = {
    "sse": "000001.SH",  # 上证指数（全部沪市 A 股）
    "szse": "399106.SZ",  # 深证综指（全部深市 A 股）
}

CHUNK_DAYS = 1000
MIN_INTERVAL_SECONDS = 0.35


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


class TushareTurnoverSource:
    """Exchange stock turnover from index_daily amounts (yuan)."""

    name = "tushare_turnover"

    def __init__(
        self,
        client: Any | None = None,
        *,
        token: str = "",
        timeout: float = 30.0,
        min_interval: float = MIN_INTERVAL_SECONDS,
    ):
        if client is None:
            if not token.strip():
                raise SourceUnavailable("TUSHARE_TOKEN is not configured")
            from .tushare_source import TushareSource

            client = TushareSource(token.strip(), timeout=timeout)
        self._client = client
        self.min_interval = min_interval
        self.calls = 0

    def _fetch(self, method: str, *args) -> list[dict[str, Any]]:
        if self.calls:
            time.sleep(self.min_interval)
        self.calls += 1
        try:
            return getattr(self._client, method)(*args)
        except SourceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize transport errors
            raise SourceUnavailable(f"tushare {method} request failed: {exc}") from exc

    def fetch_turnover(self, start: date, end: date) -> list[MarketTurnover]:
        amounts: dict[str, dict[date, float]] = {}
        for scope, index_code in EXCHANGE_INDEXES.items():
            per_day: dict[date, float] = {}
            for chunk_start, chunk_end in date_chunks(start, end, CHUNK_DAYS):
                for row in self._fetch("fetch_index_daily", index_code, chunk_start, chunk_end):
                    day = _to_day(row.get("trade_date"))
                    amount = _to_float(row.get("amount"))
                    if day is not None and amount is not None and start <= day <= end:
                        per_day[day] = amount * 1000.0
            amounts[scope] = per_day

        rows: list[MarketTurnover] = []
        for day in sorted(set(amounts["sse"]) & set(amounts["szse"])):
            sse = amounts["sse"].get(day)
            szse = amounts["szse"].get(day)
            if not sse or not szse:
                continue
            rows.append(
                MarketTurnover(
                    trade_date=day,
                    sse_amount=sse,
                    szse_amount=szse,
                )
            )
        if not rows:
            raise SourceUnavailable("tushare turnover returned no rows")
        return rows
