"""Composite market-state score (机构式多指标印证).

把各深度指标全部转成约一年滚动分位（样本不足 20 个则跳过），按方向映射到
0-100 的「温度」，平均得到综合状态分：

    0-25  冰点（逆向指标显示恐慌/冰点，机会区）
    25-40 偏冷
    40-60 中性
    60-75 偏热
    75-100 过热（risk-off 警戒）

每个分量带方向标签：顺势（高分位 = 过热，如两融占比/炸板率/上涨占比）、
逆向（高分位 = 恐慌，常见阶段底，如期权 PCR/期指净空占比）。分量平均而
非黑箱加权；样本不足的分量自动跳过并在卡片可见。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .store import PersonalStore

#: 分位回看窗口（自然日 ≈ 250 个交易日）
PERCENTILE_WINDOW_DAYS = 365
MIN_SAMPLES = 20


@dataclass(frozen=True)
class CompositeComponent:
    metric: str
    label: str
    kind: str  # pro(顺势) | contrarian(逆向)
    value: float | None
    percentile: float | None
    sample_count: int

    def as_dict(self) -> dict:
        return {
            "metric": self.metric,
            "label": self.label,
            "kind": self.kind,
            "value": self.value,
            "percentile": self.percentile,
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True)
class CompositeScore:
    score: float | None
    state: str
    components: list[CompositeComponent]

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "state": self.state,
            "components": [component.as_dict() for component in self.components],
        }


def percentile_rank(values: list[float], current: float) -> float:
    below = sum(1 for v in values if v < current)
    return round(below / len(values) * 100, 1)


def composite_score(store: PersonalStore, end: date | None = None) -> CompositeScore:
    end = end or date.today()
    start = date.fromordinal(end.toordinal() - PERCENTILE_WINDOW_DAYS)
    components: list[CompositeComponent] = []

    # --- 顺势分量：高分位 = 过热 ---
    margin_ratio = _margin_ratios(store, start, end)
    _append(components, "margin_buy_ratio", "两融交易占比", "pro", margin_ratio)

    zt = store.get_limit_up_stats(start=start, end=end)
    _append(components, "zb_rate", "炸板率", "pro", _series(zt, lambda r: r.zb_rate))
    _append(components, "max_streak", "连板高度", "pro", _series(zt, lambda r: r.max_streak))

    futures = store.get_index_futures(start=start, end=end)
    basis = _avg_by_date(futures, lambda r: r.basis_pct)
    # 基差率顺热：升水/浅贴水 = 定价乐观
    _append(components, "futures_basis_pct", "期指基差率", "pro", basis)

    breadth = store.get_market_breadth(start=start, end=end)
    _append(components, "adv_ratio", "上涨占比", "pro", _series(breadth, lambda r: r.adv_ratio))

    # --- 逆向分量：高分位 = 恐慌，常见阶段底 ---
    pcr = store.get_option_pcr(start=start, end=end, underlying="50ETF")
    _append(components, "pcr_vol", "期权PCR", "contrarian", _series(pcr, lambda r: r.pcr_vol))

    rank_rows = store.get_futures_rank(start=start, end=end)
    net_ratio = _avg_by_date(rank_rows, lambda r: r.net_ratio)
    _append(components, "futures_net_ratio", "期指净空占比", "contrarian", net_ratio)

    scored = [c for c in components if c.percentile is not None]
    if scored:
        score = round(sum(c.percentile for c in scored) / len(scored), 1)
        state = _state_of(score)
    else:
        score, state = None, "数据不足"
    return CompositeScore(score=score, state=state, components=components)


def _state_of(score: float) -> str:
    if score >= 75:
        return "过热（risk-off 警戒）"
    if score >= 60:
        return "偏热"
    if score <= 25:
        return "冰点（机会区）"
    if score <= 40:
        return "偏冷"
    return "中性"


def _series(rows, getter) -> list[tuple[date, float]]:
    out = []
    for row in rows:
        value = getter(row)
        if value is not None:
            out.append((row.trade_date, value))
    return out


def _append(
    components: list[CompositeComponent],
    metric: str,
    label: str,
    kind: str,
    series: list[tuple[date, float]],
) -> None:
    values = [v for _, v in series]
    if len(values) < MIN_SAMPLES:
        return
    current = values[-1]
    components.append(
        CompositeComponent(
            metric=metric,
            label=label,
            kind=kind,
            value=round(current, 3),
            percentile=percentile_rank(values, current),
            sample_count=len(values),
        )
    )


def _margin_ratios(store: PersonalStore, start: date, end: date) -> list[tuple[date, float]]:
    """融资买入额 / 全市场成交额（%）——两融温度计，>10% 过热 / <7% 冰点。"""
    margin = {
        row.trade_date: row.rzye_buy
        for row in store.get_margin_balance(
            start=start, end=end, scope_type="market", limit=0
        )
        if row.scope == "总计" and row.rzye_buy is not None
    }
    turnover = {
        row.trade_date: row.total_amount
        for row in store.get_market_turnover(start=start, end=end)
        if row.total_amount
    }
    out: list[tuple[date, float]] = []
    for day in sorted(set(margin) & set(turnover)):
        out.append((day, round(margin[day] / turnover[day] * 100, 3)))
    return out


def _avg_by_date(rows, getter) -> list[tuple[date, float]]:
    buckets: dict[date, list[float]] = {}
    for row in rows:
        value = getter(row)
        if value is None:
            continue
        buckets.setdefault(row.trade_date, []).append(value)
    return [(day, sum(vals) / len(vals)) for day, vals in sorted(buckets.items())]
