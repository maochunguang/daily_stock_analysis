"""决策快照（RM-12 增强）：买卖时点的市场状态存档。

每笔记账（交割单导入的成交或手动日志）在入库时自动固化当天的市场状态：
综合分及各分量分位、TRIN 判读、涨停结构、成交额、行业拥挤 top1、持仓股
两融余额及其 5 期变化。事后可统计「我在什么市场状态下操作胜率最高」。

快照是**当日数据**（用 ``composite_score(end=trade_date)`` 回看该日），
缺失的分量记 null，不影响其余字段。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from .composite import composite_score
from .store import PersonalStore


def snapshot_market_state(
    store: PersonalStore, trade_date: date, code: str | None = None
) -> dict[str, Any]:
    """Return the market state as of ``trade_date`` (JSON-safe dict)."""
    snapshot: dict[str, Any] = {"trade_date": trade_date.isoformat()}

    composite = composite_score(store, end=trade_date)
    snapshot["composite"] = {
        "score": composite.score,
        "state": composite.state,
        "components": [
            {
                "metric": component.metric,
                "label": component.label,
                "kind": component.kind,
                "percentile": component.percentile,
                "value": component.value,
            }
            for component in composite.components
            if component.percentile is not None
        ],
    }

    breadth = store.get_market_breadth(start=trade_date, end=trade_date)
    if breadth:
        row = breadth[0]
        snapshot["breadth"] = {
            "trin": row.trin,
            "band": row.band,
            "adv_ratio": row.adv_ratio,
            "interpretation": row.interpretation,
        }

    zt = store.get_limit_up_stats(start=trade_date, end=trade_date)
    if zt:
        row = zt[0]
        snapshot["limit_up"] = {
            "zt_count": row.zt_count,
            "zb_rate": row.zb_rate,
            "max_streak": row.max_streak,
        }

    turnover = store.get_market_turnover(start=trade_date, end=trade_date)
    if turnover and turnover[0].total_amount:
        snapshot["turnover_yi"] = round(turnover[0].total_amount / 1e8, 1)

    sectors = [
        (row.board, row.share_pct)
        for row in store.get_sector_amounts(
            start=trade_date, end=trade_date, limit=0
        )
        if row.share_pct is not None
    ]
    if sectors:
        board, share = max(sectors, key=lambda item: item[1])
        snapshot["sector_top"] = {"board": board, "share_pct": share}

    if code:
        series = store.get_margin_stock(code=code, end=trade_date, limit=6)
        if series:
            latest = series[-1]
            entry: dict[str, Any] = {
                "rzye": latest.rzye,
                "rzye_buy": latest.rzye_buy,
            }
            if len(series) >= 6 and series[0].rzye and latest.rzye:
                entry["rzye_chg_5d_pct"] = round(
                    (latest.rzye - series[0].rzye) / series[0].rzye * 100, 2
                )
            snapshot["margin_stock"] = entry

    return snapshot


def snapshot_json(
    store: PersonalStore, trade_date: date, code: str | None = None
) -> str:
    return json.dumps(
        snapshot_market_state(store, trade_date, code),
        ensure_ascii=False,
        separators=(",", ":"),
    )
