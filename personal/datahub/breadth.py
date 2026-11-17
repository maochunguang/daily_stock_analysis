"""Market breadth (Arms Index / TRIN) interpretation and snapshot import.

口径移植自用户另一个项目 ``easy-daily-trading`` 的 ``tools/arms_index.py``，
阈值是 2025-10 ~ 2026-10 共 250 个交易日的 A 股实测分位：

    TRIN = (上涨家数 / 下跌家数) ÷ (上涨成交量 / 下跌成交量)

A 股 TRIN 整体负偏（中位数约 0.78），不能直接套用美股 1.0 中枢。
单看 TRIN 会误判：同样 TRIN 0.40，普涨日 = 量能集中在龙头（健康），
普跌日 = 资金抱团避险（恐慌但常近短期底），所以解读要结合上涨占比。

快照来源 ``easy-daily-trading/cache/arms_index/daily/{date}.json``：
市场范围剔除北交所与 ST，前复权收盘价逐日计算涨跌，成交量统一为股，
成交额以「股 × 收盘价」估算。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterator

from .models import MarketBreadth

#: A 股经验分位带（边界, 标签, 量能状态）。
A_SHARE_BANDS: tuple[tuple[float, str, str], ...] = (
    (0.405, "极低", "量能极度集中"),
    (0.579, "偏低", "量能集中"),
    (0.780, "中低位", "偏强"),
    (1.122, "中高位", "中性"),
    (1.428, "偏高", "偏弱"),
    (1.747, "高位", "量能撤离"),
    (99.0, "极高", "恐慌/背离"),
)


def trin_band(trin: float | None) -> tuple[str, str]:
    """Return (分位区间标签, 量能状态)."""
    if trin is None:
        return "—", "数据不足"
    for edge, label, state in A_SHARE_BANDS:
        if trin <= edge:
            return label, state
    return "极高", "恐慌/背离"


def interpret(trin: float | None, adv_ratio: float | None = None) -> str:
    """结合上涨占比与 TRIN 分位给出可操作判读。"""
    if trin is None:
        return "数据不足"

    band, _ = trin_band(trin)
    ar = adv_ratio if adv_ratio is not None else 50.0

    if ar >= 60:  # 普涨
        if trin <= 0.579:
            return f"{band}｜普涨+量能集中 → 强势健康"
        if trin <= 0.780:
            return f"{band}｜普涨+量能偏强 → 温和向好"
        if trin <= 1.122:
            return f"{band}｜普涨+量能平平 → 中性"
        if trin <= 1.747:
            return f"{band}｜普涨但量能跟不上 → 警惕假突破"
        return f"{band}｜普涨但量能严重不足 → 背离警报"
    if ar <= 30:  # 普跌
        if trin <= 0.579:
            return f"{band}｜普跌+资金抱团少数票 → 恐慌，常近短期底"
        if trin <= 0.780:
            return f"{band}｜普跌+量能尚可 → 弱势整理"
        if trin <= 1.122:
            return f"{band}｜普跌+量能均衡 → 常规调整"
        if trin <= 1.747:
            return f"{band}｜普跌+放量出逃 → 弱势延续"
        return f"{band}｜普跌+恐慌性放量 → 加速赶底"
    if trin <= 0.579:  # 分化
        return f"{band}｜分化+量能偏多 → 结构性行情"
    if trin <= 1.122:
        return f"{band}｜分化+量能均衡 → 震荡"
    return f"{band}｜分化+量能偏空 → 结构性走弱"


def percentile_of(trin: float | None, history) -> float | None:
    """TRIN 在历史样本中的分位（0-100）。"""
    if trin is None:
        return None
    samples = [x for x in history if x is not None]
    if not samples:
        return None
    below = sum(1 for x in samples if x < trin)
    return round(below / len(samples) * 100, 1)


def compute_trin(
    up_count: int, down_count: int, up_vol_yi: float, down_vol_yi: float
) -> float | None:
    """TRIN = (涨/跌家数) ÷ (涨/跌成交量)；除零返回 None。"""
    if down_count <= 0 or down_vol_yi <= 0 or up_vol_yi <= 0:
        return None
    return round((up_count / down_count) / (up_vol_yi / down_vol_yi), 3)


def load_easy_daily_snapshots(
    directory: str | Path, *, source: str = "easy_daily_trading"
) -> Iterator[MarketBreadth]:
    """Yield one MarketBreadth per ``{date}.json`` snapshot file.

    Snapshot format (from easy-daily-trading ``tools/arms_index.py``)::

        {"date": "2026-11-17", "up": 1192, "down": 3717, "flat": 117,
         "up_vol_yi": 306.61, "down_vol_yi": 623.52,
         "up_amt_yi": 5225.1, "down_amt_yi": 8966.9,
         "trin": 0.652, "trin_amt": 0.55, "adv_ratio": 23.7,
         "total": 5026, "signal": "...", "band": "中低位", "pct": 32.6,
         "index": 3584.58, "index_chg": -0.5, "index_pos": 0.0,
         "signal_tag": "—", "signal_detail": [...], "divergence": 0}

    Broken/missing fields degrade to None or "" instead of raising, so a
    single bad file never blocks the import.
    """
    root = Path(directory)
    if not root.exists():
        return
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            trade_date = date.fromisoformat(str(payload["date"])[:10])
        except Exception:
            continue
        detail = payload.get("signal_detail") or []
        if isinstance(detail, list):
            detail_text = "；".join(str(item) for item in detail)
        else:
            detail_text = str(detail)
        yield MarketBreadth(
            trade_date=trade_date,
            up_count=int(payload.get("up") or 0),
            down_count=int(payload.get("down") or 0),
            flat_count=int(payload.get("flat") or 0),
            sample_count=int(payload.get("total") or 0),
            up_vol_yi=_opt_float(payload.get("up_vol_yi")),
            down_vol_yi=_opt_float(payload.get("down_vol_yi")),
            up_amount_yi=_opt_float(payload.get("up_amt_yi")),
            down_amount_yi=_opt_float(payload.get("down_amt_yi")),
            adv_ratio=_opt_float(payload.get("adv_ratio")),
            trin=_opt_float(payload.get("trin")),
            trin_amount=_opt_float(payload.get("trin_amt")),
            trin_pct=_opt_float(payload.get("pct")),
            interpretation=str(payload.get("signal") or ""),
            band=str(payload.get("band") or ""),
            index_close=_opt_float(payload.get("index")),
            index_chg_pct=_opt_float(payload.get("index_chg")),
            index_pos=_opt_float(payload.get("index_pos")),
            divergence=int(payload.get("divergence") or 0),
            signal_tag=str(payload.get("signal_tag") or ""),
            signal_detail=detail_text,
            source=source,
        )


def _opt_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
