"""Index PE percentile ranks for the deep-review page.

The valuation series prefers the *daily* Tushare ``index_dailybasic`` feed
(2000-point token, see ``personal.datahub.sources.valuation_tushare_source``)
and falls back to the weekly Legulegu endpoint. Percentiles use all stored
observations of one source in a trailing window including the latest one; a
low percentile means the current PE is cheap relative to that window, not a
buy signal. Sources are never mixed inside one window.

No persistence and no network access here: the caller syncs the raw series
first, then this module only reads the personal database.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Sequence

from ..datahub.models import IndexValuation
from ..datahub.sources.valuation_check_source import OFFICIAL_VALUATION_TARGETS
from ..datahub.sources.valuation_source import INDEX_VALUATION_TARGETS
from ..datahub.store import PersonalStore

#: label -> trailing days
VALUATION_WINDOWS: tuple[tuple[str, int], ...] = (
    ("1y", 365),
    ("3y", 365 * 3),
    ("5y", 365 * 5),
)

#: Minimum observations before a percentile is shown.  Weekly data has ~52
#: points per year; these floors also tolerate a monthly fallback instead of
#: silently showing a percentile over a handful of points.
MIN_WINDOW_SAMPLES = {"1y": 10, "3y": 30, "5y": 50}


def percentile_zone(percentile: float | None) -> str | None:
    """Stable label for UI colouring; lower = cheaper."""

    if percentile is None:
        return None
    if percentile <= 20:
        return "low"
    if percentile <= 40:
        return "low_mid"
    if percentile <= 60:
        return "mid"
    if percentile <= 80:
        return "high_mid"
    return "high"


def _sample_frequency(rows: Sequence[IndexValuation]) -> str:
    if len(rows) < 3:
        return "unknown"
    gaps = [
        (rows[index].trade_date - rows[index - 1].trade_date).days
        for index in range(1, len(rows))
        if (rows[index].trade_date - rows[index - 1].trade_date).days > 0
    ]
    if not gaps:
        return "unknown"
    median_gap = statistics.median(gaps)
    if median_gap <= 2:
        return "daily"
    if median_gap <= 10:
        return "weekly"
    return "monthly"


def _preferred_source(store: PersonalStore, code: str) -> str | None:
    """Pick one storage source per index; never mix frequencies in a window.

    The freshest ``trade_date`` wins, with row count as tie-break so the
    daily Tushare series beats the weekly Legulegu fallback once both are
    present, while a stale Tushare series loses to a freshly synced fallback.
    """

    candidates: dict[str, tuple[date, int]] = {}
    for row in store.get_index_valuations(code=code):
        latest, count = candidates.get(row.source, (row.trade_date, 0))
        candidates[row.source] = (max(latest, row.trade_date), count + 1)
    if not candidates:
        return None
    return max(candidates.items(), key=lambda item: (item[1][0], item[1][1]))[0]


def _window_summary(
    rows: Sequence[IndexValuation],
    latest: IndexValuation,
    *,
    label: str,
    days: int,
) -> dict[str, Any]:
    start = latest.trade_date - timedelta(days=days)
    values = [
        row.pe_ttm
        for row in rows
        if row.trade_date >= start
        and row.trade_date <= latest.trade_date
        and row.pe_ttm is not None
        and row.pe_ttm > 0
    ]
    samples = len(values)
    minimum = MIN_WINDOW_SAMPLES.get(label, 10)
    percentile = None
    if samples >= minimum and latest.pe_ttm is not None:
        below_or_equal = sum(1 for value in values if value <= latest.pe_ttm)
        percentile = round(below_or_equal / samples * 100, 1)
    return {
        "label": label,
        "days": days,
        "start": start.isoformat(),
        "samples": samples,
        "min_samples": minimum,
        "percentile": percentile,
        "zone": percentile_zone(percentile),
        "pe_min": round(min(values), 2) if values else None,
        "pe_median": round(statistics.median(values), 2) if values else None,
        "pe_max": round(max(values), 2) if values else None,
    }


def _index_report(
    store: PersonalStore,
    code: str,
    name: str,
    *,
    as_of: date,
    source: str | None,
) -> dict[str, Any]:
    source = source or _preferred_source(store, code)
    rows = (
        [
            row
            for row in store.get_index_valuations(code=code, end=as_of, source=source)
            if row.pe_ttm is not None and row.pe_ttm > 0
        ]
        if source
        else []
    )
    if not rows:
        return {
            "code": code,
            "name": name,
            "available": False,
            "source": source,
            "as_of": None,
            "stale_days": None,
            "sample_freq": "unknown",
            "pe_ttm": None,
            "pe_ttm_equal": None,
            "pe_static": None,
            "pe_ttm_median": None,
            "close": None,
            "windows": {},
        }
    latest = rows[-1]
    return {
        "code": code,
        "name": name,
        "available": True,
        "source": source,
        "as_of": latest.trade_date.isoformat(),
        "stale_days": max(0, (as_of - latest.trade_date).days),
        "sample_freq": _sample_frequency(rows),
        "pe_ttm": round(latest.pe_ttm, 2) if latest.pe_ttm is not None else None,
        "pe_ttm_equal": (
            round(latest.pe_ttm_equal, 2)
            if latest.pe_ttm_equal is not None
            else None
        ),
        "pe_static": (
            round(latest.pe_static, 2) if latest.pe_static is not None else None
        ),
        "pe_ttm_median": (
            round(latest.pe_ttm_median, 2)
            if latest.pe_ttm_median is not None
            else None
        ),
        "close": round(latest.close, 2) if latest.close is not None else None,
        "windows": {
            label: _window_summary(rows, latest, label=label, days=days)
            for label, days in VALUATION_WINDOWS
        },
    }


def index_valuation_report(
    store: PersonalStore,
    *,
    as_of: date | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Return the four deep-review valuation rows (always one per target).

    With ``source=None`` each index uses its freshest stored source (daily
    Tushare preferred over the weekly Legulegu fallback); frequencies are
    never mixed inside one window.
    """

    today = as_of or date.today()
    rows = [
        _index_report(store, code, name, as_of=today, source=source)
        for code, name in INDEX_VALUATION_TARGETS
    ]
    available = [row for row in rows if row["available"]]
    latest_dates = [row["as_of"] for row in available if row["as_of"]]
    detected = next((row["source"] for row in available if row["source"]), None)
    return {
        "rows": rows,
        "source": source or detected,
        "as_of": max(latest_dates) if latest_dates else None,
        "windows": [label for label, _days in VALUATION_WINDOWS],
        "available": bool(available),
    }


def _check_status(diff_pct: float) -> tuple[str, str]:
    absolute = abs(diff_pct)
    if absolute <= 5:
        return "ok", "偏差在 5% 内，当前水平一致"
    if absolute <= 15:
        return "warn", "5%-15% 口径差异，结合权重/股本口径理解"
    return "error", "偏差超过 15%，需复核数据或口径"


def valuation_cross_check(
    store: PersonalStore,
    official_values: Mapping[str, Mapping[str, Any]],
    *,
    checked_at: datetime | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Compare stored valuation levels with official current values.

    ``official_values`` is injected so tests and callers can use a fake source.
    The comparison is intentionally metric-aware: CSI's total-share PE1 is
    compared with the stored static series, while CNI's rolling PE is compared
    with the stored TTM series. With ``source=None`` each index is checked on
    its freshest stored source (Tushare daily preferred, Legulegu weekly
    fallback).
    """

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for code, name in INDEX_VALUATION_TARGETS:
        target = OFFICIAL_VALUATION_TARGETS.get(code)
        used_source = source or _preferred_source(store, code)
        history = (
            [
                row
                for row in store.get_index_valuations(
                    code=code, source=used_source
                )
                if row.pe_ttm is not None and row.pe_ttm > 0
            ]
            if used_source
            else []
        )
        if target is None or not history:
            detail = "未配置官方校验源" if target is None else "本地无估值历史"
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "status": "unavailable",
                    "detail": detail,
                    "legu_pe": None,
                    "official_pe": None,
                    "official_date": None,
                    "official_source": None,
                    "official_metric": None,
                    "legu_metric": target.get("legu_metric") if target else None,
                    "legu_label": target.get("legu_label") if target else None,
                    "diff_pct": None,
                }
            )
            warnings.append(f"{name}: {detail}")
            continue

        latest = history[-1]
        legu_pe = getattr(latest, target["legu_metric"], None)
        official = official_values.get(code) or {"error": "未获取官方值"}
        if legu_pe is None or legu_pe <= 0:
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "status": "unavailable",
                    "detail": f"本地缺少 {target['legu_label']}",
                    "legu_pe": None,
                    "official_pe": None,
                    "official_date": None,
                    "official_source": None,
                    "official_metric": None,
                    "legu_metric": target["legu_metric"],
                    "legu_label": target["legu_label"],
                    "diff_pct": None,
                }
            )
            warnings.append(f"{name}: 本地缺少 {target['legu_label']}")
            continue

        if "error" in official:
            detail = str(official["error"])
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "status": "unavailable",
                    "detail": detail,
                    "legu_pe": round(float(legu_pe), 2),
                    "official_pe": None,
                    "official_date": None,
                    "official_source": None,
                    "official_metric": target["official_metric"],
                    "legu_metric": target["legu_metric"],
                    "legu_label": target["legu_label"],
                    "diff_pct": None,
                }
            )
            warnings.append(f"{name}: {detail}")
            continue

        official_pe = float(official["official_pe"])
        diff_pct = round((float(legu_pe) / official_pe - 1) * 100, 1)
        status, detail = _check_status(diff_pct)
        row = {
            "code": code,
            "name": name,
            "status": status,
            "detail": detail,
            "legu_pe": round(float(legu_pe), 2),
            "official_pe": round(official_pe, 2),
            "official_date": official.get("official_date"),
            "official_source": official.get("official_source"),
            "official_metric": official.get("official_metric")
            or target["official_metric"],
            "legu_metric": target["legu_metric"],
            "legu_label": target["legu_label"],
            "diff_pct": diff_pct,
        }
        rows.append(row)
        if status != "ok":
            warnings.append(
                f"{name}: 本地 {row['legu_pe']} vs 官方 {row['official_pe']}，"
                f"偏差 {diff_pct:+.1f}%"
            )

    return {
        "checked_at": (checked_at or datetime.now()).isoformat(timespec="seconds"),
        "rows": rows,
        "warnings": warnings,
        "note": (
            "官方源只提供当前值（中证近 20 个交易日、国证最新），"
            "用于水平校验，不参与历史分位计算；加权/股本口径可能不同，"
            "偏差不等于数据错误。"
        ),
    }
