"""BaoStock daily bar adapter (free source, optional dependency)."""

from __future__ import annotations

from datetime import date

from ..models import DailyBar
from ..normalize import normalize_code, parse_date
from .base import SourceUnavailable


class BaostockSource:
    name = "baostock"

    def _bs(self):
        try:
            import baostock as bs
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SourceUnavailable("baostock is not installed") from exc
        return bs

    def fetch_daily_bars(self, code: str, start: date, end: date) -> list[DailyBar]:
        bs = self._bs()
        full = normalize_code(code)
        body, suffix = full.split(".")
        exchange = "sh" if suffix == "SH" else "sz"
        if suffix == "BJ":
            raise SourceUnavailable("BaoStock does not support Beijing Stock Exchange")
        bs_code = f"{exchange}.{body}"
        login = bs.login()
        if getattr(login, "error_code", "0") != "0":
            raise SourceUnavailable(f"BaoStock login failed: {login.error_msg}")
        try:
            result = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount",
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                frequency="d",
                adjustflag="3",  # unadjusted; personal layer applies factors
            )
            if result is None or result.error_code != "0":
                return []
            rows: list[DailyBar] = []
            while result.next():
                values = result.get_row_data()
                rows.append(
                    DailyBar(
                        code=full,
                        trade_date=parse_date(values[0]),
                        open=float(values[1]),
                        high=float(values[2]),
                        low=float(values[3]),
                        close=float(values[4]),
                        volume=float(values[5]),
                        amount=float(values[6]),
                        source=self.name,
                    )
                )
            return rows
        finally:
            bs.logout()
