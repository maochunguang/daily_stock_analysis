"""Exchange margin-financing (两融) adapter — summaries + per-board splits.

数据源（上交所/深交所官方公开接口，经 AkShare 或直接 HTTP）：

- 沪市汇总 ``stock_margin_sse(start, end)``：单位元，含 ETF/债券标的
- 深市汇总 ``stock_margin_szse(date)``：单位亿元，含可转债标的
- 深市明细 ``stock_margin_detail_szse(date)``：个股融资余额（元），用于板块拆分
- 沪市明细 ``queryMargin.do``：单页上限 2000 行，必须翻页（``pageHelp.pageNo``），
  这里直接走原始 HTTP 并按 ``pageHelp.pageCount`` 收齐

板块口径（仅股票标的，ETF/债券/可转债不计入板块行）：

- 沪主板 600/601/603/605，科创板 688/689
- 深主板 000/001/002/003，创业板 300/301/302
- ``market`` 行 = 官方汇总（含基金/债券标的）；``board`` 行 = 股票明细聚合，
  两者口径不同、数值不可直接相加。总计 = 沪市汇总 + 深市汇总。

两融数据 T+1 发布：D 日收盘数据次日早上才能拉到。
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date
from typing import Sequence

from ..models import MarginBalance, MarginStockRow
from .base import SourceUnavailable

SSE_DETAIL_URL = "https://query.sse.com.cn/marketdata/tradedata/queryMargin.do"
_SSE_HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}
_SSE_PAGE_SIZE = 2000

#: (scope, 判定函数)；顺序即优先级，先命中先归类
SSE_BOARDS: tuple[tuple[str, object], ...] = (
    ("科创板", lambda code: code.startswith(("688", "689"))),
    ("沪主板", lambda code: code.startswith(("600", "601", "603", "605"))),
)
SZSE_BOARDS: tuple[tuple[str, object], ...] = (
    ("创业板", lambda code: code.startswith(("300", "301", "302"))),
    ("深主板", lambda code: code.startswith(("000", "001", "002", "003"))),
)


def classify_board(code: str) -> str | None:
    """股票代码 -> 板块名；非股票标的（ETF/债券/可转债等）返回 None。"""
    code = (code or "").strip()
    if code.startswith("6") and len(code) == 6:
        for name, match in SSE_BOARDS:
            if match(code):
                return name
        return None
    for name, match in SZSE_BOARDS:
        if match(code):
            return name
    return None


class MarginSource:
    name = "exchange_margin"

    def _ak(self):
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SourceUnavailable("akshare is not installed") from exc
        return ak

    def fetch_margin_balance(self, start: date, end: date) -> list[MarginBalance]:
        rows, _ = self.fetch_margin_all(start, end, ())
        return rows

    def fetch_margin_all(
        self, start: date, end: date, stock_codes: Sequence[str] = ()
    ) -> tuple[list[MarginBalance], list[MarginStockRow]]:
        """Market/board rows plus per-stock rows for ``stock_codes``.

        持仓股两融（RM-42）：明细本来只聚合成板块就丢弃，这里按代码留档，
        与市场行共用同一次逐日请求，不额外增加交易所调用。
        """
        ak = self._ak()
        rows: list[MarginBalance] = []
        stock_rows: list[MarginStockRow] = []
        wanted = {code.strip() for code in stock_codes if code and code.strip()}

        sse_summary = self._sse_summary(ak, start, end)

        # 交易日锚点：优先用沪市汇总返回的日期（一次区间请求），
        # 汇总失败时退回逐日历日探测（交易所接口对非交易日返回空）。
        days = sorted(sse_summary) or list(_date_range(start, end))

        for day in days:
            date_text = day.strftime("%Y%m%d")
            has_any = False
            board_rows: list[MarginBalance] = []

            # 沪市板块（股票明细聚合，翻页收齐）
            detail = self._sse_detail(date_text)
            if detail:
                has_any = True
                sums = _sum_by_board(detail)
                for scope, values in sums.items():
                    board_rows.append(
                        MarginBalance(
                            trade_date=day,
                            scope_type="board",
                            scope=scope,
                            rzye=values.get("rzye"),
                            rzye_buy=values.get("rzye_buy"),
                            source=self.name,
                        )
                    )

            # 深市板块
            szse_detail = self._szse_detail(ak, date_text)
            if szse_detail is not None:
                has_any = True
                for scope, values in _sum_szse_detail(szse_detail).items():
                    board_rows.append(
                        MarginBalance(
                            trade_date=day,
                            scope_type="board",
                            scope=scope,
                            rzye=values.get("rzye"),
                            rqye=values.get("rqye"),
                            rzye_buy=values.get("rzye_buy"),
                            source=self.name,
                        )
                    )

            if wanted:
                stock_rows.extend(_stock_rows_sse(detail or [], day, wanted, self.name))
                if szse_detail is not None:
                    stock_rows.extend(
                        _stock_rows_szse(szse_detail, day, wanted, self.name)
                    )

            if not has_any:
                continue

            # 沪/深 market 行（官方汇总口径）
            sse_row = sse_summary.get(day)
            if sse_row is not None:
                rows.append(
                    MarginBalance(
                        trade_date=day,
                        scope_type="market",
                        scope="沪市",
                        rzye=sse_row.get("rzye"),
                        rqye=sse_row.get("rqye"),
                        rzrqye=sse_row.get("rzrqye"),
                        rzye_buy=sse_row.get("rzye_buy"),
                        source=self.name,
                    )
                )
            szse_row = self._szse_summary(ak, date_text)
            if szse_row is not None:
                rows.append(
                    MarginBalance(
                        trade_date=day,
                        scope_type="market",
                        scope="深市",
                        rzye=szse_row.get("rzye"),
                        rqye=szse_row.get("rqye"),
                        rzrqye=szse_row.get("rzrqye"),
                        rzye_buy=szse_row.get("rzye_buy"),
                        source=self.name,
                    )
                )
            if sse_row is not None and szse_row is not None:
                rows.append(_total_row(day, sse_row, szse_row, self.name))
            rows.extend(board_rows)
            # 两融明细按日轮询（SSE 翻页 + 深市两接口），礼貌节流
            time.sleep(0.3)
        return rows, stock_rows

    # ------------------------------------------------------------------
    # SSE
    # ------------------------------------------------------------------
    def _sse_summary(
        self, ak, start: date, end: date
    ) -> dict[date, dict[str, float]]:
        """沪市官方汇总（元），一次区间请求。"""
        try:
            frame = ak.stock_margin_sse(
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
        except Exception:
            return {}
        out: dict[date, dict[str, float]] = {}
        if frame is None or frame.empty:
            return out
        for _, row in frame.iterrows():
            day = _parse_day(str(row.get("信用交易日期")))
            if day is None:
                continue
            out[day] = {
                "rzye": _to_float(row.get("融资余额")),
                "rqye": _to_float(row.get("融券余量金额")),
                "rzrqye": _to_float(row.get("融资融券余额")),
                "rzye_buy": _to_float(row.get("融资买入额")),
            }
        return out

    def _sse_detail(self, date_text: str) -> list[dict]:
        """沪市个股/基金明细（翻页收齐，原始 HTTP）。"""
        rows: list[dict] = []
        page = 1
        total_pages = 1
        while page <= max(total_pages, 1) and page <= 50:
            params = {
                "isPagination": "true",
                "tabType": "mxtype",
                "detailsDate": date_text,
                "stockCode": "",
                "beginDate": "",
                "endDate": "",
                "pageHelp.pageSize": str(_SSE_PAGE_SIZE),
                "pageHelp.pageCount": "50",
                "pageHelp.pageNo": str(page),
                "pageHelp.beginPage": str(page),
                "pageHelp.cacheSize": "1",
                "pageHelp.endPage": "21",
            }
            url = f"{SSE_DETAIL_URL}?{urllib.parse.urlencode(params)}"
            try:
                request = urllib.request.Request(url, headers=_SSE_HEADERS)
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            except Exception:
                break
            help_meta = payload.get("pageHelp") or {}
            total = _to_int(help_meta.get("total"))
            if total is not None and _SSE_PAGE_SIZE:
                total_pages = max(1, -(-total // _SSE_PAGE_SIZE))
            page_rows = payload.get("result") or []
            if not page_rows:
                break
            rows.extend(page_rows)
            if page >= total_pages:
                break
            page += 1
            time.sleep(0.3)
        return rows

    # ------------------------------------------------------------------
    # SZSE
    # ------------------------------------------------------------------
    def _szse_summary(self, ak, date_text: str) -> dict[str, float] | None:
        try:
            frame = ak.stock_margin_szse(date=date_text)
        except Exception:
            return None
        if frame is None or frame.empty:
            return None
        row = frame.iloc[0].to_dict()
        return {
            # 深交所汇总口径单位是亿元，统一换算成元
            "rzye": _yi_to_yuan(row.get("融资余额")),
            "rqye": _yi_to_yuan(row.get("融券余额")),
            "rzrqye": _yi_to_yuan(row.get("融资融券余额")),
            "rzye_buy": _yi_to_yuan(row.get("融资买入额")),
        }

    def _szse_detail(self, ak, date_text: str):
        try:
            frame = ak.stock_margin_detail_szse(date=date_text)
        except Exception:
            return None
        if frame is None or frame.empty:
            return None
        return frame


def _stock_rows_sse(
    detail: list[dict], day: date, wanted: set[str], source: str
) -> list[MarginStockRow]:
    rows: list[MarginStockRow] = []
    for row in detail:
        code = str(row.get("stockCode") or "").strip()
        if code not in wanted:
            continue
        rows.append(
            MarginStockRow(
                trade_date=day,
                code=code,
                name=str(
                    row.get("stockName") or row.get("securityAbbr") or ""
                ).strip(),
                rzye=_to_float(row.get("rzye")),
                rzye_buy=_to_float(row.get("rzmre")),
                rqye=_to_float(row.get("rqye")),
                source=source,
            )
        )
    return rows


def _stock_rows_szse(
    frame, day: date, wanted: set[str], source: str
) -> list[MarginStockRow]:
    rows: list[MarginStockRow] = []
    for _, row in frame.iterrows():
        code = str(row.get("证券代码") or "").strip()
        if code not in wanted:
            continue
        rows.append(
            MarginStockRow(
                trade_date=day,
                code=code,
                name=str(row.get("证券简称") or "").strip(),
                rzye=_to_float(row.get("融资余额")),
                rzye_buy=_to_float(row.get("融资买入额")),
                rqye=_to_float(row.get("融券余额")),
                source=source,
            )
        )
    return rows


def _sum_by_board(rows: list[dict]) -> dict[str, dict[str, float]]:
    """SSE 明细行（dict 键）按板块聚合（仅股票标的）。"""
    sums: dict[str, dict[str, float]] = {}
    for row in rows:
        code = str(row.get("stockCode") or "").strip()
        scope = classify_board(code)
        if scope is None:
            continue
        bucket = sums.setdefault(scope, {"rzye": 0.0, "rzye_buy": 0.0})
        bucket["rzye"] += _to_float(row.get("rzye")) or 0.0
        bucket["rzye_buy"] += _to_float(row.get("rzmre")) or 0.0
    return sums


def _sum_szse_detail(frame) -> dict[str, dict[str, float]]:
    sums: dict[str, dict[str, float]] = {}
    for _, row in frame.iterrows():
        code = str(row.get("证券代码") or "").strip()
        scope = classify_board(code)
        if scope is None:
            continue
        bucket = sums.setdefault(scope, {"rzye": 0.0, "rqye": 0.0, "rzye_buy": 0.0})
        bucket["rzye"] += _to_float(row.get("融资余额")) or 0.0
        bucket["rqye"] += _to_float(row.get("融券余额")) or 0.0
        bucket["rzye_buy"] += _to_float(row.get("融资买入额")) or 0.0
    return sums


def _total_row(day: date, sse: dict[str, float], szse: dict[str, float], source: str):
    def _sum(key: str) -> float | None:
        left, right = sse.get(key), szse.get(key)
        if left is None or right is None:
            return None
        return left + right

    return MarginBalance(
        trade_date=day,
        scope_type="market",
        scope="总计",
        rzye=_sum("rzye"),
        rqye=_sum("rqye"),
        rzrqye=_sum("rzrqye"),
        rzye_buy=_sum("rzye_buy"),
        source=source,
    )


def _yi_to_yuan(value) -> float | None:
    number = _to_float(value)
    return None if number is None else number * 1e8


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    number = _to_float(value)
    return None if number is None else int(number)


def _parse_day(text: str) -> date | None:
    digits = "".join(ch for ch in text if ch.isdigit())[:8]
    if len(digits) != 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def _date_range(start: date, end: date):
    day = start
    step = (end - start).days
    if step < 0:
        return
    for offset in range(step + 1):
        yield day
        day = date.fromordinal(day.toordinal() + 1)
