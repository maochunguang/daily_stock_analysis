"""AkShare daily bar adapter (free source, optional dependency)."""

from __future__ import annotations

from datetime import date

from ..models import DailyBar
from ..normalize import is_etf_code, normalize_code, parse_date
from .base import SourceUnavailable


class AkshareSource:
    name = "akshare"

    def _ak(self):
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SourceUnavailable("akshare is not installed") from exc
        return ak

    def fetch_daily_bars(self, code: str, start: date, end: date) -> list[DailyBar]:
        ak = self._ak()
        full = normalize_code(code)
        body = full.split(".")[0]
        start_text = start.strftime("%Y%m%d")
        end_text = end.strftime("%Y%m%d")
        if is_etf_code(full):
            frame = ak.fund_etf_hist_em(
                symbol=body,
                period="daily",
                start_date=start_text,
                end_date=end_text,
                adjust="",
            )
        else:
            frame = ak.stock_zh_a_hist(
                symbol=body,
                period="daily",
                start_date=start_text,
                end_date=end_text,
                adjust="",
            )
        if frame is None or frame.empty:
            return []

        column_map = {
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
        }
        frame = frame.rename(columns=column_map)
        frame = frame.sort_values("date")
        bars: list[DailyBar] = []
        for _, row in frame.iterrows():
            bars.append(
                DailyBar(
                    code=full,
                    trade_date=parse_date(row["date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]) * 100.0,  # AkShare volume is in lots
                    amount=float(row["amount"]),
                    source=self.name,
                )
            )
        return bars
