"""Event-driven daily portfolio backtest engine.

Signals are generated after the close of day D and executed at the open of the
next trading day. This avoids look-ahead bias and matches the T+1 reality of
A-share stocks.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable, Mapping, Optional, Sequence

import pandas as pd

from ..datahub.models import DailyBar, TradingStatus
from ..datahub.normalize import normalize_code
from .costs import CostModel
from .execution import ExecutionSimulator
from .metrics import compute_metrics
from .portfolio import Portfolio
from .types import BacktestConfig, BacktestResult, Signal, Trade


def run_backtest(
    bars_by_code: Mapping[str, Sequence[DailyBar]],
    signals: Iterable[Signal],
    config: BacktestConfig,
    *,
    status_by_code: Optional[Mapping[str, Mapping[date, TradingStatus]]] = None,
    benchmark_bars: Optional[Sequence[DailyBar]] = None,
) -> BacktestResult:
    bars = _prepare_bars(bars_by_code, config)
    by_date = _index_by_date(bars)
    trading_dates = sorted(by_date)
    if not trading_dates:
        raise ValueError("no bars in the requested window")

    normalized_signals = _prepare_signals(signals, config)
    signals_by_date: dict[date, list[Signal]] = defaultdict(list)
    for signal in normalized_signals:
        signals_by_date[signal.trade_date].append(signal)

    cost_model = CostModel(config.cost)
    simulator = ExecutionSimulator(
        cost_model,
        lot_size=config.lot_size,
        exclude_st=config.exclude_st,
        exclude_suspended=config.exclude_suspended,
    )
    portfolio = Portfolio(config.initial_cash)
    trades: list[Trade] = []
    equity_points: list[tuple[date, float]] = []
    last_prices: dict[str, float] = {}
    pending: list[Signal] = []

    for current_date in trading_dates:
        today = by_date[current_date]
        equity_before = portfolio.equity(last_prices) if last_prices else portfolio.cash

        for signal in pending:
            bar = today.get(signal.code)
            if bar is None:
                continue
            status = _status_for(status_by_code, signal.code, current_date)
            if signal.action == "buy":
                if (
                    portfolio.quantity(signal.code) <= 0
                    and len(portfolio.positions) >= config.max_positions
                ):
                    continue
                weight = signal.weight or min(
                    config.max_position_pct, 1.0 / max(1, config.max_positions)
                )
                trade = simulator.buy(
                    portfolio,
                    signal.code,
                    weight,
                    bar,
                    status,
                    equity_before,
                    reason=signal.reason,
                )
            else:
                trade = simulator.sell(
                    portfolio,
                    signal.code,
                    bar,
                    status,
                    reason=signal.reason,
                )
            if trade is not None:
                trades.append(trade)
                equity_before = portfolio.equity(last_prices)

        for code, bar in today.items():
            last_prices[code] = bar.close
        equity_points.append((current_date, portfolio.equity(last_prices)))
        pending = list(signals_by_date.get(current_date, []))

    equity_curve = pd.Series(
        [value for _, value in equity_points],
        index=pd.Index([day for day, _ in equity_points], name="date"),
        name="equity",
    )
    benchmark_curve = _build_benchmark_curve(benchmark_bars, trading_dates)
    metrics = compute_metrics(equity_curve, benchmark_curve, trades)

    return BacktestResult(
        equity_curve=equity_curve,
        benchmark_curve=benchmark_curve,
        trades=trades,
        metrics=metrics,
        final_cash=portfolio.cash,
        final_positions=portfolio.position_quantities(),
    )


def _prepare_bars(
    bars_by_code: Mapping[str, Sequence[DailyBar]], config: BacktestConfig
) -> dict[str, list[DailyBar]]:
    prepared: dict[str, list[DailyBar]] = {}
    for raw_code, series in bars_by_code.items():
        code = normalize_code(raw_code)
        filtered = [
            bar
            for bar in sorted(series, key=lambda item: item.trade_date)
            if config.start <= bar.trade_date <= config.end
        ]
        if filtered:
            prepared[code] = filtered
    return prepared


def _index_by_date(
    bars_by_code: Mapping[str, Sequence[DailyBar]]
) -> dict[date, dict[str, DailyBar]]:
    by_date: dict[date, dict[str, DailyBar]] = defaultdict(dict)
    for code, series in bars_by_code.items():
        for bar in series:
            by_date[bar.trade_date][code] = bar
    return dict(by_date)


def _prepare_signals(signals: Iterable[Signal], config: BacktestConfig) -> list[Signal]:
    prepared: list[Signal] = []
    for signal in signals:
        action = str(signal.action).strip().lower()
        if action not in {"buy", "sell"}:
            continue
        if not (config.start <= signal.trade_date <= config.end):
            continue
        prepared.append(
            Signal(
                trade_date=signal.trade_date,
                code=normalize_code(signal.code),
                action=action,
                weight=signal.weight,
                reason=signal.reason,
            )
        )
    return prepared


def _status_for(
    status_by_code: Optional[Mapping[str, Mapping[date, TradingStatus]]],
    code: str,
    trade_date: date,
) -> Optional[TradingStatus]:
    if not status_by_code:
        return None
    return status_by_code.get(code, {}).get(trade_date)


def _build_benchmark_curve(
    benchmark_bars: Optional[Sequence[DailyBar]], trading_dates: Sequence[date]
) -> Optional[pd.Series]:
    if not benchmark_bars:
        return None
    closes = {bar.trade_date: bar.close for bar in benchmark_bars}
    values: list[float] = []
    last: Optional[float] = None
    for day in trading_dates:
        if day in closes:
            last = closes[day]
        values.append(last if last is not None else float("nan"))
    series = pd.Series(
        values,
        index=pd.Index(trading_dates, name="date"),
        name="benchmark",
    )
    series = series.dropna()
    if series.empty:
        return None
    return series / series.iloc[0]
