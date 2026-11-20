"""Tushare CFFEX index-futures adapter (2000-point token).

Rebuilds the IF/IH/IC/IM main-contract daily series from official exchange
data:

1. ``fut_mapping`` maps each continuous code (``IF.CFX``) to its main
   contract per trading day.
2. ``fut_daily`` fetches each distinct main contract once over its own
   date span (close/vol/oi are official CFFEX figures).
3. ``index_daily`` provides the spot index closes for basis math.

This is the primary source for ``sync_index_futures`` when a token is
configured; the AkShare/Sina main-continuous adapter stays as fallback
(it has a known jump on contract rolls). ``oi_chg`` is recomputed across
the assembled per-family series — the per-contract ``oi_chg`` from
``fut_daily`` would jump at rolls, unlike the continuous view.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

from ..models import IndexFutures
from .base import SourceUnavailable
from .futures_source import FUTURES_SPEC

#: Tushare spot index codes (``index_daily``); FUTURES_SPEC carries Sina codes
#: only, so the futures adapter keeps its own mapping.
SPOT_INDEX_CODES: dict[str, str] = {
    "IF": "000300.SH",  # 沪深300
    "IH": "000016.SH",  # 上证50
    "IC": "000905.SH",  # 中证500
    "IM": "000852.SH",  # 中证1000
}

#: conservative pacing between Tushare calls (28+ requests for a 1.5y backfill)
MIN_INTERVAL_SECONDS = 0.3


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


class TushareFuturesSource:
    """Main-contract index futures from official CFFEX data via Tushare."""

    name = "tushare_futures"

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

    def fetch_index_futures(self, start: date, end: date) -> list[IndexFutures]:
        spot: dict[str, dict[date, float]] = {}
        rows: list[IndexFutures] = []
        for symbol in FUTURES_SPEC:
            family_rows = self._family_rows(symbol, start, end)
            if not family_rows:
                continue
            index_code = SPOT_INDEX_CODES[symbol]
            if index_code not in spot:
                spot[index_code] = self._index_closes(index_code, start, end)
            closes = spot[index_code]
            prev_oi: float | None = None
            prev_contract: str | None = None
            for day in sorted(family_rows):
                contract, close, volume, oi = family_rows[day]
                index_close = closes.get(day)
                basis = (
                    round(close - index_close, 4)
                    if close is not None and index_close is not None
                    else None
                )
                basis_pct = (
                    round(basis / index_close * 100, 4)
                    if basis is not None and index_close
                    else None
                )
                # Across a main-contract switch the two contracts' OI levels
                # are not comparable (migration in progress) — leave oi_chg
                # empty instead of reporting a fake jump.
                rolled = prev_contract is not None and contract != prev_contract
                oi_chg = (
                    round(oi - prev_oi, 0)
                    if oi is not None
                    and prev_oi is not None
                    and not rolled
                    else None
                )
                rows.append(
                    IndexFutures(
                        trade_date=day,
                        symbol=symbol,
                        close=close,
                        volume=volume,
                        open_interest=oi,
                        oi_chg=oi_chg,
                        index_close=index_close,
                        basis=basis,
                        basis_pct=basis_pct,
                        source=self.name,
                    )
                )
                prev_oi = oi
                prev_contract = contract
        if not rows:
            raise SourceUnavailable("tushare futures returned no rows")
        return rows

    def _family_rows(
        self, symbol: str, start: date, end: date
    ) -> dict[date, tuple[str, float | None, float | None, float | None]]:
        """{trade_date: (main contract, close, volume, oi)} for one family."""

        mapping = self._fetch("fetch_fut_mapping", f"{symbol}.CFX", start, end)
        by_day: dict[date, str] = {}
        for row in mapping:
            day = _to_day(row.get("trade_date"))
            contract = str(row.get("mapping_ts_code") or "").strip()
            if day is None or not contract:
                continue
            by_day[day] = contract
        if not by_day:
            return {}

        spans: dict[str, tuple[date, date]] = {}
        for day, contract in by_day.items():
            first, last = spans.get(contract, (day, day))
            spans[contract] = (min(first, day), max(last, day))

        bars: dict[str, dict[date, dict[str, float | None]]] = {}
        for contract, (first, last) in sorted(spans.items()):
            for row in self._fetch("fetch_fut_daily", contract, first, last):
                day = _to_day(row.get("trade_date"))
                if day is None:
                    continue
                bars.setdefault(contract, {})[day] = {
                    "close": _to_float(row.get("close")),
                    "vol": _to_float(row.get("vol")),
                    "oi": _to_float(row.get("oi")),
                }

        out: dict[date, tuple[str, float | None, float | None, float | None]] = {}
        for day, contract in by_day.items():
            bar = bars.get(contract, {}).get(day)
            if bar is None:
                continue
            out[day] = (contract, bar["close"], bar["vol"], bar["oi"])
        return out

    def _index_closes(
        self, index_code: str, start: date, end: date
    ) -> dict[date, float]:
        out: dict[date, float] = {}
        for row in self._fetch("fetch_index_daily", index_code, start, end):
            day = _to_day(row.get("trade_date"))
            close = _to_float(row.get("close"))
            if day is not None and close is not None and start <= day <= end:
                out[day] = close
        return out
