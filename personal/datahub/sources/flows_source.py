"""Fund-flow adapters: exchange turnover, broad ETF shares, sector crowding.

- 成交概况：上交所每日成交概况（`stock_deal_daily_sse`，akshare 1.20.44 前为
  `stock_sse_deal_daily`）取「成交金额-股票」行；深交所 `stock_summary_szse`
  （旧名 `stock_szse_summary`）取证券类别=股票 行。两融交易占比的分母。
- ETF 份额：东财 ETF 快照（`fund_etf_spot_em`）对固定宽基名单做每日快照，
  份额序列需自行累积（无历史 API），增减 = 申赎近似。
- 行业拥挤度：同花顺行业一览（`stock_board_industry_summary_ths`，90 个行业，
  含总成交额），份额 = 板块成交额 / 全部板块之和；历史分位随积累变可靠。
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from urllib.parse import urlencode

from ..models import EtfShare, MarketTurnover, SectorAmount
from .base import SourceUnavailable

#: 宽基 ETF 份额观察名单（code, 简称）
BROAD_ETFS: tuple[tuple[str, str], ...] = (
    ("510050", "上证50"),
    ("510300", "沪深300"),
    ("510500", "中证500"),
    ("512100", "中证1000"),
    ("159915", "创业板"),
    ("588000", "科创50"),
    ("159949", "创业板50"),
)


def _first_attr(ak, *names):
    for name in names:
        fetch = getattr(ak, name, None)
        if fetch is not None:
            return fetch
    raise SourceUnavailable(f"akshare has none of {names}")


def _to_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


class TurnoverSource:
    name = "exchange_turnover"

    def _ak(self):
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover
            raise SourceUnavailable("akshare is not installed") from exc
        return ak

    def fetch_turnover(self, start: date, end: date) -> list[MarketTurnover]:
        ak = self._ak()
        sse_amounts = self._sse_amounts(ak, start, end)
        szse_amounts = self._szse_amounts(ak, start, end)
        rows: list[MarketTurnover] = []
        day = start
        while day <= end:
            sse = sse_amounts.get(day)
            szse = szse_amounts.get(day)
            if sse is not None and szse is not None:
                rows.append(MarketTurnover(trade_date=day, sse_amount=sse, szse_amount=szse))
            time.sleep(0.2)  # 交易所接口礼貌节流
            day = date.fromordinal(day.toordinal() + 1)
        return rows

    def _sse_amounts(self, ak, start: date, end: date) -> dict[date, float]:
        """上交所每日成交概况（按日快照，成交金额单位亿元）。"""
        out: dict[date, float] = {}
        fetch = _first_attr(ak, "stock_deal_daily_sse", "stock_sse_deal_daily")
        day = start
        while day <= end:
            try:
                frame = fetch(date=day.strftime("%Y%m%d"))
            except Exception:
                day = date.fromordinal(day.toordinal() + 1)
                continue
            if frame is not None and not frame.empty:
                row = frame[frame["单日情况"] == "成交金额"]
                if not row.empty:
                    amount = _to_float(row.iloc[0].get("股票"))
                    if amount is not None:
                        out[day] = amount * 1e8
            day = date.fromordinal(day.toordinal() + 1)
        return out

    def _szse_amounts(self, ak, start: date, end: date) -> dict[date, float]:
        out: dict[date, float] = {}
        fetch = _first_attr(ak, "stock_summary_szse", "stock_szse_summary")
        day = start
        while day <= end:
            try:
                frame = fetch(date=day.strftime("%Y%m%d"))
            except Exception:
                day = date.fromordinal(day.toordinal() + 1)
                continue
            if frame is not None and not frame.empty:
                match = frame[frame["证券类别"] == "股票"]
                if not match.empty:
                    amount = _to_float(match.iloc[0].get("成交金额"))
                    if amount is not None:
                        out[day] = amount
            time.sleep(0.2)  # 交易所接口礼貌节流
            day = date.fromordinal(day.toordinal() + 1)
        return out

    @staticmethod
    def _parse_day(value) -> date | None:
        text = str(value).strip()
        digits = "".join(ch for ch in text if ch.isdigit())[:8]
        if len(digits) == 8:
            try:
                return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
            except ValueError:
                return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


class EtfShareSource:
    name = "em_etf_share"

    def _ak(self):
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover
            raise SourceUnavailable("akshare is not installed") from exc
        return ak

    def fetch_etf_share(self, trade_date: date) -> list[EtfShare]:
        """Broad-ETF shares in 亿份.

        Primary path is the Eastmoney list API (all ETFs in one paginated pull).
        That endpoint can reject/close long paginations (observed as
        ``RemoteDisconnected``); the fallback asks the single-security quote API
        for ``f84`` (总股本/基金份额) per ETF — 7 small requests instead of all
        pages, and it kept working while the list endpoint was blocked.
        """
        try:
            ak = self._ak()
            fetch = _first_attr(ak, "fund_etf_spot_em", "fund_etf_hist_em")
            if fetch.__name__ != "fund_etf_spot_em":
                raise SourceUnavailable("fund_etf_spot_em unavailable")
            frame = fetch()
            rows = self._from_frame(frame, trade_date)
        except Exception:  # noqa: BLE001 - fall back to per-symbol quotes
            rows = []
        if rows:
            return rows
        return self._from_quotes(trade_date)

    def _from_frame(self, frame, trade_date: date) -> list[EtfShare]:
        if frame is None or frame.empty:
            return []
        wanted = {code: label for code, label in BROAD_ETFS}
        rows: list[EtfShare] = []
        for _, row in frame.iterrows():
            code = str(row.get("代码") or "").strip()
            if code not in wanted:
                continue
            share = _to_float(row.get("最新份额"))
            # 东财「最新份额」单位是份，模型/卡片统一用亿份
            share_yi = round(share / 1e8, 2) if share is not None else None
            rows.append(
                EtfShare(
                    trade_date=trade_date,
                    code=code,
                    name=wanted[code],
                    share_yi=share_yi,
                )
            )
        return rows

    def _from_quotes(self, trade_date: date) -> list[EtfShare]:
        rows: list[EtfShare] = []
        for code, label in BROAD_ETFS:
            share = self._quote_share(code)
            if share:
                rows.append(
                    EtfShare(
                        trade_date=trade_date,
                        code=code,
                        name=label,
                        share_yi=round(share / 1e8, 2),
                    )
                )
            time.sleep(0.2)  # 逐只请求，保持礼貌
        return rows

    def _quote_share(self, code: str) -> float | None:
        market = "1" if code.startswith(("5", "6", "9")) else "0"
        params = urlencode(
            {
                "secid": f"{market}.{code}",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fields": "f58,f84,f85",
                "invt": "2",
                "fltt": "2",
            }
        )
        request = urllib.request.Request(
            f"https://push2.eastmoney.com/api/qt/stock/get?{params}",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                ),
                "Referer": "https://quote.eastmoney.com/",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - one retry, then give up on this symbol
            time.sleep(0.5)
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception:  # noqa: BLE001
                return None
        data = payload.get("data") or {}
        return _to_float(data.get("f84")) or _to_float(data.get("f85"))


class SectorSource:
    name = "ths_sector_amount"

    def _ak(self):
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover
            raise SourceUnavailable("akshare is not installed") from exc
        return ak

    def fetch_sector_amounts(self, trade_date: date) -> list[SectorAmount]:
        ak = self._ak()
        frame = ak.stock_board_industry_summary_ths()
        if frame is None or frame.empty:
            return []
        amounts: list[tuple[str, float | None, float | None]] = []
        for _, row in frame.iterrows():
            board = str(row.get("板块") or "").strip()
            if not board:
                continue
            amounts.append(
                (
                    board,
                    _to_float(row.get("总成交额")),
                    _to_float(row.get("涨跌幅")),
                )
            )
        total = sum(a for _, a, _ in amounts if a is not None)
        rows: list[SectorAmount] = []
        for board, amount, pct_chg in amounts:
            share = (
                round(amount / total * 100, 3)
                if amount is not None and total > 0
                else None
            )
            rows.append(
                SectorAmount(
                    trade_date=trade_date,
                    board=board,
                    amount_yi=amount,
                    share_pct=share,
                    pct_chg=pct_chg,
                )
            )
        return rows
