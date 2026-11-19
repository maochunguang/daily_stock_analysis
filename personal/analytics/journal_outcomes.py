"""Forward outcomes for individual journal decisions.

Each journal entry is evaluated after its own trade date: D+N means the Nth
security trading bar strictly after that date. Entry prices are converted into
the same adjusted-price space as the bars, so a split/dividend inside the
window does not create a fake return. Results are computed on demand; they are
not persisted, which avoids presenting stale outcomes as current facts.
"""

from __future__ import annotations

import bisect
import json
import math
from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

from ..backtest.metrics import wilson_interval
from ..datahub.adjust import adjust_bars, factor_at
from ..datahub.models import AdjustFactor, DailyBar
from ..datahub.normalize import normalize_code
from ..datahub.store import PersonalStore

HORIZONS = (1, 5, 20, 60)


def evaluate_journal_outcomes(
    store: PersonalStore,
    *,
    horizon: int = 20,
    days: int = 365,
    code: str | None = None,
    side: str | None = None,
    limit: int = 200,
    benchmark_code: str | None = None,
    adjust_mode: str = "hfq",
    today: date | None = None,
) -> dict[str, Any]:
    """Evaluate all eligible journal entries and return rows + summary."""

    if horizon <= 0:
        raise ValueError("horizon must be positive")
    today = today or date.today()
    normalized_code = normalize_code(code) if code else None
    normalized_side = side.strip().lower() if side else None
    if normalized_side and normalized_side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")

    start = today - timedelta(days=max(1, days))
    entries = store.list_journal(
        limit=10_000,
        start=start,
        end=today,
        code=normalized_code,
    )
    if normalized_side:
        entries = [entry for entry in entries if entry.get("side") == normalized_side]
    if not entries:
        return {
            "horizon": horizon,
            "days": days,
            "benchmark_code": benchmark_code,
            "rows": [],
            "summary": _empty_summary(horizon),
        }

    plans = {
        plan["id"]: plan for plan in store.list_trade_plans(limit=2_000)
    }
    benchmark_bars, benchmark_source = _load_benchmark(
        store, benchmark_code, start, today
    )
    benchmark_returns = _index_benchmark_returns(benchmark_bars)

    # One bar source per code for the entire window. Fetching separately per
    # horizon could silently switch sources and make D+1/5/20/60 inconsistent.
    bars_by_code: dict[str, list[DailyBar]] = {}
    factors_by_code: dict[str, list[AdjustFactor]] = {}
    for entry in entries:
        entry_code = normalize_code(str(entry["code"]))
        if entry_code in bars_by_code:
            continue
        try:
            trade_date = date.fromisoformat(str(entry["trade_date"]))
            bars = store.get_bars(
                entry_code, trade_date - timedelta(days=400), today
            )
            factors = store.get_adjust_factors(entry_code)
            adjusted = adjust_bars(bars, factors, mode=adjust_mode)
        except (ValueError, RuntimeError):
            bars, factors, adjusted = [], [], []
        bars_by_code[entry_code] = adjusted
        factors_by_code[entry_code] = factors

    rows: list[dict[str, Any]] = []
    for entry in entries:
        rows.append(
            _evaluate_one(
                entry,
                bars=bars_by_code.get(normalize_code(str(entry["code"])), []),
                factors=factors_by_code.get(normalize_code(str(entry["code"])), []),
                benchmark_returns=benchmark_returns,
                benchmark_source=benchmark_source,
                horizon=horizon,
                adjust_mode=adjust_mode,
                plans=plans,
            )
        )

    summary = summarize_outcomes(rows, horizon=horizon)
    return {
        "horizon": horizon,
        "days": days,
        "benchmark_code": benchmark_code,
        "rows": rows[: max(0, int(limit))],
        "summary": summary,
    }


def _evaluate_one(
    entry: Mapping[str, Any],
    *,
    bars: Sequence[DailyBar],
    factors: Sequence[AdjustFactor],
    benchmark_returns: Mapping[date, float] | None,
    benchmark_source: str | None,
    horizon: int,
    adjust_mode: str,
    plans: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    trade_date = date.fromisoformat(str(entry["trade_date"]))
    side = str(entry.get("side") or "").lower()
    code = normalize_code(str(entry["code"]))
    price = _number(entry.get("price"))
    quantity = _number(entry.get("quantity")) or 0.0
    base = {
        "journal_id": entry["id"],
        "trade_date": trade_date.isoformat(),
        "code": code,
        "side": side,
        "quantity": quantity,
        "price": price,
        "amount": _number(entry.get("amount")),
        "source": entry.get("source") or "manual",
        "mistake_type": entry.get("mistake_type"),
        "horizon": horizon,
        "status": "unavailable",
        "unable_reason": None,
        "target_date": None,
        "bar_count": 0,
        "entry_price_adjusted": None,
        "end_close": None,
        "asset_return": None,
        "aligned_return": None,
        "benchmark_return": None,
        "excess_return": None,
        "mae": None,
        "mfe": None,
        "stock_source": bars[0].source if bars else None,
        "benchmark_source": benchmark_source,
    }
    _attach_snapshot_context(base, entry)
    _attach_plan_context(base, entry, plans)

    if price is None or price <= 0:
        base["unable_reason"] = "成交价格无效，无法计算收益"
        return base
    if not bars:
        base["unable_reason"] = "本地没有该代码的日线数据"
        return base
    try:
        adjusted_entry = _adjust_entry_price(
            price, trade_date, bars, factors, adjust_mode
        )
    except ValueError:
        base["unable_reason"] = "复权因子无效"
        return base
    base["entry_price_adjusted"] = round(adjusted_entry, 4)
    future = [bar for bar in bars if bar.trade_date > trade_date]
    base["bar_count"] = min(len(future), horizon)
    if not future:
        base["status"] = "pending"
        base["unable_reason"] = "尚无成交日之后的交易日数据"
        return base
    if len(future) < horizon:
        base["status"] = "pending"
        base["unable_reason"] = (
            f"交易日不足：已有 {len(future)} 个，还需 {horizon - len(future)} 个"
        )
        window = future
        base["mae"], base["mfe"] = _mae_mfe(window, adjusted_entry, side)
        return base

    window = future[:horizon]
    target = window[-1]
    end_close = target.close
    asset_return = end_close / adjusted_entry - 1.0
    base.update(
        {
            "status": "completed",
            "target_date": target.trade_date.isoformat(),
            "end_close": round(end_close, 4),
            "asset_return": round(asset_return, 6),
            "aligned_return": round(
                asset_return if side == "buy" else -asset_return, 6
            ),
            "mae": _round(_mae_mfe(window, adjusted_entry, side)[0], 6),
            "mfe": _round(_mae_mfe(window, adjusted_entry, side)[1], 6),
        }
    )
    if benchmark_returns:
        benchmark_return = _benchmark_return(
            benchmark_returns, trade_date, target.trade_date
        )
        if benchmark_return is not None:
            base["benchmark_return"] = round(benchmark_return, 6)
            base["excess_return"] = round(asset_return - benchmark_return, 6)
    return base


def summarize_outcomes(
    rows: Sequence[Mapping[str, Any]], *, horizon: int
) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    pending = [row for row in rows if row.get("status") == "pending"]
    unavailable = [row for row in rows if row.get("status") == "unavailable"]
    aligned = [
        float(row["aligned_return"])
        for row in completed
        if row.get("aligned_return") is not None
    ]
    successes = sum(1 for value in aligned if value > 0)
    win_rate = successes / len(aligned) if aligned else None
    ci_low, ci_high = wilson_interval(successes, len(aligned)) if aligned else (None, None)
    by_side = {
        side: _group_summary(
            [row for row in completed if row.get("side") == side]
        )
        for side in ("buy", "sell")
    }
    by_state: dict[str, dict[str, Any]] = {}
    for row in completed:
        state = row.get("composite_state") or "未记录"
        by_state.setdefault(state, []).append(row)
    by_market_state = {
        state: _group_summary(items) for state, items in by_state.items()
    }
    linked = [row for row in completed if row.get("plan_id")]
    in_range = [
        row for row in linked if row.get("entry_in_plan_range") is True
    ]
    return {
        "horizon": horizon,
        "total": len(rows),
        "completed": len(completed),
        "pending": len(pending),
        "unavailable": len(unavailable),
        "aligned_mean": _round(_mean(aligned), 6),
        "aligned_median": _round(_median(aligned), 6),
        "win_rate": _round(win_rate, 6),
        "win_rate_ci": [
            _round(ci_low, 6) if ci_low is not None else None,
            _round(ci_high, 6) if ci_high is not None else None,
        ],
        "avg_mae": _round(_mean([_number(row.get("mae")) for row in completed]), 6),
        "avg_mfe": _round(_mean([_number(row.get("mfe")) for row in completed]), 6),
        "by_side": by_side,
        "by_market_state": by_market_state,
        "plan_linked": len(linked),
        "plan_entry_in_range": len(in_range),
        "plan_entry_in_range_rate": _round(
            len(in_range) / len(linked), 6
        )
        if linked
        else None,
        "sample_warning": len(aligned) < 30,
    }


def _group_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = [
        float(row["aligned_return"])
        for row in rows
        if row.get("aligned_return") is not None
    ]
    successes = sum(1 for value in values if value > 0)
    return {
        "completed": len(rows),
        "aligned_mean": _round(_mean(values), 6),
        "win_rate": _round(successes / len(values), 6) if values else None,
        "avg_mae": _round(_mean([_number(row.get("mae")) for row in rows]), 6),
        "avg_mfe": _round(_mean([_number(row.get("mfe")) for row in rows]), 6),
    }


def _empty_summary(horizon: int) -> dict[str, Any]:
    return {
        "horizon": horizon,
        "total": 0,
        "completed": 0,
        "pending": 0,
        "unavailable": 0,
        "aligned_mean": None,
        "aligned_median": None,
        "win_rate": None,
        "win_rate_ci": [None, None],
        "avg_mae": None,
        "avg_mfe": None,
        "by_side": {
            "buy": _empty_group(),
            "sell": _empty_group(),
        },
        "by_market_state": {},
        "plan_linked": 0,
        "plan_entry_in_range": 0,
        "plan_entry_in_range_rate": None,
        "sample_warning": True,
    }


def _empty_group() -> dict[str, Any]:
    return {
        "completed": 0,
        "aligned_mean": None,
        "win_rate": None,
        "avg_mae": None,
        "avg_mfe": None,
    }


def _attach_snapshot_context(
    base: dict[str, Any], entry: Mapping[str, Any]
) -> None:
    raw = entry.get("snapshot")
    if not raw:
        return
    try:
        snapshot = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return
    composite = snapshot.get("composite") or {}
    breadth = snapshot.get("breadth") or {}
    base["composite_state"] = composite.get("state")
    base["composite_score"] = composite.get("score")
    base["trin"] = breadth.get("trin")


def _attach_plan_context(
    base: dict[str, Any],
    entry: Mapping[str, Any],
    plans: Mapping[int, Mapping[str, Any]],
) -> None:
    plan_id = entry.get("plan_id")
    if not plan_id:
        return
    plan = plans.get(int(plan_id))
    if not plan:
        return
    price = _number(entry.get("price"))
    entry_low = _number(plan.get("entry_low"))
    entry_high = _number(plan.get("entry_high"))
    midpoint = (entry_low + entry_high) / 2.0 if entry_low and entry_high else None
    suggested = _number(plan.get("requested_quantity"))
    if suggested is None:
        try:
            preview = json.loads(plan.get("preview_json") or "{}")
            suggested = _number(preview.get("suggested_quantity"))
        except (TypeError, ValueError):
            suggested = None
    quantity = _number(entry.get("quantity")) or 0.0
    base.update(
        {
            "plan_id": int(plan_id),
            "plan_status": plan.get("status"),
            "plan_side": plan.get("side"),
            "plan_entry_low": entry_low,
            "plan_entry_high": entry_high,
            "entry_in_plan_range": (
                entry_low <= price <= entry_high
                if price is not None and entry_low is not None and entry_high is not None
                else None
            ),
            "entry_deviation": (
                (price - midpoint) / midpoint
                if price is not None and midpoint
                else None
            ),
            "plan_suggested_quantity": suggested,
            "plan_quantity_ratio": (
                quantity / suggested if suggested and suggested > 0 else None
            ),
        }
    )


def _adjust_entry_price(
    price: float,
    trade_date: date,
    bars: Sequence[DailyBar],
    factors: Sequence[AdjustFactor],
    mode: str,
) -> float:
    if mode in {"", "none"} or not factors or not bars:
        return price
    if mode == "qfq":
        base = factor_at(factors, bars[-1].trade_date)
    else:
        base = factor_at(factors, bars[0].trade_date)
    if base == 0:
        raise ValueError("invalid adjustment factor")
    return price * factor_at(factors, trade_date) / base


def _mae_mfe(
    bars: Sequence[DailyBar], entry: float, side: str
) -> tuple[float | None, float | None]:
    if not bars or entry <= 0:
        return None, None
    low = min(bar.low for bar in bars)
    high = max(bar.high for bar in bars)
    if side == "sell":
        mae = min(0.0, (entry - high) / entry)
        mfe = max(0.0, (entry - low) / entry)
    else:
        mae = min(0.0, low / entry - 1.0)
        mfe = max(0.0, high / entry - 1.0)
    return mae, mfe


def _load_benchmark(
    store: PersonalStore,
    benchmark_code: str | None,
    start: date,
    end: date,
) -> tuple[list[DailyBar], str | None]:
    if not benchmark_code:
        return [], None
    try:
        bars = store.get_bars(normalize_code(benchmark_code), start, end)
        if not bars:
            return [], None
        factors = store.get_adjust_factors(normalize_code(benchmark_code))
        adjusted = adjust_bars(bars, factors, mode="hfq")
        return adjusted, adjusted[0].source
    except (ValueError, RuntimeError):
        return [], None


def _index_benchmark_returns(
    bars: Sequence[DailyBar],
) -> dict[date, float]:
    if len(bars) < 2:
        return {}
    values = {bar.trade_date: bar.close for bar in bars if bar.close > 0}
    dates = sorted(values)
    result: dict[date, float] = {}
    for previous, current in zip(dates, dates[1:]):
        if values[previous] > 0:
            result[current] = values[current] / values[previous] - 1.0
    return result


def _benchmark_return(
    returns: Mapping[date, float], entry_date: date, target_date: date
) -> float | None:
    """Compound benchmark returns from the close on/before entry to target."""

    dates = sorted(returns)
    start_index = bisect.bisect_right(dates, entry_date)
    end_index = bisect.bisect_right(dates, target_date)
    if start_index >= end_index:
        return None
    value = 1.0
    for day in dates[start_index:end_index]:
        value *= 1.0 + returns[day]
    return value - 1.0


def _mean(values: Iterable[float | None]) -> float | None:
    cleaned = [float(value) for value in values if value is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits)


__all__ = ["HORIZONS", "evaluate_journal_outcomes", "summarize_outcomes"]
