"""Tushare Pro adapter using the raw HTTP API.

Using the raw API avoids the heavy ``tushare`` SDK (and its lxml dependency).
Only the standard library is required; the token is read from configuration.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date
from typing import Any

from ..models import AdjustFactor, DailyBar
from ..normalize import is_etf_code, normalize_code, parse_date
from .base import SourceUnavailable

API_URL = "http://api.tushare.pro"


class TushareSource:
    name = "tushare"

    def __init__(
        self,
        token: str,
        timeout: float = 30.0,
        *,
        retry_on_rate_limit: bool = True,
        rate_limit_sleep: float = 61.0,
    ):
        self.token = token.strip()
        self.timeout = timeout
        self.retry_on_rate_limit = retry_on_rate_limit
        self.rate_limit_sleep = rate_limit_sleep

    def _call(
        self,
        api_name: str,
        params: dict[str, Any],
        fields: str = "",
        *,
        _retried: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.token:
            raise SourceUnavailable("TUSHARE_TOKEN is not configured")
        payload = json.dumps(
            {
                "api_name": api_name,
                "token": self.token,
                "params": params,
                "fields": fields,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            API_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise SourceUnavailable(f"Tushare request failed: {exc}") from exc

        code = result.get("code")
        if code != 0:
            message = str(result.get("msg") or "")
            if "小时" in message:
                raise SourceUnavailable(
                    f"Tushare {api_name} hourly rate limit reached: {message}"
                )
            if (
                self.retry_on_rate_limit
                and not _retried
                and "分钟" in message
            ):
                time.sleep(self.rate_limit_sleep)
                return self._call(api_name, params, fields, _retried=True)
            raise SourceUnavailable(
                f"Tushare {api_name} error {code}: {message}"
            )
        data = result.get("data") or {}
        field_names = data.get("fields") or []
        items = data.get("items") or []
        return [dict(zip(field_names, item)) for item in items]

    def fetch_daily_bars(self, code: str, start: date, end: date) -> list[DailyBar]:
        full = normalize_code(code)
        body, suffix = full.split(".")
        api_name = "fund_daily" if is_etf_code(full) else "daily"
        rows = self._call(
            api_name,
            {
                "ts_code": f"{body}.{suffix}",
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
        )
        bars: list[DailyBar] = []
        for row in sorted(rows, key=lambda item: item["trade_date"]):
            bars.append(
                DailyBar(
                    code=full,
                    trade_date=parse_date(row["trade_date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("vol") or 0.0) * 100.0,
                    amount=float(row.get("amount") or 0.0) * 1000.0,
                    source=self.name,
                )
            )
        return bars

    def fetch_adjust_factors(
        self, code: str, start: date, end: date
    ) -> list[AdjustFactor]:
        full = normalize_code(code)
        body, suffix = full.split(".")
        rows = self._call(
            "adj_factor",
            {
                "ts_code": f"{body}.{suffix}",
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
        )
        return [
            AdjustFactor(
                code=full,
                ex_date=parse_date(row["trade_date"]),
                factor=float(row["adj_factor"]),
                reason="",
                source=self.name,
            )
            for row in sorted(rows, key=lambda item: item["trade_date"])
        ]

    def fetch_trade_calendar(self, start: date, end: date) -> list[date]:
        rows = self._call(
            "trade_cal",
            {
                "exchange": "SSE",
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
            "cal_date,is_open",
        )
        return [
            parse_date(row["cal_date"])
            for row in rows
            if str(row.get("is_open")) == "1"
        ]

    def fetch_index_dailybasic(
        self, code: str, start: date, end: date
    ) -> list[dict[str, Any]]:
        """Raw ``index_dailybasic`` rows (needs a 2000-point token)."""

        return self._call(
            "index_dailybasic",
            {
                "ts_code": normalize_code(code),
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
            "ts_code,trade_date,close,pe,pe_ttm",
        )

    def fetch_margin_summary(self, start: date, end: date) -> list[dict[str, Any]]:
        """Raw ``margin`` rows (exchange-level margin summary, yuan)."""

        return self._call(
            "margin",
            {
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
        )

    def fetch_margin_detail(
        self, code: str, start: date, end: date
    ) -> list[dict[str, Any]]:
        """Raw ``margin_detail`` rows for one instrument (yuan)."""

        return self._call(
            "margin_detail",
            {
                "ts_code": normalize_code(code),
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
        )

    def fetch_fut_mapping(
        self, continuous_code: str, start: date, end: date
    ) -> list[dict[str, Any]]:
        """Raw ``fut_mapping`` rows (main-contract map for e.g. ``IF.CFX``)."""

        return self._call(
            "fut_mapping",
            {
                "ts_code": continuous_code,
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
        )

    def fetch_fut_daily(
        self, code: str, start: date, end: date
    ) -> list[dict[str, Any]]:
        """Raw ``fut_daily`` rows for one contract (CFFEX: ``*.CFX``)."""

        return self._call(
            "fut_daily",
            {
                "ts_code": code,
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
        )

    def fetch_index_daily(
        self, code: str, start: date, end: date
    ) -> list[dict[str, Any]]:
        """Raw ``index_daily`` rows (spot index bars for basis math)."""

        return self._call(
            "index_daily",
            {
                "ts_code": normalize_code(code),
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
            "ts_code,trade_date,close,pre_close,amount",
        )

    def fetch_daily_by_date(self, trade_date: date) -> list[dict[str, Any]]:
        """All stocks for one session via ``daily`` (~5.5k rows)."""

        return self._call(
            "daily",
            {"trade_date": trade_date.strftime("%Y%m%d")},
            "ts_code,trade_date,close,pre_close,change,vol,amount",
        )

    def fetch_stock_name_map(self) -> dict[str, str]:
        """``ts_code -> name`` for the whole market via ``stock_basic``."""

        rows = self._call("stock_basic", {}, "ts_code,name")
        return {
            str(row.get("ts_code")): str(row.get("name") or "").strip()
            for row in rows
        }

    def fetch_share_float(self, start: date, end: date) -> list[dict[str, Any]]:
        """Raw ``share_float`` rows in a float-date window (shares in 股)."""

        return self._call(
            "share_float",
            {
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
        )

    def fetch_daily_close_map(self, trade_date: date) -> dict[str, float]:
        """``code -> close`` for one session via ``daily`` (whole market)."""

        rows = self._call(
            "daily",
            {"trade_date": trade_date.strftime("%Y%m%d")},
            "ts_code,close",
        )
        return {
            str(row.get("ts_code")): float(row["close"])
            for row in rows
            if row.get("close") is not None
        }

    def fetch_instrument_name(self, code: str) -> str:
        full = normalize_code(code)
        body, suffix = full.split(".")
        rows = self._call(
            "stock_basic",
            {"ts_code": f"{body}.{suffix}"},
            "ts_code,name",
        )
        if not rows:
            return ""
        return str(rows[0].get("name") or "").strip()
