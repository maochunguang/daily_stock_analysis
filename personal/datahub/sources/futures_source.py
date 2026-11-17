"""CFFEX index-futures adapter (main contracts via AkShare, optional).

做空压力口径：主力连续合约 IF0/IH0/IC0/IM0 收盘价对比对应现货指数收盘，
``basis = 期货收盘 - 现货收盘``，``basis_pct = basis / 现货 * 100``。
持续贴水（basis_pct 深度为负）= 对冲/做空压力大；升水转贴水拐点也值得注意。
持仓量（open interest）及其变化反映空头建仓/平仓力度。
"""

from __future__ import annotations

from datetime import date

from ..models import IndexFutures
from .base import SourceUnavailable

#: symbol -> (主力连续代码, 现货指数 sina 代码)
FUTURES_SPEC: dict[str, tuple[str, str]] = {
    "IF": ("IF0", "sh000300"),  # 沪深300
    "IH": ("IH0", "sh000016"),  # 上证50
    "IC": ("IC0", "sh000905"),  # 中证500
    "IM": ("IM0", "sh000852"),  # 中证1000
}


class FuturesSource:
    name = "akshare_futures"

    def _ak(self):
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SourceUnavailable("akshare is not installed") from exc
        return ak

    def fetch_index_futures(self, start: date, end: date) -> list[IndexFutures]:
        ak = self._ak()
        start_text = start.strftime("%Y%m%d")
        end_text = end.strftime("%Y%m%d")

        spot: dict[str, dict[date, float]] = {}
        rows: list[IndexFutures] = []
        for symbol, (contract, index_code) in FUTURES_SPEC.items():
            frame = ak.futures_main_sina(
                symbol=contract, start_date=start_text, end_date=end_text
            )
            if frame is None or frame.empty:
                continue
            if index_code not in spot:
                spot[index_code] = self._index_closes(ak, index_code, start, end)
            closes = spot[index_code]

            prev_oi: float | None = None
            for _, row in frame.sort_values("日期").iterrows():
                trade_date = _to_date(row.get("日期"))
                if trade_date is None:
                    continue
                close = _to_float(row.get("收盘价"))
                oi = _to_float(row.get("持仓量"))
                index_close = closes.get(trade_date)
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
                rows.append(
                    IndexFutures(
                        trade_date=trade_date,
                        symbol=symbol,
                        close=close,
                        volume=_to_float(row.get("成交量")),
                        open_interest=oi,
                        oi_chg=(
                            round(oi - prev_oi, 0)
                            if oi is not None and prev_oi is not None
                            else None
                        ),
                        index_close=index_close,
                        basis=basis,
                        basis_pct=basis_pct,
                        source=self.name,
                    )
                )
                prev_oi = oi
        return rows

    def _index_closes(
        self, ak, index_code: str, start: date, end: date
    ) -> dict[date, float]:
        """Spot index closes for one index (full history, filtered to range)."""
        closes: dict[date, float] = {}
        try:
            frame = ak.index_zh_daily_sina(symbol=index_code)
        except Exception:
            return closes
        if frame is None or frame.empty:
            return closes
        for _, row in frame.iterrows():
            day = _to_date(row.get("date"))
            if day is None or not (start <= day <= end):
                continue
            close = _to_float(row.get("close"))
            if close is not None:
                closes[day] = close
        return closes


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date(value) -> date | None:
    if value is None:
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
