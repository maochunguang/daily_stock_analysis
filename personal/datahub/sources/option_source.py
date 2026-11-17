"""ETF-option PCR adapter — SSE official daily statistics (free, per-day).

上交所官方「期权统计」（经 AkShare ``option_daily_stats_sse``）：按交易日返回
每个合约标的的认购/认沽成交量、未平仓合约数，**口径完整**（交易所聚合，
不是逐合约拉取），无第三方限频。

为什么不走 Tushare ``opt_daily``：免费档 opt_basic/opt_daily 都是 1 次/小时，
半年回填需要 5 天以上；官方统计一个接口一天一调用，回填半年只要几分钟。

PCR 口径：官方「认沽/认购」列是百分数（如 62.52），入库统一除以 100
（0.6252），与卡片/综合分的比值口径一致。持仓量 PCR 用未平仓合约数，
是全量口径（比 opt_daily 的有行情合约子集准确）。
"""

from __future__ import annotations

import time
from datetime import date

from ..models import OptionPcr
from .base import SourceUnavailable

#: 合约标的代码 -> personal 层 underlying 名
PCR_UNDERLYINGS: dict[str, str] = {
    "510050": "50ETF",
    "510300": "300ETF",
}


class OptionPcrSource:
    name = "sse_option_stats"

    def _ak(self):
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SourceUnavailable("akshare is not installed") from exc
        return ak

    def _stats(self, ak, date_text: str):
        fetch = getattr(ak, "option_daily_stats_sse", None) or getattr(
            ak, "option_sse_daily_stats", None
        )
        if fetch is None:
            raise SourceUnavailable("no SSE option daily statistics interface")
        try:
            return fetch(date=date_text)
        except TypeError:
            return fetch(date_text)

    def fetch_option_pcr(self, start: date, end: date) -> list[OptionPcr]:
        ak = self._ak()
        rows: list[OptionPcr] = []
        day = start
        while day <= end:
            try:
                frame = self._stats(ak, day.strftime("%Y%m%d"))
            except Exception:
                # 非交易日/接口抖动：跳过该日
                day = date.fromordinal(day.toordinal() + 1)
                time.sleep(0.3)
                continue
            if frame is not None and not frame.empty:
                for _, row in frame.iterrows():
                    code = str(row.get("合约标的代码") or "").strip()
                    underlying = PCR_UNDERLYINGS.get(code)
                    if underlying is None:
                        continue
                    call_vol = _f(row.get("认购成交量"))
                    put_vol = _f(row.get("认沽成交量"))
                    call_oi = _f(row.get("未平仓认购合约数"))
                    put_oi = _f(row.get("未平仓认沽合约数"))
                    rows.append(
                        OptionPcr(
                            trade_date=day,
                            underlying=underlying,
                            call_vol=call_vol,
                            put_vol=put_vol,
                            pcr_vol=(
                                round(put_vol / call_vol, 3) if call_vol > 0 else None
                            ),
                            call_oi=call_oi,
                            put_oi=put_oi,
                            pcr_oi=(
                                round(put_oi / call_oi, 3) if call_oi > 0 else None
                            ),
                        )
                    )
            # 交易所接口礼貌节流
            time.sleep(0.3)
            day = date.fromordinal(day.toordinal() + 1)
        return rows


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
