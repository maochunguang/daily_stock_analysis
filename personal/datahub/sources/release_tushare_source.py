"""Tushare restricted-release adapter (2000-point token).

Fallback for the Eastmoney release-calendar source. ``share_float`` rows are
aggregated per ``float_date`` into the same daily shape as
``RestrictedRelease`` (shares unit: 股, matching the Eastmoney adapter):

- ``company_count`` = distinct instruments releasing that day
- ``shares`` = sum of ``float_share`` (股)
- ``market_value_yi`` = Σ float_share × latest close (estimated at the latest
  completed session's price, since future float dates have no close yet);
  left empty when any code lacks a price so a partial estimate is never
  shown as complete.

The Eastmoney source stays primary because it carries the official
实际解禁市值; this fallback fills the calendar when Eastmoney is unavailable
and is identifiable through the ``source`` column in ``sync_state`` logs.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any, Callable, Sequence

from ..models import RestrictedRelease
from .base import SourceUnavailable, date_chunks


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


class TushareReleaseSource:
    name = "tushare_share_float"

    def __init__(
        self,
        client: Any | None = None,
        *,
        token: str = "",
        timeout: float = 30.0,
        min_interval: float = 0.35,
        close_provider: Callable[[date], dict[str, float]] | None = None,
    ):
        if client is None:
            if not token.strip():
                raise SourceUnavailable("TUSHARE_TOKEN is not configured")
            from .tushare_source import TushareSource

            client = TushareSource(token.strip(), timeout=timeout)
        self._client = client
        self._close_provider = close_provider
        self.min_interval = min_interval

    #: `share_float` returns one row per HOLDER (months run 5k+ rows) and caps
    #: at 6000 per call — 30-day chunks stay safely below it.
    FLOAT_CHUNK_DAYS = 30

    def fetch_release_summary(self, start: date, end: date) -> list[RestrictedRelease]:
        try:
            raw: list[dict] = []
            chunks = date_chunks(start, end, self.FLOAT_CHUNK_DAYS)
            for index, (chunk_start, chunk_end) in enumerate(chunks):
                if index:
                    time.sleep(self.min_interval)
                raw.extend(self._client.fetch_share_float(chunk_start, chunk_end))
            close_map = self._latest_closes()
        except SourceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize transport errors
            raise SourceUnavailable(f"tushare share_float request failed: {exc}") from exc

        buckets: dict[date, dict[str, float]] = {}
        for row in raw:
            day = _to_day(row.get("float_date"))
            code = str(row.get("ts_code") or "").strip()
            shares = _to_float(row.get("float_share"))
            if day is None or not code or shares is None or shares <= 0:
                continue
            bucket = buckets.setdefault(day, {})
            bucket[code] = bucket.get(code, 0.0) + shares

        out: list[RestrictedRelease] = []
        for day in sorted(buckets):
            per_code = buckets[day]
            mv_yuan: float | None = 0.0
            for code, shares in per_code.items():
                close = close_map.get(code)
                if close is None:
                    mv_yuan = None  # incomplete price coverage → no estimate
                    break
                if mv_yuan is not None:
                    mv_yuan += shares * close
            out.append(
                RestrictedRelease(
                    release_date=day,
                    company_count=len(per_code),
                    shares=round(sum(per_code.values()), 2),
                    market_value_yi=(
                        round(mv_yuan / 1e8, 2) if mv_yuan is not None else None
                    ),
                )
            )
        return out

    def _latest_closes(self) -> dict[str, float]:
        """code -> close, walking back over weekends/holidays until data exists."""

        day = self._candidate_session(date.today())
        for _attempt in range(6):
            closes = (
                self._close_provider(day)
                if self._close_provider is not None
                else self._client.fetch_daily_close_map(day)
            )
            if closes:
                return closes
            day = self._candidate_session(day - timedelta(days=1))
        return {}

    @staticmethod
    def _candidate_session(day: date) -> date:
        while day.weekday() >= 5:
            day = day - timedelta(days=1)
        return day
