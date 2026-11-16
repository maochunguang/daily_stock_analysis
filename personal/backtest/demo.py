"""Synthetic demo backtest shared by the CLI and the Web console."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from ..datahub.sources.base import SyntheticSource
from .engine import run_backtest
from .types import BacktestConfig, BacktestResult, Signal

DEMO_CODES = ("600519.SH", "000001.SZ", "300750.SZ", "601318.SH", "510050.SH")


@dataclass
class DemoRun:
    result: BacktestResult
    start: date
    end: date
    codes: tuple[str, ...]
    signals: list[Signal]


def run_demo_backtest(settings: Any, *, days: int = 400) -> DemoRun:
    end = date.today()
    start = end - timedelta(days=days)
    bars_by_code: dict[str, list] = {}
    for index, code in enumerate(DEMO_CODES):
        source = SyntheticSource(seed=7 + index, start_price=10.0 + index * 5)
        bars_by_code[code] = source.fetch_daily_bars(code, start, end)

    benchmark_source = SyntheticSource(seed=99, start_price=4000.0)
    benchmark_bars = benchmark_source.fetch_daily_bars("000300.SH", start, end)

    signals: list[Signal] = []
    for code, bars in bars_by_code.items():
        for index in range(20, len(bars) - 5, 60):
            signals.append(
                Signal(bars[index].trade_date, code, "buy", reason="demo entry")
            )
            sell_index = index + 30
            if sell_index < len(bars) - 1:
                signals.append(
                    Signal(
                        bars[sell_index].trade_date,
                        code,
                        "sell",
                        reason="demo exit",
                    )
                )

    config = BacktestConfig(
        start=start,
        end=end,
        initial_cash=settings.backtest_initial_cash,
        benchmark="000300.SH",
    )
    result = run_backtest(
        bars_by_code,
        signals,
        config,
        benchmark_bars=benchmark_bars,
    )
    return DemoRun(
        result=result,
        start=start,
        end=end,
        codes=DEMO_CODES,
        signals=signals,
    )
