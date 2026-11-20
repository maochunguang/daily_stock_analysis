"""Daily index valuation from Tushare ``index_dailybasic``.

With a 2000-point token this interface exposes the full daily PE history for
broad-based indexes, which is strictly better than the weekly Legulegu series
used as fallback: percentiles get ~244 samples per year instead of ~52.

Field mapping (total-share base, same as the official CSI PE1):

================= ================================
``pe_ttm``        weighted rolling PE (used)
``pe``            static PE (total-share, LYR)
``close``         index close
================= ================================

``index_dailybasic`` has no equal-weight or median series, so those model
fields stay empty; the card shows the equal-weight line as ``—`` for this
source.  Requests are chunked by ~380-day windows and spaced with a
conservative ``min_interval`` because the 2000-point tier still rate-limits
per interface.  A truncated fetch (< ``MIN_DAILY_ROWS``) raises
``SourceUnavailable`` so ``sync_index_valuation`` keeps the previous series
(or falls back to Legulegu) instead of replacing history with a stub.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any, Sequence

from ..models import IndexValuation
from .base import SourceUnavailable, date_chunks
from .valuation_source import INDEX_VALUATION_NAMES

#: Look back far enough to fill the 5-year window (+ buffer for holidays).
HISTORY_DAYS = 365 * 5 + 40
#: Calendar-day span per ``index_dailybasic`` request (~250 trading rows).
CHUNK_DAYS = 380
#: Conservative spacing between requests; 2000-point tiers still cap per-interface QPS.
MIN_INTERVAL_SECONDS = 0.5
#: A real 5-year daily series has ~1200 rows; below this the fetch is truncated.
MIN_DAILY_ROWS = 200


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_trade_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_tushare_dailybasic(
    rows: Sequence[dict[str, Any]],
    *,
    code: str,
    source: str = "tushare",
) -> list[IndexValuation]:
    """Parse raw ``index_dailybasic`` records into validated observations."""

    parsed: list[IndexValuation] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        trade_date = _parse_trade_date(item.get("trade_date"))
        if trade_date is None:
            continue
        pe_ttm = _to_float(item.get("pe_ttm"))
        if pe_ttm is None or pe_ttm <= 0:
            continue
        parsed.append(
            IndexValuation(
                code=code,
                trade_date=trade_date,
                name=INDEX_VALUATION_NAMES.get(code, code),
                pe_ttm=pe_ttm,
                pe_ttm_equal=None,
                pe_static=_to_float(item.get("pe")),
                pe_ttm_median=None,
                close=_to_float(item.get("close")),
                source=source,
            )
        )
    parsed.sort(key=lambda row: row.trade_date)
    return parsed


class TushareValuationSource:
    """Fetch daily PE history for the configured broad-based indexes."""

    name = "tushare"
    is_daily = True

    def __init__(
        self,
        client: Any | None = None,
        *,
        token: str = "",
        timeout: float = 30.0,
        min_interval: float = MIN_INTERVAL_SECONDS,
        history_days: int = HISTORY_DAYS,
        chunk_days: int = CHUNK_DAYS,
        min_rows: int = MIN_DAILY_ROWS,
        start: date | None = None,
    ):
        if client is None:
            if not token.strip():
                raise SourceUnavailable("TUSHARE_TOKEN is not configured")
            from .tushare_source import TushareSource

            client = TushareSource(token.strip(), timeout=timeout)
        self._client = client
        self.min_interval = min_interval
        self.history_days = history_days
        self.chunk_days = chunk_days
        self.min_rows = min_rows
        self._start = start
        self.calls = 0

    def fetch_index_valuation(self, code: str) -> list[IndexValuation]:
        if code not in INDEX_VALUATION_NAMES:
            raise SourceUnavailable(f"unsupported index valuation code: {code}")
        end = date.today()
        start = self._start or (end - timedelta(days=self.history_days))
        observations: dict[date, IndexValuation] = {}
        for index, (chunk_start, chunk_end) in enumerate(
            date_chunks(start, end, self.chunk_days)
        ):
            if index:
                time.sleep(self.min_interval)
            self.calls += 1
            try:
                raw = self._client.fetch_index_dailybasic(
                    code, chunk_start, chunk_end
                )
            except SourceUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 - normalize transport errors
                raise SourceUnavailable(f"tushare request failed: {exc}") from exc
            for row in parse_tushare_dailybasic(raw, code=code, source=self.name):
                observations[row.trade_date] = row
        rows = sorted(observations.values(), key=lambda row: row.trade_date)
        if len(rows) < self.min_rows:
            raise SourceUnavailable(
                f"tushare returned only {len(rows)} daily observations for {code}"
            )
        return rows

    def fetch_index_valuations(
        self, codes: Sequence[str] = tuple(INDEX_VALUATION_NAMES)
    ) -> list[IndexValuation]:
        rows: list[IndexValuation] = []
        for code in codes:
            rows.extend(self.fetch_index_valuation(code))
        return rows
