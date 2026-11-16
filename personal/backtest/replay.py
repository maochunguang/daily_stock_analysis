"""Replay upstream AI advice / decision signals through the portfolio engine."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional, Sequence

from ..backtest.engine import run_backtest
from ..backtest.types import BacktestConfig, BacktestResult, Signal
from ..contracts.models import AnalysisRecord, DecisionSignalRecord
from ..contracts.upstream_db import UpstreamDB
from ..datahub.normalize import normalize_code
from ..datahub.store import PersonalStore

BUY_KEYWORDS = ("买入", "加仓", "增持", "建仓", "buy", "add", "accumulate")
SELL_KEYWORDS = ("卖出", "减仓", "清仓", "减持", "sell", "reduce", "avoid")
NEGATIONS = ("不", "别", "勿", "谨慎", "暂不", "不宜")


def advice_to_action(advice: Optional[str]) -> Optional[str]:
    text = str(advice or "").strip().lower()
    if not text:
        return None
    for keyword in SELL_KEYWORDS:
        position = text.find(keyword)
        if position >= 0 and not _negated(text, position):
            return "sell"
    for keyword in BUY_KEYWORDS:
        position = text.find(keyword)
        if position >= 0 and not _negated(text, position):
            return "buy"
    return None


def _negated(text: str, position: int) -> bool:
    prefix = text[max(0, position - 3) : position]
    return any(negation in prefix for negation in NEGATIONS)


def signals_from_analyses(records: Iterable[AnalysisRecord]) -> list[Signal]:
    signals: dict[tuple[date, str, str], Signal] = {}
    for record in records:
        if record.created_at is None:
            continue
        action = advice_to_action(record.operation_advice)
        if action is None:
            continue
        code = normalize_code(record.code)
        key = (record.created_at.date(), code, action)
        signals[key] = Signal(
            trade_date=record.created_at.date(),
            code=code,
            action=action,
            reason=record.operation_advice or "",
        )
    return sorted(signals.values(), key=lambda item: (item.trade_date, item.code))


def signals_from_decision_signals(
    records: Iterable[DecisionSignalRecord],
) -> list[Signal]:
    signals: dict[tuple[date, str, str], Signal] = {}
    for record in records:
        if record.created_at is None:
            continue
        action = str(record.action or "").strip().lower()
        if action in {"buy", "add"}:
            mapped = "buy"
        elif action in {"sell", "reduce", "avoid"}:
            mapped = "sell"
        else:
            continue
        code = normalize_code(record.stock_code)
        key = (record.created_at.date(), code, mapped)
        signals[key] = Signal(
            trade_date=record.created_at.date(),
            code=code,
            action=mapped,
            reason=record.reason or action,
        )
    return sorted(signals.values(), key=lambda item: (item.trade_date, item.code))


def load_upstream_signals(
    db: UpstreamDB,
    start: date,
    end: date,
    *,
    include_analyses: bool = True,
    include_signals: bool = True,
) -> list[Signal]:
    signals: list[Signal] = []
    if include_analyses:
        signals.extend(
            signal
            for signal in signals_from_analyses(db.recent_analyses(limit=10_000))
            if start <= signal.trade_date <= end
        )
    if include_signals:
        signals.extend(
            signal
            for signal in signals_from_decision_signals(db.recent_decision_signals(limit=10_000))
            if start <= signal.trade_date <= end
        )
    deduped = {
        (signal.trade_date, signal.code, signal.action): signal for signal in signals
    }
    return sorted(deduped.values(), key=lambda item: (item.trade_date, item.code))


def replay_upstream(
    db: UpstreamDB,
    store: PersonalStore,
    config: BacktestConfig,
    *,
    include_analyses: bool = True,
    include_signals: bool = True,
    preferred_sources: Optional[Sequence[str]] = None,
) -> tuple[BacktestResult, list[Signal]]:
    signals = load_upstream_signals(
        db,
        config.start,
        config.end,
        include_analyses=include_analyses,
        include_signals=include_signals,
    )
    if not signals:
        raise ValueError("no upstream buy/sell signals in the requested window")

    codes = sorted({signal.code for signal in signals})
    bars_by_code = {}
    missing: list[str] = []
    for code in codes:
        bars = store.get_bars(
            code,
            config.start,
            config.end,
            preferred_sources=preferred_sources,
        )
        if bars:
            bars_by_code[code] = bars
        else:
            missing.append(code)
    if not bars_by_code:
        raise ValueError(
            "no local bars for signal codes; run `dsa-personal sync` first "
            f"(missing: {', '.join(missing)})"
        )

    benchmark_bars = None
    if config.benchmark:
        benchmark_bars = store.get_bars(
            config.benchmark,
            config.start,
            config.end,
            preferred_sources=preferred_sources,
        )

    result = run_backtest(
        bars_by_code,
        signals,
        config,
        benchmark_bars=benchmark_bars or None,
    )
    return result, signals
