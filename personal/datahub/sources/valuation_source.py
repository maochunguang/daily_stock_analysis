"""Index valuation history from 乐咕乐股 (Legulegu).

The free endpoint exposes weekly history (``freq=week``); daily history is a
paid feature.  A weekly series is enough for 1/3/5-year percentile ranks and
keeps the request count low.

Field mapping (the site labels ``add*`` as the cap-weighted series):

============ ==============================
``addTtmPe`` weighted rolling PE (used)
``ttmPe``    equal-weight rolling PE
``addLyrPe`` weighted static PE
``middleTtmPe`` constituent median rolling PE
============ ==============================

The endpoint needs a short-lived cookie from a normal page and a token equal
to ``md5(Beijing date)``.  Neither is a user credential.  Parse failures and
upstream rate limits surface as ``SourceUnavailable`` so the scheduler keeps
the previous good series instead of replacing it with truncated data.
"""

from __future__ import annotations

import hashlib
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from ..models import IndexValuation
from .base import SourceUnavailable

API_URL = "https://legulegu.com/api/stockdata/index-basic-pe"
COOKIE_PAGE = "https://legulegu.com/stockdata/hs300-ttm-lyr"

#: Indexes shown in the deep-review valuation card, in display order.
INDEX_VALUATION_TARGETS: tuple[tuple[str, str], ...] = (
    ("000300.SH", "沪深300"),
    ("399006.SZ", "创业板指"),
    ("399673.SZ", "创业板50"),
    ("000688.SH", "科创50"),
)
INDEX_VALUATION_NAMES = dict(INDEX_VALUATION_TARGETS)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _beijing_today() -> date:
    """Beijing date without relying on system tzdata (slim images)."""

    return (datetime.now(timezone.utc) + timedelta(hours=8)).date()


def parse_legulegu_payload(
    payload: Any,
    *,
    code: str,
    name: str = "",
    source: str = "legulegu",
) -> list[IndexValuation]:
    """Parse one API payload into ordered, validated observations."""

    if isinstance(payload, dict):
        raw_rows = payload.get("data")
    else:
        raw_rows = payload
    if not isinstance(raw_rows, list):
        raise SourceUnavailable(f"legulegu: unexpected payload for {code}")

    rows: list[IndexValuation] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        text = str(item.get("date") or "")[:10]
        try:
            trade_date = date.fromisoformat(text)
        except ValueError:
            continue
        pe_ttm = _to_float(item.get("addTtmPe"))
        if pe_ttm is None or pe_ttm <= 0:
            # Keep the series usable even if an older row only has the
            # equal-weight field; don't mix the two semantics, though.
            continue
        rows.append(
            IndexValuation(
                code=code,
                trade_date=trade_date,
                name=name or INDEX_VALUATION_NAMES.get(code, code),
                pe_ttm=pe_ttm,
                pe_ttm_equal=_to_float(item.get("ttmPe")),
                pe_static=_to_float(item.get("addLyrPe")),
                pe_ttm_median=_to_float(item.get("middleTtmPe")),
                close=_to_float(item.get("close")),
                source=source,
            )
        )
    rows.sort(key=lambda row: row.trade_date)
    return rows


def keep_week_latest(rows: Iterable[IndexValuation]) -> list[IndexValuation]:
    """Keep one observation per ISO week (the latest date in that week).

    The API returns a fresh point for the current day while the rest of the
    series is weekly.  Persisting every daily update would over-weight the
    latest week in percentile calculations, so collapse to one point.
    """

    buckets: dict[tuple[int, int], IndexValuation] = {}
    for row in rows:
        iso = row.trade_date.isocalendar()
        key = (iso[0], iso[1])
        current = buckets.get(key)
        if current is None or row.trade_date > current.trade_date:
            buckets[key] = row
    return sorted(buckets.values(), key=lambda row: row.trade_date)


class LeguleguValuationSource:
    """Fetch weekly PE history for the configured broad-based indexes."""

    name = "legulegu"

    def __init__(
        self,
        session: Any | None = None,
        *,
        timeout: float = 30.0,
        min_interval: float = 1.0,
    ):
        self._session = session
        self._page_loaded = False
        self._calls = 0
        self.timeout = timeout
        self.min_interval = min_interval

    def _get_session(self) -> Any:
        if self._session is None:
            try:
                import requests
            except ImportError as exc:  # pragma: no cover - image has requests
                raise SourceUnavailable("requests is not installed") from exc
            self._session = requests.Session()
            self._session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120 Safari/537.36"
                    ),
                    "Referer": COOKIE_PAGE,
                }
            )
        if not self._page_loaded:
            try:
                response = self._session.get(COOKIE_PAGE, timeout=self.timeout)
            except Exception as exc:  # noqa: BLE001 - normalize transport errors
                raise SourceUnavailable(f"legulegu page unavailable: {exc}") from exc
            if response.status_code >= 400:
                raise SourceUnavailable(
                    f"legulegu page HTTP {response.status_code}"
                )
            self._page_loaded = True
        return self._session

    def fetch_index_valuation(self, code: str) -> list[IndexValuation]:
        if code not in INDEX_VALUATION_NAMES:
            raise SourceUnavailable(f"unsupported index valuation code: {code}")
        session = self._get_session()
        if self._calls:
            time.sleep(self.min_interval)
        self._calls += 1

        token = hashlib.md5(_beijing_today().isoformat().encode("ascii")).hexdigest()
        params = {"token": token, "indexCode": code, "freq": "week"}
        response = None
        for attempt in range(2):
            try:
                response = session.get(API_URL, params=params, timeout=self.timeout)
            except Exception as exc:  # noqa: BLE001 - normalize transport errors
                raise SourceUnavailable(f"legulegu request failed: {exc}") from exc
            if response.status_code == 429 and attempt == 0:
                time.sleep(3.0)
                continue
            break
        assert response is not None
        if response.status_code == 429:
            raise SourceUnavailable("legulegu rate limited (HTTP 429)")
        if response.status_code >= 400:
            raise SourceUnavailable(
                f"legulegu HTTP {response.status_code} for {code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceUnavailable(f"legulegu returned invalid JSON for {code}") from exc
        rows = parse_legulegu_payload(
            payload,
            code=code,
            name=INDEX_VALUATION_NAMES[code],
            source=self.name,
        )
        if not rows:
            raise SourceUnavailable(f"legulegu returned no PE history for {code}")
        return rows

    def fetch_index_valuations(
        self, codes: Sequence[str] = tuple(INDEX_VALUATION_NAMES)
    ) -> list[IndexValuation]:
        rows: list[IndexValuation] = []
        for code in codes:
            rows.extend(self.fetch_index_valuation(code))
        return rows
