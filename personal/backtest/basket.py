"""Custom basket backtest: user-picked codes, weights and rebalancing.

Portable by design — copy this file together with the backtest kernel
(``engine.py`` / ``types.py`` / ``costs.py`` / ``execution.py`` /
``portfolio.py`` / ``metrics.py``) and the datahub helpers it imports
(``adjust`` / ``normalize`` / ``status`` / ``models``) and it works in any
project:

- The core (``parse_basket_codes`` / ``build_basket_signals`` /
  ``compute_per_stock`` / ``run_basket``) is pure: it consumes plain bars,
  adjustment factors and status rows, never a store.
- ``run_basket_from_store`` is the thin PersonalStore adapter; swap only this
  function when porting.

Semantics (identical to the engine's documented rules):

- Signals dated day D fill at the next trading day's open (T+1 reality).
- The basket enters at the open right after the first trading date in the
  window; per-stock period returns are computed from window-first to
  window-last adjusted close (a market-caliber number, independent of fills).
- ``rebalance="monthly"|"weekly"`` restores the target weights on the first
  trading day of each month / ISO week after entry: sell signals are emitted
  before buy signals for the same date, so the fills sell everything first
  and re-buy at the target weights (sale proceeds are usable the same day,
  matching A-share cash rules). A code suspended at the rebalance open keeps
  its position and heals at the next rebalance.
- Weights: fully specified baskets are normalized to sum to 1; partially
  specified baskets keep the specified ratios and split the remainder evenly
  across unweighted codes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Mapping, Optional, Sequence

from ..datahub.adjust import adjust_bars, factor_at
from ..datahub.models import AdjustFactor, DailyBar, TradingStatus
from ..datahub.normalize import normalize_code
from ..datahub.status import derive_trading_statuses, scale_status_limits
from .engine import run_backtest
from .types import BacktestConfig, BacktestResult, Signal

REBALANCE_CHOICES = ("none", "monthly", "weekly")
MAX_CODES = 30


@dataclass(frozen=True)
class BasketPlan:
    """Parsed basket input: normalized codes and weights summing to ~1."""

    codes: tuple[str, ...]
    weights: dict[str, float]


@dataclass
class BasketStockRow:
    """Per-stock period return over the window (market caliber)."""

    code: str
    weight: float
    first_date: date
    first_close: float
    last_date: date
    last_close: float
    return_pct: float


@dataclass
class BasketRun:
    result: BacktestResult
    codes: list[str]
    skipped: list[str]
    weights: dict[str, float]
    per_stock: list[BasketStockRow]
    signals: list[Signal]
    rebalance: str
    start: date
    end: date


def parse_basket_codes(entries: Sequence[str]) -> BasketPlan:
    """Parse ``CODE`` / ``CODE:weight`` entries into normalized codes+weights."""

    codes: list[str] = []
    raw_weights: dict[str, Optional[float]] = {}
    for entry in entries:
        text = str(entry or "").strip()
        if not text:
            continue
        code_part, sep, weight_part = text.partition(":")
        code = normalize_code(code_part.strip())
        weight = None
        if sep:
            try:
                weight = float(weight_part.strip())
            except ValueError as exc:
                raise ValueError(f"invalid weight for {code}: {weight_part!r}") from exc
            if weight <= 0:
                raise ValueError(f"weight for {code} must be positive")
        if code in raw_weights:
            raise ValueError(f"duplicate basket code: {code}")
        codes.append(code)
        raw_weights[code] = weight
    if not codes:
        raise ValueError("no basket codes given")
    if len(codes) > MAX_CODES:
        raise ValueError(f"too many basket codes ({len(codes)} > {MAX_CODES})")

    specified = {code: value for code, value in raw_weights.items() if value is not None}
    weights: dict[str, float]
    if not specified:
        share = 1.0 / len(codes)
        weights = {code: share for code in codes}
    else:
        total = sum(specified.values())
        unweighted = [code for code in codes if code not in specified]
        if unweighted and total > 1.0 + 1e-9:
            raise ValueError(
                "specified weights already exceed 1.0; nothing left for: "
                + ", ".join(unweighted)
            )
        if unweighted:
            weights = dict(specified)
            share = (1.0 - total) / len(unweighted)
            weights.update({code: share for code in unweighted})
        else:
            weights = {code: value / total for code, value in specified.items()}
    return BasketPlan(codes=tuple(codes), weights=weights)


def rebalance_dates(
    entry_date: date,
    trading_dates: Sequence[date],
    mode: str,
) -> list[date]:
    """First trading day of each month / ISO week strictly after entry."""

    if mode not in {"monthly", "weekly"}:
        return []
    buckets: dict[tuple[int, int], date] = {}
    for day in trading_dates:
        if mode == "monthly":
            key = (day.year, day.month)
        else:
            iso = day.isocalendar()
            key = (iso[0], iso[1])
        buckets.setdefault(key, day)
    return sorted(day for day in buckets.values() if day > entry_date)


def build_basket_signals(
    plan: BasketPlan,
    *,
    entry_date: date,
    trading_dates: Sequence[date],
    rebalance: str = "none",
) -> list[Signal]:
    """Entry buys plus optional rebalance sell/buy pairs.

    Signals dated D fill at the next trading day's open; for a rebalance date
    the sells are listed before the buys so same-day fills liquidate first and
    re-buy at the target weights.
    """

    if rebalance not in REBALANCE_CHOICES:
        raise ValueError(f"unsupported rebalance: {rebalance}")
    signals: list[Signal] = []
    for code in plan.codes:
        signals.append(
            Signal(
                trade_date=entry_date,
                code=code,
                action="buy",
                weight=plan.weights.get(code),
                reason="basket entry",
            )
        )
    for rebalance_day in rebalance_dates(entry_date, trading_dates, rebalance):
        for code in plan.codes:
            signals.append(
                Signal(
                    trade_date=rebalance_day,
                    code=code,
                    action="sell",
                    reason=f"rebalance {rebalance}",
                )
            )
        for code in plan.codes:
            signals.append(
                Signal(
                    trade_date=rebalance_day,
                    code=code,
                    action="buy",
                    weight=plan.weights.get(code),
                    reason=f"rebalance {rebalance}",
                )
            )
    return signals


def compute_per_stock(
    bars_by_code: Mapping[str, Sequence[DailyBar]],
    factors_by_code: Mapping[str, Sequence[AdjustFactor]],
    weights: Mapping[str, float],
    *,
    adjust_mode: str = "hfq",
) -> list[BasketStockRow]:
    """Window-first to window-last adjusted-close return per code."""

    rows: list[BasketStockRow] = []
    for code, bars in sorted(bars_by_code.items()):
        ordered = sorted(bars, key=lambda item: item.trade_date)
        if not ordered:
            continue
        adjusted = adjust_bars(ordered, factors_by_code.get(code, ()), mode=adjust_mode)
        first, last = adjusted[0], adjusted[-1]
        if not first.close:
            continue
        rows.append(
            BasketStockRow(
                code=code,
                weight=round(weights.get(code, 0.0), 6),
                first_date=first.trade_date,
                first_close=first.close,
                last_date=last.trade_date,
                last_close=last.close,
                return_pct=round((last.close / first.close - 1) * 100, 2),
            )
        )
    return rows


def run_basket(
    plan: BasketPlan,
    bars_by_code: Mapping[str, Sequence[DailyBar]],
    config: BacktestConfig,
    *,
    rebalance: str = "none",
    factors_by_code: Optional[Mapping[str, Sequence[AdjustFactor]]] = None,
    status_by_code: Optional[Mapping[str, Mapping[date, TradingStatus]]] = None,
    benchmark_bars: Optional[Sequence[DailyBar]] = None,
) -> BasketRun:
    """Run the basket through the portfolio engine (pure, no I/O)."""

    if rebalance not in REBALANCE_CHOICES:
        raise ValueError(f"unsupported rebalance: {rebalance}")
    prepared = {
        normalize_code(code): list(bars) for code, bars in bars_by_code.items() if bars
    }
    skipped = [code for code in plan.codes if not prepared.get(code)]
    tradable = [code for code in plan.codes if prepared.get(code)]
    if not tradable:
        raise ValueError(
            "no local bars for basket codes (missing: "
            f"{', '.join(plan.codes)}); 先在「数据同步」页同步日线，或运行 "
            "`python -m personal.cli.main sync --source auto --code <代码>` 后重试"
        )

    effective_config = replace(config, max_positions=max(config.max_positions, len(tradable)))
    trading_dates = sorted(
        {
            bar.trade_date
            for bars in prepared.values()
            for bar in bars
            if config.start <= bar.trade_date <= config.end
        }
    )
    if not trading_dates:
        raise ValueError("no bars in the requested window")
    entry_date = trading_dates[0]
    signals = build_basket_signals(
        plan,
        entry_date=entry_date,
        trading_dates=trading_dates,
        rebalance=rebalance,
    )
    result = run_backtest(
        prepared,
        signals,
        effective_config,
        status_by_code=status_by_code,
        benchmark_bars=benchmark_bars,
        adjust_factors_by_code=factors_by_code,
    )
    per_stock = compute_per_stock(
        prepared,
        dict(factors_by_code or {}),
        plan.weights,
        adjust_mode=config.adjust_mode,
    )
    return BasketRun(
        result=result,
        codes=list(plan.codes),
        skipped=skipped,
        weights=dict(plan.weights),
        per_stock=per_stock,
        signals=signals,
        rebalance=rebalance,
        start=config.start,
        end=config.end,
    )


def statuses_for(
    code: str,
    bars: Sequence[DailyBar],
    factors: Sequence[AdjustFactor],
    config: BacktestConfig,
    *,
    stored: Optional[Mapping[date, TradingStatus]] = None,
    calendar: Optional[Sequence[date]] = None,
) -> dict[date, TradingStatus]:
    """Merge stored status rows with derived ones, scaled to the bar space.

    Portable counterpart of the replay helper: takes plain inputs instead of a
    store so the basket core never touches persistence.
    """

    derived = {
        item.trade_date: item
        for item in derive_trading_statuses(
            code,
            bars,
            list(calendar or []),
            factors=factors,
        )
    }
    statuses = dict(derived)
    if stored:
        statuses.update(stored)

    ordered = sorted(bars, key=lambda item: item.trade_date)
    if config.adjust_mode in {"none", ""} or not factors or not ordered:
        return statuses

    if config.adjust_mode == "qfq":
        base = factor_at(factors, ordered[-1].trade_date)
    else:
        base = factor_at(factors, ordered[0].trade_date)
    if base == 0:
        return statuses

    return {
        trade_date: scale_status_limits(
            status,
            factor_at(factors, trade_date) / base,
        )
        for trade_date, status in statuses.items()
    }


def run_basket_from_store(
    store,
    config: BacktestConfig,
    *,
    entries: Sequence[str],
    rebalance: str = "none",
    preferred_sources: Optional[Sequence[str]] = None,
) -> BasketRun:
    """PersonalStore adapter: fetch bars/factors/statuses, then run the core.

    This is the only project-specific part — replace it (or feed ``run_basket``
    directly) when porting the basket backtest to another codebase.
    """

    plan = parse_basket_codes(entries)
    bars_by_code: dict[str, list[DailyBar]] = {}
    for code in plan.codes:
        bars = store.get_bars(
            code,
            config.start,
            config.end,
            preferred_sources=preferred_sources,
        )
        if bars:
            bars_by_code[code] = list(bars)
    if not bars_by_code:
        raise ValueError(
            "no local bars for basket codes (missing: "
            f"{', '.join(plan.codes)}); 先在「数据同步」页同步日线，或运行 "
            "`python -m personal.cli.main sync --source auto --code <代码>` 后重试"
        )

    benchmark_bars = None
    if config.benchmark:
        benchmark_bars = store.get_bars(
            config.benchmark,
            config.start,
            config.end,
            preferred_sources=preferred_sources,
        )

    factors_by_code: dict[str, list[AdjustFactor]] = {
        code: list(store.get_adjust_factors(code)) for code in bars_by_code
    }
    calendar = store.get_trading_dates(config.start, config.end)
    status_map: dict[str, dict[date, TradingStatus]] = {
        code: statuses_for(
            code,
            bars,
            factors_by_code.get(code, []),
            config,
            stored=store.get_trading_statuses(code, config.start, config.end),
            calendar=calendar,
        )
        for code, bars in bars_by_code.items()
    }
    return run_basket(
        plan,
        bars_by_code,
        config,
        rebalance=rebalance,
        factors_by_code=factors_by_code,
        status_by_code=status_map,
        benchmark_bars=benchmark_bars or None,
    )
