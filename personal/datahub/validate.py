"""数据准确性校验（RM-41）：内部一致性 + 跨指标交叉 + 外部源抽检。

三层防线，全部只读，不修改源数据：

1. **内部一致性**（离线，每次同步后自动跑）：恒等式（总计=沪+深、
   融资余额+融券余额=两融余额、PCR=认沽/认购、净空=卖-买、基差率复算、
   占比合计=100）、取值域、非交易日、重复日期、日环比跳变、缺失交易日。
2. **跨指标交叉**（离线）：行业成交额合计 vs 全市场成交额（可同时抓出
   快照日期错位和半日数据）、板块两融合计 vs 全市场总计、综合分样本覆盖。
3. **外部源抽检**（在线，手动 ``validate --online``）：两融明细 vs 交易所
   汇总、中债官方国债收益率 vs 东财、中金所官方日行情 vs 新浪主力合约、
   乐咕乐股涨跌家数 vs 阿姆氏快照。每个外部源独立 try/except，失败只记
   info，不影响离线结论。

输出按数据集分组：``ok`` / ``warn`` / ``error`` / ``empty``，健康分取各数据
集状态均值（ok=100, warn=70, empty=50, error=20），用于深度复盘页「数据
体检」卡片和 ``data_quality_event`` 落库。
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Iterable, Sequence

from .store import PersonalStore

#: 参与体检的数据集（与 schedule/CLI 的 dataset 名一致）
DATASETS: tuple[str, ...] = (
    "turnover",
    "margin",
    "futures",
    "cffex_rank",
    "pcr",
    "zt",
    "sector",
    "etf_share",
    "bond",
    "breadth",
    "release",
)

DATASET_LABELS: dict[str, str] = {
    "turnover": "全市场成交额",
    "margin": "融资余额",
    "futures": "股指期货",
    "cffex_rank": "期指会员持仓",
    "pcr": "期权 PCR",
    "zt": "涨停梯队",
    "sector": "行业拥挤度",
    "etf_share": "ETF 份额",
    "bond": "中美利差",
    "breadth": "市场宽度 TRIN",
    "release": "解禁日历",
}

#: 允许落后「最近已收盘交易日」的交易日数。
#: 收盘后当天数据要等下一轮 06:00 同步才入库，所以统一留 1 个交易日缓冲；
#: 连续两轮没更新才会报 stale。
MAX_LAG_DAYS: dict[str, int] = {
    "turnover": 1,
    "margin": 1,  # 交易所两融数据次日早间发布
    "futures": 1,
    "cffex_rank": 1,
    "pcr": 1,
    "zt": 1,
    "sector": 1,
    "etf_share": 1,
    "bond": 1,  # 美债腿随美国时段滞后
    "breadth": 3,  # 快照由 easy-daily-trading 手动导入
    "release": 999,  # 前瞻日历，不做新鲜度判断
}

_SCORE_BY_STATUS = {"ok": 100, "warn": 70, "empty": 50, "error": 20}


@dataclass(frozen=True)
class Finding:
    dataset: str
    rule: str
    severity: str  # error | warn | info
    detail: str
    trade_date: date | None = None

    def as_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "rule": self.rule,
            "severity": self.severity,
            "detail": self.detail,
            "trade_date": self.trade_date.isoformat() if self.trade_date else None,
        }


@dataclass
class DatasetReport:
    dataset: str
    label: str
    status: str
    rows: int
    latest: date | None
    expected_latest: date | None
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for item in self.findings if item.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for item in self.findings if item.severity == "warn")

    def as_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "label": self.label,
            "status": self.status,
            "rows": self.rows,
            "latest": self.latest.isoformat() if self.latest else None,
            "expected_latest": (
                self.expected_latest.isoformat() if self.expected_latest else None
            ),
            "errors": self.errors,
            "warnings": self.warnings,
            "findings": [item.as_dict() for item in self.findings],
        }


@dataclass
class ValidationReport:
    generated_at: str
    start: date
    end: date
    score: int
    status: str
    online: bool
    datasets: list[DatasetReport]

    @property
    def findings(self) -> list[Finding]:
        flat = [item for report in self.datasets for item in report.findings]
        order = {"error": 0, "warn": 1, "info": 2}
        return sorted(flat, key=lambda item: order.get(item.severity, 3))

    def as_dict(self) -> dict:
        counts = {status: 0 for status in ("ok", "warn", "error", "empty")}
        for report in self.datasets:
            counts[report.status] = counts.get(report.status, 0) + 1
        return {
            "generated_at": self.generated_at,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "score": self.score,
            "status": self.status,
            "online": self.online,
            "counts": counts,
            "datasets": [report.as_dict() for report in self.datasets],
            "findings": [item.as_dict() for item in self.findings[:50]],
        }


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------
def validate_store(
    store: PersonalStore,
    *,
    days: int = 400,
    datasets: Sequence[str] | None = None,
    online: bool = False,
    now: datetime | None = None,
) -> ValidationReport:
    """Run every requested check and return a grouped report."""
    now = now or datetime.now()
    end = now.date()
    start = end - timedelta(days=days) if days and days > 0 else date(2000, 1, 1)
    selected = tuple(datasets or DATASETS)
    unknown = [name for name in selected if name not in _CHECKERS]
    if unknown:
        raise ValueError(f"unknown validation dataset(s): {', '.join(unknown)}")

    calendar = _calendar(store, start, end)
    completed = _last_completed_trade_date(calendar, now)
    online_findings = _online_findings(store, selected) if online else {}

    reports: list[DatasetReport] = []
    for name in selected:
        rows, latest, findings = _CHECKERS[name](store, start, end, calendar)
        findings = list(findings) + online_findings.get(name, [])
        expected = _expected_latest(completed, MAX_LAG_DAYS[name], calendar)
        findings.extend(_freshness(name, rows, latest, expected, completed))
        status = _status(rows, findings)
        reports.append(
            DatasetReport(
                dataset=name,
                label=DATASET_LABELS.get(name, name),
                status=status,
                rows=rows,
                latest=latest,
                expected_latest=expected,
                findings=findings,
            )
        )

    score = round(
        sum(_SCORE_BY_STATUS[report.status] for report in reports) / len(reports)
    )
    worst = "ok"
    if any(report.status == "error" for report in reports):
        worst = "error"
    elif any(report.status == "warn" for report in reports):
        worst = "warn"
    elif any(report.status == "empty" for report in reports):
        worst = "empty"
    return ValidationReport(
        generated_at=now.isoformat(timespec="seconds"),
        start=start,
        end=end,
        score=score,
        status=worst,
        online=online,
        datasets=reports,
    )


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------
def _calendar(store: PersonalStore, start: date, end: date) -> list[date]:
    days = store.get_trading_dates(
        start=start - timedelta(days=40), end=end + timedelta(days=1)
    )
    return days


def _last_completed_trade_date(calendar: Sequence[date], now: datetime) -> date:
    today = now.date()
    days = [day for day in calendar if day <= today]
    if days and days[-1] == today and now.hour < 15:
        days = days[:-1]
    if days:
        return days[-1]
    day = today
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _expected_latest(
    completed: date, lag: int, calendar: Sequence[date]
) -> date | None:
    if lag >= 999:
        return None
    if not calendar:
        return completed - timedelta(days=lag)
    index = bisect.bisect_right(calendar, completed) - 1
    return calendar[max(0, index - lag)]


def _status(rows: int, findings: Sequence[Finding]) -> str:
    if any(item.severity == "error" for item in findings):
        return "error"
    if rows <= 0:
        return "empty"
    if any(item.severity == "warn" for item in findings):
        return "warn"
    return "ok"


def _freshness(
    dataset: str,
    rows: int,
    latest: date | None,
    expected: date | None,
    completed: date,
) -> list[Finding]:
    if rows <= 0:
        return [
            Finding(dataset, "empty", "warn", "数据集为空，先运行对应 sync")
        ]
    if latest is None:
        return [Finding(dataset, "no_latest", "warn", "没有可用日期")]
    if expected is not None and latest > completed:
        return [
            Finding(
                dataset,
                "future_dated",
                "warn",
                f"最新日期 {latest} 晚于最近已收盘交易日 {completed}"
                "（快照日期可能错位）",
                latest,
            )
        ]
    if expected is not None and latest < expected:
        return [
            Finding(
                dataset,
                "stale",
                "warn",
                f"最新日期 {latest}，预期至少到 {expected}（发布滞后或同步失败）",
                latest,
            )
        ]
    return []


def _non_trading(
    dataset: str, days: Iterable[date], calendar: Sequence[date]
) -> list[Finding]:
    if len(calendar) < 20:
        return []
    known = set(calendar)
    window_start, window_end = calendar[0], calendar[-1]
    unchecked = 0
    bad: list[date] = []
    for day in days:
        if day < window_start or day > window_end:
            unchecked += 1
        elif day not in known:
            bad.append(day)
    findings: list[Finding] = []
    if unchecked:
        findings.append(
            Finding(
                dataset,
                "calendar_coverage",
                "info",
                f"{unchecked} 条记录早于/晚于交易日历覆盖范围"
                f"（{window_start}~{window_end}），未做交易日校验；可回填 calendar",
            )
        )
    if bad:
        sample = ", ".join(day.isoformat() for day in bad[:3])
        findings.append(
            Finding(
                dataset,
                "non_trading_day",
                "error",
                f"{len(bad)} 条记录落在非交易日：{sample}",
            )
        )
    return findings


def _gaps(
    dataset: str,
    days: Iterable[date],
    calendar: Sequence[date],
    *,
    max_missing_ratio: float,
) -> list[Finding]:
    present = sorted(set(days))
    if not present or len(calendar) < 20:
        return []
    window = [day for day in calendar if present[0] <= day <= present[-1]]
    missing = [day for day in window if day not in set(present)]
    if not missing:
        return []
    ratio = len(missing) / max(len(window), 1)
    if ratio <= max_missing_ratio:
        return []
    sample = ", ".join(day.isoformat() for day in missing[:5])
    return [
        Finding(
            dataset,
            "missing_days",
            "warn",
            f"窗口内缺 {len(missing)}/{len(window)} 个交易日（{ratio:.1%}）：{sample}",
        )
    ]


def _jump(
    dataset: str,
    series: Sequence[tuple[date, float]],
    *,
    max_pct: float,
    floor: float | None = None,
    label: str = "环比",
) -> list[Finding]:
    findings: list[Finding] = []
    for (prev_day, prev), (day, value) in zip(series, series[1:]):
        if prev and abs(value - prev) / abs(prev) > max_pct:
            findings.append(
                Finding(
                    dataset,
                    "extreme_jump",
                    "warn",
                    f"{day} {label} {prev:g} -> {value:g}",
                    day,
                )
            )
    if floor is not None:
        for day, value in series:
            if value < floor:
                findings.append(
                    Finding(
                        dataset,
                        "below_floor",
                        "warn",
                        f"{day} 数值 {value:g} 低于合理下限 {floor:g}（疑似半日/盘前数据）",
                        day,
                    )
                )
    return findings[:8]


def _scopes_by_date(rows, getter) -> dict[date, list]:
    buckets: dict[date, list] = {}
    for row in rows:
        buckets.setdefault(getter(row), []).append(row)
    return buckets


# ----------------------------------------------------------------------
# Per-dataset checkers
# ----------------------------------------------------------------------
def _check_turnover(store, start, end, calendar):
    rows = store.get_market_turnover(start=start, end=end)
    findings: list[Finding] = []
    dates: list[date] = []
    series: list[tuple[date, float]] = []
    for row in rows:
        dates.append(row.trade_date)
        if not row.total_amount or not row.sse_amount or not row.szse_amount:
            findings.append(
                Finding("turnover", "zero_amount", "error", f"{row.trade_date} 成交额为 0/缺失", row.trade_date)
            )
            continue
        # total_amount is derived (sse+szse) by the model, so the only stored
        # identity left to guard is that both legs are present and positive.
        series.append((row.trade_date, row.total_amount / 1e8))
    findings.extend(_non_trading("turnover", dates, calendar))
    findings.extend(_gaps("turnover", dates, calendar, max_missing_ratio=0.02))
    findings.extend(_jump("turnover", series, max_pct=0.6, floor=2000.0))
    latest = max(dates, default=None)
    return len(rows), latest, findings


def _check_margin(store, start, end, calendar):
    rows = store.get_margin_balance(start=start, end=end, limit=0)
    findings: list[Finding] = []
    dates = [row.trade_date for row in rows]
    for bucket_date, items in _scopes_by_date(rows, lambda row: row.trade_date).items():
        by_scope = {row.scope: row for row in items}
        # Tushare 历史回补只产 market 行（3 口径）；板块行只来自交易所明细，
        # 因此以该日是否已有板块行判定预期口径数。
        has_board = any(row.scope_type == "board" for row in items)
        expected_scopes = 7 if has_board else 3
        if len(by_scope) < expected_scopes:
            findings.append(
                Finding(
                    "margin",
                    "incomplete_scopes",
                    "warn",
                    f"{bucket_date} 只有 {len(by_scope)} 个口径（预期 {expected_scopes}）",
                    bucket_date,
                )
            )
        total = by_scope.get("总计")
        sse = by_scope.get("沪市")
        szse = by_scope.get("深市")
        if total and sse and szse and total.rzye and sse.rzye and szse.rzye:
            if abs(total.rzye - sse.rzye - szse.rzye) / total.rzye > 0.005:
                findings.append(
                    Finding(
                        "margin",
                        "identity_market_total",
                        "error",
                        f"{bucket_date} 总计 {total.rzye:g} ≠ 沪 {sse.rzye:g} + 深 {szse.rzye:g}",
                        bucket_date,
                    )
                )
    for row in rows:
        where = f"{row.scope_type}/{row.scope}"
        if row.rzye is None or row.rzye <= 0:
            findings.append(
                Finding("margin", "non_positive_rzye", "error", f"{row.trade_date} {where} 融资余额缺失/非正", row.trade_date)
            )
        if row.rzye_buy and row.rzye and row.rzye_buy > row.rzye * 1.001:
            findings.append(
                Finding(
                    "margin",
                    "buy_gt_balance",
                    "error",
                    f"{row.trade_date} {where} 融资买入 {row.rzye_buy:g} > 融资余额 {row.rzye:g}",
                    row.trade_date,
                )
            )
        if row.rzye and row.rqye is not None and row.rzrqye:
            diff = abs(row.rzrqye - row.rzye - row.rqye)
            # 深交所汇总存在固定 100 万元口径差，按 0.01% 或 2e6 容差
            if diff > max(2e6, row.rzrqye * 0.0001):
                findings.append(
                    Finding(
                        "margin",
                        "identity_balance_total",
                        "warn",
                        f"{row.trade_date} {where} 融资+融券与两融合计差 {diff / 1e4:.0f} 万",
                        row.trade_date,
                    )
                )
    for bucket_date, items in _scopes_by_date(rows, lambda row: row.trade_date).items():
        by_scope = {row.scope: row for row in items}
        total = by_scope.get("总计")
        board_sum = sum(
            row.rzye or 0 for row in items if row.scope_type == "board"
        )
        if total and total.rzye and board_sum:
            ratio = board_sum / total.rzye
            if not 0.85 <= ratio <= 1.0:
                findings.append(
                    Finding(
                        "margin",
                        "board_share",
                        "warn",
                        f"{bucket_date} 板块合计/总计 = {ratio:.1%}（预期 85%-100%）",
                        bucket_date,
                    )
                )
    findings.extend(_non_trading("margin", dates, calendar))
    findings.extend(_gaps("margin", dates, calendar, max_missing_ratio=0.02))
    latest = max(dates, default=None)
    return len(rows), latest, findings


def _check_futures(store, start, end, calendar):
    rows = store.get_index_futures(start=start, end=end)
    findings: list[Finding] = []
    dates = [row.trade_date for row in rows]
    for bucket_date, items in _scopes_by_date(rows, lambda row: row.trade_date).items():
        symbols = {row.symbol for row in items}
        if len(symbols) < 4:
            findings.append(
                Finding(
                    "futures",
                    "incomplete_symbols",
                    "warn",
                    f"{bucket_date} 只有 {sorted(symbols)}（预期 IF/IH/IC/IM）",
                    bucket_date,
                )
            )
    oi_series: dict[str, list[tuple[date, float]]] = {}
    for row in rows:
        if not row.close or row.close <= 0:
            findings.append(
                Finding("futures", "bad_close", "error", f"{row.trade_date} {row.symbol} 收盘价缺失/非正", row.trade_date)
            )
            continue
        if row.index_close and row.basis_pct is not None:
            recomputed = (row.close - row.index_close) / row.index_close * 100
            if abs(recomputed - row.basis_pct) > 0.05:
                findings.append(
                    Finding(
                        "futures",
                        "basis_recompute",
                        "error",
                        f"{row.trade_date} {row.symbol} 基差率 {row.basis_pct:g} ≠ 复算 {recomputed:.3f}",
                        row.trade_date,
                    )
                )
        if row.basis_pct is not None and abs(row.basis_pct) > 10:
            findings.append(
                Finding(
                    "futures",
                    "basis_out_of_range",
                    "error",
                    f"{row.trade_date} {row.symbol} 基差率 {row.basis_pct:g}% 超出 ±10%",
                    row.trade_date,
                )
            )
        if row.open_interest and row.oi_chg is not None and abs(row.oi_chg) > row.open_interest * 0.5:
            findings.append(
                Finding(
                    "futures",
                    "oi_chg_out_of_range",
                    "warn",
                    f"{row.trade_date} {row.symbol} 持仓变化 {row.oi_chg:g} / 持仓 {row.open_interest:g}",
                    row.trade_date,
                )
            )
        if row.open_interest:
            oi_series.setdefault(row.symbol, []).append((row.trade_date, row.open_interest))
    findings.extend(_non_trading("futures", dates, calendar))
    findings.extend(_gaps("futures", dates, calendar, max_missing_ratio=0.02))
    latest = max(dates, default=None)
    return len(rows), latest, findings


def _check_cffex_rank(store, start, end, calendar):
    rows = store.get_futures_rank(start=start, end=end)
    findings: list[Finding] = []
    dates = [row.trade_date for row in rows]
    for bucket_date, items in _scopes_by_date(rows, lambda row: row.trade_date).items():
        if len({row.symbol for row in items}) < 4:
            findings.append(
                Finding(
                    "cffex_rank",
                    "incomplete_symbols",
                    "warn",
                    f"{bucket_date} 只有 {sorted({row.symbol for row in items})}",
                    bucket_date,
                )
            )
    for row in rows:
        if not row.top20_buy or not row.top20_sell:
            findings.append(
                Finding("cffex_rank", "zero_position", "error", f"{row.trade_date} {row.symbol} 持仓为 0", row.trade_date)
            )
            continue
        if row.net is None or abs(row.top20_sell - row.top20_buy - row.net) > 1:
            findings.append(
                Finding(
                    "cffex_rank",
                    "net_recompute",
                    "error",
                    f"{row.trade_date} {row.symbol} 净空 {row.net} ≠ 卖 {row.top20_sell:g} - 买 {row.top20_buy:g}",
                    row.trade_date,
                )
            )
        if row.net_ratio is not None:
            recomputed = row.net / (row.top20_buy + row.top20_sell)
            if abs(recomputed - row.net_ratio) > 0.002:
                findings.append(
                    Finding(
                        "cffex_rank",
                        "net_ratio_recompute",
                        "error",
                        f"{row.trade_date} {row.symbol} 净空占比 {row.net_ratio:g} ≠ 复算 {recomputed:.4f}",
                        row.trade_date,
                    )
                )
            if abs(row.net_ratio) > 0.5:
                findings.append(
                    Finding(
                        "cffex_rank",
                        "net_ratio_range",
                        "warn",
                        f"{row.trade_date} {row.symbol} 净空占比 {row.net_ratio:g} 超出 ±0.5",
                        row.trade_date,
                    )
                )
    findings.extend(_non_trading("cffex_rank", dates, calendar))
    findings.extend(_gaps("cffex_rank", dates, calendar, max_missing_ratio=0.02))
    latest = max(dates, default=None)
    return len(rows), latest, findings


def _check_pcr(store, start, end, calendar):
    rows = store.get_option_pcr(start=start, end=end)
    findings: list[Finding] = []
    dates = [row.trade_date for row in rows]
    for bucket_date, items in _scopes_by_date(rows, lambda row: row.trade_date).items():
        if len({row.underlying for row in items}) < 2:
            findings.append(
                Finding("pcr", "incomplete_underlyings", "warn", f"{bucket_date} 缺少 300ETF 或 50ETF", bucket_date)
            )
    for row in rows:
        if not row.call_vol or not row.put_vol:
            findings.append(
                Finding("pcr", "zero_volume", "error", f"{row.trade_date} {row.underlying} 成交量为 0", row.trade_date)
            )
            continue
        recomputed = round(row.put_vol / row.call_vol, 3)
        if row.pcr_vol is None or abs(recomputed - row.pcr_vol) > 0.005:
            findings.append(
                Finding(
                    "pcr",
                    "pcr_recompute",
                    "error",
                    f"{row.trade_date} {row.underlying} PCR {row.pcr_vol} ≠ 认沽/认购 {recomputed}",
                    row.trade_date,
                )
            )
        for value, name in ((row.pcr_vol, "成交量PCR"), (row.pcr_oi, "持仓量PCR")):
            if value is not None and not 0.05 <= value <= 5:
                findings.append(
                    Finding(
                        "pcr",
                        "pcr_range",
                        "warn",
                        f"{row.trade_date} {row.underlying} {name} {value} 超出 0.05-5",
                        row.trade_date,
                    )
                )
    findings.extend(_non_trading("pcr", dates, calendar))
    findings.extend(_gaps("pcr", dates, calendar, max_missing_ratio=0.03))
    latest = max(dates, default=None)
    return len(rows), latest, findings


def _check_zt(store, start, end, calendar):
    rows = store.get_limit_up_stats(start=start, end=end)
    findings: list[Finding] = []
    dates = [row.trade_date for row in rows]
    for row in rows:
        if not 0 <= row.zt_count <= 400:
            findings.append(
                Finding("zt", "zt_count_range", "error", f"{row.trade_date} 涨停 {row.zt_count} 家超出 0-400", row.trade_date)
            )
        if row.first_board + row.streak_ge2 != row.zt_count:
            findings.append(
                Finding(
                    "zt",
                    "ladder_total",
                    "warn",
                    f"{row.trade_date} 首板 {row.first_board} + 连板 {row.streak_ge2} ≠ 涨停 {row.zt_count}",
                    row.trade_date,
                )
            )
        if row.max_streak > 30:
            findings.append(
                Finding("zt", "streak_range", "warn", f"{row.trade_date} 最高连板 {row.max_streak}", row.trade_date)
            )
        if row.zb_rate is not None:
            denominator = row.zt_count + row.zb_count
            if denominator:
                recomputed = row.zb_count / denominator
                if abs(recomputed - row.zb_rate) > 0.02:
                    findings.append(
                        Finding(
                            "zt",
                            "zb_rate_recompute",
                            "warn",
                            f"{row.trade_date} 炸板率 {row.zb_rate:g} ≠ 炸板/{涨停+炸板} {recomputed:.3f}",
                            row.trade_date,
                        )
                    )
            if not 0 <= row.zb_rate <= 1:
                findings.append(
                    Finding("zt", "zb_rate_range", "error", f"{row.trade_date} 炸板率 {row.zb_rate:g} 超出 0-1", row.trade_date)
                )
    findings.extend(_non_trading("zt", dates, calendar))
    latest = max(dates, default=None)
    return len(rows), latest, findings


def _check_sector(store, start, end, calendar):
    rows = store.get_sector_amounts(start=start, end=end, limit=0)
    findings: list[Finding] = []
    dates = [row.trade_date for row in rows]
    turnover = {row.trade_date: row.total_amount for row in store.get_market_turnover(start=start, end=end)}
    for bucket_date, items in _scopes_by_date(rows, lambda row: row.trade_date).items():
        if len(items) < 30:
            findings.append(
                Finding("sector", "board_count", "warn", f"{bucket_date} 只有 {len(items)} 个行业（预期 90）", bucket_date)
            )
        share_sum = sum(row.share_pct or 0 for row in items)
        if abs(share_sum - 100) > 0.5:
            findings.append(
                Finding("sector", "share_sum", "error", f"{bucket_date} 行业占比合计 {share_sum:.2f}% ≠ 100%", bucket_date)
            )
        total_amount = sum(row.amount_yi or 0 for row in items) * 1e8
        benchmark = turnover.get(bucket_date)
        if benchmark:
            ratio = total_amount / benchmark
            if not 0.85 <= ratio <= 1.15:
                findings.append(
                    Finding(
                        "sector",
                        "amount_vs_turnover",
                        "error",
                        f"{bucket_date} 行业成交额/全市场成交额 = {ratio:.1%}（预期 85%-115%，疑似日期错位/半日）",
                        bucket_date,
                    )
                )
            elif not 0.92 <= ratio <= 1.08:
                findings.append(
                    Finding(
                        "sector",
                        "amount_vs_turnover",
                        "warn",
                        f"{bucket_date} 行业成交额/全市场成交额 = {ratio:.1%}",
                        bucket_date,
                    )
                )
    findings.extend(_non_trading("sector", dates, calendar))
    latest = max(dates, default=None)
    return len(rows), latest, findings


def _check_etf_share(store, start, end, calendar):
    rows = store.get_etf_share(start=start, end=end, limit=0)
    findings: list[Finding] = []
    dates = [row.trade_date for row in rows]
    by_code: dict[str, list[tuple[date, float]]] = {}
    for row in rows:
        if not row.share_yi or not 1 <= row.share_yi <= 5000:
            findings.append(
                Finding(
                    "etf_share",
                    "share_range",
                    "error",
                    f"{row.trade_date} {row.code} 份额 {row.share_yi} 超出 1-5000 亿份（单位/数据错误）",
                    row.trade_date,
                )
            )
            continue
        by_code.setdefault(row.code, []).append((row.trade_date, row.share_yi))
    for bucket_date, items in _scopes_by_date(rows, lambda row: row.trade_date).items():
        if len(items) < 7:
            findings.append(
                Finding("etf_share", "incomplete_codes", "warn", f"{bucket_date} 只有 {len(items)} 只 ETF（预期 7）", bucket_date)
            )
    for code, series in by_code.items():
        findings.extend(_jump("etf_share", series, max_pct=0.3, label=f"{code} 份额"))
    findings.extend(_non_trading("etf_share", dates, calendar))
    latest = max(dates, default=None)
    return len(rows), latest, findings


def _check_bond(store, start, end, calendar):
    rows = store.get_bond_yield(start=start, end=end)
    findings: list[Finding] = []
    dates = [row.trade_date for row in rows]
    cn_series: list[tuple[date, float]] = []
    us_series: list[tuple[date, float]] = []
    for row in rows:
        if row.cn_10y is not None:
            if not 0.5 <= row.cn_10y <= 6:
                findings.append(
                    Finding("bond", "cn_10y_range", "error", f"{row.trade_date} 中国10Y {row.cn_10y} 超出 0.5-6", row.trade_date)
                )
            cn_series.append((row.trade_date, row.cn_10y))
        if row.us_10y is not None:
            if not 0 <= row.us_10y <= 10:
                findings.append(
                    Finding("bond", "us_10y_range", "error", f"{row.trade_date} 美国10Y {row.us_10y} 超出 0-10", row.trade_date)
                )
            us_series.append((row.trade_date, row.us_10y))
        if row.cn_10y is not None and row.us_10y is not None:
            if row.spread_10y is None or abs(row.cn_10y - row.us_10y - row.spread_10y) > 0.02:
                findings.append(
                    Finding(
                        "bond",
                        "spread_recompute",
                        "error",
                        f"{row.trade_date} 10Y 利差 {row.spread_10y} ≠ 中 {row.cn_10y} - 美 {row.us_10y}",
                        row.trade_date,
                    )
                )
    latest_row = max(rows, key=lambda row: row.trade_date, default=None)
    if latest_row and latest_row.cn_10y is not None and latest_row.us_10y is None:
        findings.append(
            Finding(
                "bond",
                "us_leg_pending",
                "info",
                f"{latest_row.trade_date} 美债腿尚未更新（美国时段滞后，次日补齐）",
                latest_row.trade_date,
            )
        )
    # 东财收益率序列按自然日给出（含美债独立交易日与调休日），
    # 不能按 A 股交易日历判定非交易日，也不做交易日缺口检查。
    findings.extend(_jump("bond", cn_series, max_pct=0.05, label="中国10Y"))
    findings.extend(_jump("bond", us_series, max_pct=0.05, label="美国10Y"))
    latest = max(dates, default=None)
    return len(rows), latest, findings


def _check_breadth(store, start, end, calendar):
    rows = store.get_market_breadth(start=start, end=end)
    findings: list[Finding] = []
    dates = [row.trade_date for row in rows]
    for row in rows:
        if row.up_count + row.down_count + row.flat_count != row.sample_count:
            findings.append(
                Finding(
                    "breadth",
                    "count_identity",
                    "error",
                    f"{row.trade_date} 涨 {row.up_count} + 跌 {row.down_count} + 平 {row.flat_count} "
                    f"≠ 样本 {row.sample_count}",
                    row.trade_date,
                )
            )
        if row.adv_ratio is not None and row.sample_count:
            expected_sample = row.up_count / row.sample_count * 100
            pair = row.up_count + row.down_count
            expected_pair = row.up_count / pair * 100 if pair else expected_sample
            if min(abs(row.adv_ratio - expected_sample), abs(row.adv_ratio - expected_pair)) > 0.3:
                findings.append(
                    Finding(
                        "breadth",
                        "adv_ratio_recompute",
                        "warn",
                        f"{row.trade_date} 上涨占比 {row.adv_ratio:g} 与涨/样本 {expected_sample:.2f} "
                        f"及涨/(涨+跌) {expected_pair:.2f} 都不符",
                        row.trade_date,
                    )
                )
        if row.trin is not None and not 0.1 <= row.trin <= 10:
            findings.append(
                Finding("breadth", "trin_range", "error", f"{row.trade_date} TRIN {row.trin} 超出 0.1-10", row.trade_date)
            )
    findings.extend(_non_trading("breadth", dates, calendar))
    findings.extend(_gaps("breadth", dates, calendar, max_missing_ratio=0.03))
    latest = max(dates, default=None)
    return len(rows), latest, findings


def _check_release(store, start, end, calendar):
    rows = store.get_restricted_release(start=start, end=end)
    findings: list[Finding] = []
    for row in rows:
        if row.company_count < 0 or (row.shares is not None and row.shares < 0):
            findings.append(
                Finding("release", "negative_value", "error", f"{row.release_date} 家数/股数为负", row.release_date)
            )
        if row.market_value_yi is not None and row.market_value_yi < 0:
            findings.append(
                Finding("release", "negative_value", "error", f"{row.release_date} 解禁市值为负", row.release_date)
            )
    latest = max((row.release_date for row in rows), default=None)
    return len(rows), latest, findings


_CHECKERS: dict[str, Callable] = {
    "turnover": _check_turnover,
    "margin": _check_margin,
    "futures": _check_futures,
    "cffex_rank": _check_cffex_rank,
    "pcr": _check_pcr,
    "zt": _check_zt,
    "sector": _check_sector,
    "etf_share": _check_etf_share,
    "bond": _check_bond,
    "breadth": _check_breadth,
    "release": _check_release,
}


# ----------------------------------------------------------------------
# Online spot checks (optional, manual)
# ----------------------------------------------------------------------
def _online_findings(
    store: PersonalStore, datasets: Sequence[str]
) -> dict[str, list[Finding]]:
    try:
        import akshare as ak
    except ImportError:
        return {
            name: [Finding(name, "online_unavailable", "info", "akshare 未安装，跳过外部抽检")]
            for name in datasets
        }

    out: dict[str, list[Finding]] = {}
    checks: dict[str, Callable] = {
        "margin": _online_margin,
        "futures": _online_futures,
        "bond": _online_bond,
        "breadth": _online_breadth,
    }
    for name in datasets:
        check = checks.get(name)
        if check is None:
            continue
        try:
            findings = check(store, ak)
        except Exception as exc:  # noqa: BLE001 - online check is best effort
            findings = [
                Finding(name, "online_error", "info", f"外部抽检失败（{type(exc).__name__}: {exc}）")
            ]
        if findings:
            out[name] = findings
    return out


def _online_margin(store: PersonalStore, ak) -> list[Finding]:
    latest = _latest_date(store.get_margin_balance(limit=1))
    if latest is None:
        return []
    summary = {
        row.scope: row
        for row in store.get_margin_balance(
            start=latest, end=latest, scope_type="market"
        )
    }
    findings: list[Finding] = []
    text = latest.strftime("%Y%m%d")
    for scope, fetch, name in (
        ("沪市", ak.stock_margin_detail_sse, "上交所明细"),
        ("深市", ak.stock_margin_detail_szse, "深交所明细"),
    ):
        row = summary.get(scope)
        if row is None or not row.rzye:
            continue
        detail = fetch(date=text)
        if detail is None or detail.empty:
            continue
        column = "融资余额"
        if column not in detail.columns:
            continue
        ratio = float(detail[column].sum()) / row.rzye
        if not 0.85 <= ratio <= 1.02:
            findings.append(
                Finding(
                    "margin",
                    "online_detail_vs_summary",
                    "warn",
                    f"{latest} {name}合计/交易所汇总 = {ratio:.1%}（预期 85%-102%）",
                    latest,
                )
            )
        else:
            findings.append(
                Finding(
                    "margin",
                    "online_detail_vs_summary",
                    "info",
                    f"{latest} {name}合计/汇总 = {ratio:.1%}，交叉一致",
                    latest,
                )
            )
    return findings


def _online_futures(store: PersonalStore, ak) -> list[Finding]:
    """CFFEX official daily quotes vs our Sina main-contract snapshot."""
    latest = _latest_date(store.get_index_futures(limit=1))
    if latest is None:
        return []
    # akshare 1.20 renamed get_futures_daily -> futures_daily
    fetch = getattr(ak, "futures_daily", None) or getattr(
        ak, "get_futures_daily", None
    )
    if fetch is None:
        return [Finding("futures", "online_unavailable", "info", "akshare 无期货日行情接口")]
    frame = fetch(
        start_date=latest.strftime("%Y%m%d"),
        end_date=latest.strftime("%Y%m%d"),
        market="CFFEX",
    )
    if frame is None or frame.empty:
        return []
    stored = {
        row.symbol: row
        for row in store.get_index_futures(start=latest, end=latest)
    }
    findings: list[Finding] = []
    for symbol, row in stored.items():
        subset = frame[frame["variety"] == symbol]
        if subset.empty or not row.close:
            continue
        main = subset.loc[subset["volume"].idxmax()]
        diff = abs(float(main["close"]) - row.close) / row.close * 100
        if diff > 0.5:
            findings.append(
                Finding(
                    "futures",
                    "online_close_mismatch",
                    "warn",
                    f"{latest} {symbol} 新浪主力 {row.close:g} vs 中金所 {main['symbol']} "
                    f"{float(main['close']):g}（{diff:.2f}%）",
                    latest,
                )
            )
        else:
            findings.append(
                Finding(
                    "futures",
                    "online_close_check",
                    "info",
                    f"{latest} {symbol} 与中金所 {main['symbol']} 收盘差 {diff:.2f}%，交叉一致",
                    latest,
                )
            )
    return findings


def _online_bond(store: PersonalStore, ak) -> list[Finding]:
    latest = _latest_date(store.get_bond_yield(limit=1))
    if latest is None:
        return []
    store_rows = {
        row.trade_date: row for row in store.get_bond_yield(start=latest, end=latest)
    }
    row = store_rows.get(latest)
    if row is None or row.cn_10y is None:
        return []
    text = latest.strftime("%Y%m%d")
    frame = ak.bond_china_yield(start_date=text, end_date=text)
    if frame is None or frame.empty:
        return []
    official = frame[frame["曲线名称"] == "中债国债收益率曲线"]
    if official.empty or "10年" not in official.columns:
        return []
    value = float(official.iloc[0]["10年"])
    diff_bp = abs(value - row.cn_10y) * 100
    if diff_bp > 5:
        return [
            Finding(
                "bond",
                "online_cn10y_mismatch",
                "warn",
                f"{latest} 东财中国10Y {row.cn_10y} vs 中债官方 {value}（{diff_bp:.1f}bp）",
                latest,
            )
        ]
    return [
        Finding(
            "bond",
            "online_cn10y_check",
            "info",
            f"{latest} 中国10Y 与中债官方差 {diff_bp:.1f}bp，交叉一致",
            latest,
        )
    ]


def _online_breadth(store: PersonalStore, ak) -> list[Finding]:
    latest = _latest_date(store.get_market_breadth(limit=1))
    if latest is None:
        return []
    frame = ak.stock_market_activity_legu()
    if frame is None or frame.empty:
        return []
    values = dict(zip(frame["item"], frame["value"]))
    stamp = str(values.get("统计日期", ""))[:10]
    if stamp and stamp != latest.isoformat():
        return [
            Finding(
                "breadth",
                "online_skipped",
                "info",
                f"乐咕统计日 {stamp} 与本地最新 {latest} 不同，跳过涨跌家数比对",
                latest,
            )
        ]
    row = store.get_market_breadth(start=latest, end=latest)[0]
    findings: list[Finding] = []
    for label, local in (("上涨", row.up_count), ("下跌", row.down_count)):
        try:
            remote = float(values.get(label))
        except (TypeError, ValueError):
            continue
        if local and abs(remote - local) / local > 0.05:
            findings.append(
                Finding(
                    "breadth",
                    "online_breadth_mismatch",
                    "warn",
                    f"{latest} {label}家数 本地 {local} vs 乐咕 {remote:.0f}",
                    latest,
                )
            )
        else:
            findings.append(
                Finding(
                    "breadth",
                    "online_breadth_check",
                    "info",
                    f"{latest} {label}家数 本地 {local} vs 乐咕 {remote:.0f}，交叉一致",
                    latest,
                )
            )
    return findings


def _latest_date(rows) -> date | None:
    if not rows:
        return None
    return max(row.trade_date for row in rows)
