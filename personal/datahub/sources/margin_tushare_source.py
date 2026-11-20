"""Tushare margin-financing adapter (2000-point token).

Fallback for the exchange scraper: ``margin`` provides the exchange-level
summary (rzye/rzmre/rqye/rzrqye, yuan) and ``margin_detail`` provides
per-instrument rows queryable by ``ts_code``, so a full history backfill for
watchlist codes costs one request per code instead of one request per day.

Only ``SSE``/``SZSE`` rows are used (BSE excluded to match the 沪市/深市/总计
scopes). Board splits are not available here — the exchange detail scrape
stays the primary source for those rows.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from ..models import MarginBalance, MarginStockRow
from .base import SourceUnavailable, date_chunks

EXCHANGE_SCOPE = {"SSE": "沪市", "SZSE": "深市"}


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


def parse_margin_summary(rows: Sequence[dict[str, Any]]) -> list[MarginBalance]:
    """Parse ``margin`` rows into 沪市/深市/总计 market rows (yuan)."""

    by_day: dict[date, dict[str, dict[str, float]]] = {}
    for row in rows:
        day = _to_day(row.get("trade_date"))
        exchange = str(row.get("exchange_id") or "").strip()
        scope = EXCHANGE_SCOPE.get(exchange)
        if day is None or scope is None:
            continue
        values = {
            "rzye": _to_float(row.get("rzye")),
            "rqye": _to_float(row.get("rqye")),
            "rzrqye": _to_float(row.get("rzrqye")),
            "rzye_buy": _to_float(row.get("rzmre")),
        }
        by_day.setdefault(day, {})[scope] = values

    out: list[MarginBalance] = []
    for day in sorted(by_day):
        for scope in ("沪市", "深市"):
            values = by_day[day].get(scope)
            if values is None:
                continue
            out.append(
                MarginBalance(
                    trade_date=day,
                    scope_type="market",
                    scope=scope,
                    source="tushare_margin",
                    **values,
                )
            )
        sse = by_day[day].get("沪市")
        szse = by_day[day].get("深市")
        if sse is not None and szse is not None:
            def _sum(key: str) -> float | None:
                left, right = sse.get(key), szse.get(key)
                if left is None or right is None:
                    return None
                return left + right

            out.append(
                MarginBalance(
                    trade_date=day,
                    scope_type="market",
                    scope="总计",
                    rzye=_sum("rzye"),
                    rqye=_sum("rqye"),
                    rzrqye=_sum("rzrqye"),
                    rzye_buy=_sum("rzye_buy"),
                    source="tushare_margin",
                )
            )
    return out


def parse_margin_detail(
    rows: Sequence[dict[str, Any]],
    *,
    code: str,
    source: str = "tushare_margin",
) -> list[MarginStockRow]:
    """Parse ``margin_detail`` rows for one instrument (yuan, no name)."""

    out: list[MarginStockRow] = []
    for row in rows:
        day = _to_day(row.get("trade_date"))
        if day is None:
            continue
        out.append(
            MarginStockRow(
                trade_date=day,
                code=code,
                name="",  # blank never overwrites a stored name (store guard)
                rzye=_to_float(row.get("rzye")),
                rzye_buy=_to_float(row.get("rzmre")),
                rqye=_to_float(row.get("rqye")),
                source=source,
            )
        )
    out.sort(key=lambda row: row.trade_date)
    return out


class TushareMarginSource:
    """Margin summary + per-code detail via Tushare (2000-point token)."""

    name = "tushare_margin"

    def __init__(
        self,
        client: Any | None = None,
        *,
        token: str = "",
        timeout: float = 30.0,
        min_interval: float = 0.3,
    ):
        if client is None:
            if not token.strip():
                raise SourceUnavailable("TUSHARE_TOKEN is not configured")
            from .tushare_source import TushareSource

            client = TushareSource(token.strip(), timeout=timeout)
        self._client = client
        self.min_interval = min_interval
        self.calls = 0

    def _throttle(self) -> None:
        if self.calls:
            import time

            time.sleep(self.min_interval)
        self.calls += 1

    #: `margin` caps at 4000 rows per call; 500 calendar days (~365 trading
    #: days x 3 exchanges ≈ 1100 rows) stays far below it.
    SUMMARY_CHUNK_DAYS = 500

    def fetch_margin_balance(self, start: date, end: date) -> list[MarginBalance]:
        raw: list[dict] = []
        for chunk_start, chunk_end in date_chunks(
            start, end, self.SUMMARY_CHUNK_DAYS
        ):
            self._throttle()
            try:
                raw.extend(
                    self._client.fetch_margin_summary(chunk_start, chunk_end)
                )
            except SourceUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 - normalize transport errors
                raise SourceUnavailable(
                    f"tushare margin request failed: {exc}"
                ) from exc
        rows = parse_margin_summary(raw)
        if not rows:
            raise SourceUnavailable("tushare margin returned no summary rows")
        return rows

    def fetch_margin_stock_rows(
        self, codes: Sequence[str], start: date, end: date
    ) -> list[MarginStockRow]:
        rows: list[MarginStockRow] = []
        for code in codes:
            normalized = code.strip()
            if not normalized:
                continue
            self._throttle()
            try:
                raw = self._client.fetch_margin_detail(
                    normalized, start, end
                )
            except SourceUnavailable as exc:
                raise SourceUnavailable(f"tushare margin_detail failed: {exc}") from exc
            except Exception as exc:  # noqa: BLE001 - normalize transport errors
                raise SourceUnavailable(
                    f"tushare margin_detail request failed: {exc}"
                ) from exc
            rows.extend(parse_margin_detail(raw, code=normalized, source=self.name))
        return rows
