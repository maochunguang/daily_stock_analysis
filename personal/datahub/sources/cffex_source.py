"""CFFEX top-20 member position rank adapter (official CSV, stdlib HTTP).

中金所每日收市后公布各合约前 20 会员成交/持仓排名（GBK CSV）：

    http://www.cffex.com.cn/sj/ccpm/{YYYYMM}/{DD}/{IF|IH|IC|IM}_1.csv

文件为「交易日,合约,排名,成交量排名…持买单量排名…持卖单量排名」三段结构，
每合约 20 行。汇总口径：对产品内**全部列出的合约**累加前 20 会员的
持买单量/持卖单量，净空头 = 持卖 − 持买，净空占比 = 净 / (买+卖)。
"""

from __future__ import annotations

import csv
import io
import time
import urllib.request
from datetime import date

from ..models import FuturesRank
from .base import SourceUnavailable

CFFEX_RANK_URL = "http://www.cffex.com.cn/sj/ccpm/{month}/{day}/{symbol}_1.csv"
_HEADERS = {
    "Referer": "http://www.cffex.com.cn/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}
SYMBOLS: tuple[str, ...] = ("IF", "IH", "IC", "IM")


class CffexRankSource:
    name = "cffex_rank"

    def fetch_rank_summary(self, start: date, end: date) -> list[FuturesRank]:
        rows: list[FuturesRank] = []
        day = start
        while day <= end:
            for symbol in SYMBOLS:
                summary = self._fetch_symbol(symbol, day)
                if summary is not None:
                    rows.append(summary)
                time.sleep(0.2)  # 中金所接口礼貌节流
            day = date.fromordinal(day.toordinal() + 1)
        return rows

    def _fetch_symbol(self, symbol: str, day: date) -> FuturesRank | None:
        url = CFFEX_RANK_URL.format(
            month=day.strftime("%Y%m"), day=day.strftime("%d"), symbol=symbol
        )
        request = urllib.request.Request(url, headers=_HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read().decode("gbk", errors="ignore")
        except Exception:
            return None
        lines = raw.strip().splitlines()
        if len(lines) < 3:
            return None
        contracts: set[str] = set()
        buy_total = 0.0
        sell_total = 0.0
        for record in csv.reader(io.StringIO("\n".join(lines[2:]))):
            if len(record) < 11 or not record[1]:
                continue
            contracts.add(record[1])
            try:
                buy_total += float(record[7] or 0)
                sell_total += float(record[10] or 0)
            except ValueError:
                continue
        if buy_total + sell_total <= 0:
            return None
        net = sell_total - buy_total
        return FuturesRank(
            trade_date=day,
            symbol=symbol,
            contracts=len(contracts),
            top20_buy=round(buy_total, 0),
            top20_sell=round(sell_total, 0),
            net=round(net, 0),
            net_ratio=round(net / (buy_total + sell_total), 4),
        )
