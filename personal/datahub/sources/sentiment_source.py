"""A-share limit-up structure adapter (Eastmoney pools, free data).

涨停梯队口径（东财涨停池，盘后为最终口径）：

- 涨停家数 zt_count、首板数（连板数=1）、二板及以上、最高连板
- 炸板率 = 炸板家数 / (涨停 + 炸板)，>40% 视为亏钱效应显著
- 昨涨停今收益：昨日涨停股今日涨跌幅的均值与上涨占比
  （接力资金盈亏，深负 = 亏钱效应扩散 / 退潮）
"""

from __future__ import annotations

from datetime import date

from ..models import LimitUpStats
from .base import SourceUnavailable


def _zt_pool(ak, api_name_old: str, api_name_new: str, date_text: str):
    """Eastmoney pool APIs keep the same name in akshare 1.19/1.20, but use
    the fallback helper so future renames degrade gracefully."""
    fetch = getattr(ak, api_name_new, None) or getattr(ak, api_name_old, None)
    if fetch is None:
        raise SourceUnavailable(f"akshare has no {api_name_new}")
    try:
        return fetch(date=date_text)
    except TypeError:
        return fetch(date_text)


class LimitUpSource:
    name = "em_limit_up"

    def _ak(self):
        try:
            import akshare as ak
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SourceUnavailable("akshare is not installed") from exc
        return ak

    def fetch_limit_up_stats(self, start: date, end: date) -> list[LimitUpStats]:
        ak = self._ak()
        rows: list[LimitUpStats] = []
        day = start
        while day <= end:
            date_text = day.strftime("%Y%m%d")
            zt = _zt_pool(ak, "stock_zt_pool_em", "stock_zt_pool_em", date_text)
            zb = _zt_pool(ak, "stock_zt_pool_zbgc_em", "stock_zt_pool_zbgc_em", date_text)
            prev = _zt_pool(
                ak, "stock_zt_pool_previous_em", "stock_zt_pool_previous_em", date_text
            )
            if (zt is None or getattr(zt, "empty", True)) and (
                zb is None or getattr(zb, "empty", True)
            ):
                day = date.fromordinal(day.toordinal() + 1)
                continue

            streaks = _numeric(zt, "连板数") if zt is not None else []
            zt_count = 0 if zt is None else int(len(zt))
            zb_count = 0 if zb is None else int(len(zb))
            zb_rate = (
                round(zb_count / (zt_count + zb_count), 4)
                if (zt_count + zb_count) > 0
                else None
            )
            prev_mean = None
            prev_up_ratio = None
            if prev is not None and not getattr(prev, "empty", True):
                chgs = _numeric(prev, "涨跌幅")
                if chgs:
                    prev_mean = round(sum(chgs) / len(chgs), 2)
                    prev_up_ratio = round(
                        sum(1 for c in chgs if c > 0) / len(chgs) * 100, 1
                    )
            rows.append(
                LimitUpStats(
                    trade_date=day,
                    zt_count=zt_count,
                    first_board=sum(1 for s in streaks if s == 1),
                    streak_ge2=sum(1 for s in streaks if s >= 2),
                    max_streak=max(streaks, default=0),
                    zb_count=zb_count,
                    zb_rate=zb_rate,
                    prev_zt_mean=prev_mean,
                    prev_zt_up_ratio=prev_up_ratio,
                )
            )
            day = date.fromordinal(day.toordinal() + 1)
        return rows


def _numeric(frame, column: str) -> list[float]:
    values: list[float] = []
    for item in frame[column]:
        try:
            values.append(float(item))
        except (TypeError, ValueError):
            continue
    return values
