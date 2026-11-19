"""RM-05: scheduled incremental syncs (daily at a fixed local time).

Runs the market datasets in order — calendar/status first (status derives
from calendar), then bars/adjust, then futures/margin — records per-dataset
freshness into ``sync_state`` and keeps going after per-dataset failures
(the next day's run retries naturally).

两融/期指/日线都是增量幂等 upsert；默认回看 10~30 天自愈缺口。
阿姆氏快照不在 NAS 上自动更新（easy-daily-trading 在本地 Mac）；配置
``--arms-dir`` 指向挂载目录时才会顺带导入。
"""

from __future__ import annotations

import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Callable, Sequence

from ..config import Settings
from .normalize import normalize_code
from .market import (
    last_completed_trade_date,
    sync_bond_yield,
    sync_etf_share,
    sync_futures_rank,
    sync_index_futures,
    sync_index_valuation,
    sync_limit_up,
    sync_margin_balance,
    sync_option_pcr,
    sync_restricted_release,
    sync_sector_amount,
    sync_turnover,
)
from .store import PersonalStore
from .sync import DataSyncService, build_sources
from .validate import validate_store

DEFAULT_DATASETS: tuple[str, ...] = (
    "calendar",
    "status",
    "bars",
    "adjust",
    "futures",
    "valuation",
    "turnover",
    "margin",
    "cffex_rank",
    "zt",
    "pcr",
    "sector",
    "etf_share",
    "bond",
    "release",
)
DEFAULT_AT = "06:00"


@dataclass(frozen=True)
class ScheduledJobResult:
    dataset: str
    ok: bool
    rows: int
    message: str
    seconds: float

    def as_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "ok": self.ok,
            "rows": self.rows,
            "message": self.message,
            "seconds": round(self.seconds, 1),
        }


def parse_at(value: str) -> dt_time:
    parts = value.strip().split(":")
    if len(parts) not in (1, 2):
        raise ValueError(f"invalid --at {value!r}; expected HH:MM")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) == 2 else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid --at {value!r}")
    return dt_time(hour=hour, minute=minute)


def parse_times(value: str) -> list[dt_time]:
    """Parse ``HH:MM`` or a comma list (``06:00,12:00``) into distinct times."""
    times: list[dt_time] = []
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        parsed = parse_at(part)
        if parsed not in times:
            times.append(parsed)
    if not times:
        raise ValueError(f"invalid --at {value!r}; expected HH:MM[,HH:MM]")
    return times


def next_run_at(now: datetime, at: dt_time) -> datetime:
    """Next local datetime matching ``at`` (tomorrow when today's passed)."""
    candidate = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def next_run_time(now: datetime, times: Sequence[dt_time]) -> datetime:
    return min(next_run_at(now, at) for at in times)


def run_scheduled_sync(
    settings: Settings,
    *,
    datasets: Sequence[str] = DEFAULT_DATASETS,
    arms_dir: str | Path | None = None,
    store: PersonalStore | None = None,
    log: Callable[[str], None] = print,
) -> list[ScheduledJobResult]:
    """Run every requested dataset once, recording sync_state per dataset."""
    own_store = store is None
    store = store or PersonalStore(settings.personal_db)
    results: list[ScheduledJobResult] = []
    today = date.today()
    codes = list(settings.stock_list)
    try:
        for dataset in datasets:
            started = time_module.monotonic()
            try:
                rows = _run_dataset(
                    settings, store, dataset, codes=codes, today=today, log=log
                )
                ok, message = True, ""
            except Exception as exc:  # noqa: BLE001 - scheduler must survive
                rows = 0
                ok = False
                message = str(exc)
            result = ScheduledJobResult(
                dataset=dataset,
                ok=ok,
                rows=rows,
                message=message,
                seconds=time_module.monotonic() - started,
            )
            if dataset != "arms" and dataset in DEFAULT_DATASETS or dataset == "arms":
                store.record_sync_state(
                    dataset,
                    ok=ok,
                    rows=rows,
                    message=message,
                    ok_date=today if ok else None,
                )
            tag = "ok" if ok else "FAILED"
            suffix = f": {message}" if message else ""
            log(
                f"[schedule] {dataset}: {tag}, {result.rows} rows "
                f"({result.seconds:.1f}s){suffix}"
            )
            results.append(result)

        _record_validation(store, log=log)

        if arms_dir:
            result = _import_arms(store, arms_dir, log=log)
            results.append(result)
    finally:
        if own_store:
            store.close()
    return results


def _record_validation(
    store: PersonalStore, *, log: Callable[[str], None], days: int = 180
) -> None:
    """Post-run offline data check, persisted for the freshness card (RM-41)."""
    from .models import QualityIssue

    try:
        report = validate_store(store, days=days)
    except Exception as exc:  # noqa: BLE001 - validation must not fail the run
        log(f"[schedule] validate: FAILED: {exc}")
        return
    issues = [
        QualityIssue(
            dataset=f"validate:{item.dataset}",
            rule=item.rule,
            severity=item.severity,
            trade_date=item.trade_date,
            detail=item.detail,
        )
        for item in report.findings
        if item.severity in ("error", "warn")
    ]
    store.clear_quality_events("validate:")
    store.record_quality_events(issues)
    log(
        f"[schedule] validate: score {report.score}, status {report.status}, "
        f"{len(issues)} issue(s)"
    )


def _run_dataset(
    settings: Settings,
    store: PersonalStore,
    dataset: str,
    *,
    codes: list[str],
    today: date,
    log: Callable[[str], None],
) -> int:
    # Only finalized sessions: at 06:00 this is yesterday, at noon still
    # yesterday, after the close it is today. Prevents pre-close/partial
    # snapshots (notably Eastmoney limit-up pools, which ignore future dates).
    as_of = last_completed_trade_date(store)
    if dataset == "valuation":
        return sync_index_valuation(store).rows
    if dataset == "futures":
        return sync_index_futures(store, start=as_of - timedelta(days=10), end=as_of).rows
    if dataset == "margin":
        # 持仓股两融：自选股 ∪ 交割单持仓 ∪ 截图账户快照持仓 ∪ 已留档代码
        # （最后一组用于回填历史上缺少名称的沪市明细行）
        codes_margin = list(
            dict.fromkeys(
                [
                    *codes,
                    *store.broker_position_codes(),
                    *store.account_position_codes(),
                    *store.margin_stock_codes(),
                ]
            )
        )
        return sync_margin_balance(
            store,
            start=as_of - timedelta(days=10),
            end=as_of,
            stock_codes=codes_margin,
        ).rows
    if dataset == "turnover":
        return sync_turnover(store, start=as_of - timedelta(days=30), end=as_of).rows
    if dataset == "zt":
        return sync_limit_up(store, start=as_of - timedelta(days=10), end=as_of).rows
    if dataset == "pcr":
        return sync_option_pcr(store, start=as_of - timedelta(days=10), end=as_of).rows
    if dataset == "cffex_rank":
        return sync_futures_rank(store, start=as_of - timedelta(days=10), end=as_of).rows
    if dataset == "sector":
        return sync_sector_amount(store).rows
    if dataset == "etf_share":
        return sync_etf_share(store).rows
    if dataset == "bond":
        return sync_bond_yield(store, start=as_of - timedelta(days=3650)).rows
    if dataset == "release":
        return sync_restricted_release(store, start=today, end=today + timedelta(days=45)).rows

    if dataset not in ("bars", "adjust", "calendar", "status"):
        raise ValueError(f"unknown dataset {dataset!r}")
    if dataset in ("bars", "adjust", "status"):
        # Personal daily bars must cover actual holdings, not just the manual
        # watchlist. Skip non-A-share codes that upstream's STOCK_LIST may hold.
        tracked = list(
            dict.fromkeys(
                [
                    *codes,
                    *store.broker_position_codes(),
                    *store.account_position_codes(),
                ]
            )
        )
        codes = [
            item
            for item in tracked
            if normalize_code(item).endswith((".SH", ".SZ", ".BJ"))
        ]
    if not codes and dataset != "calendar":
        log("[schedule] no stock list configured; skipping")
        return 0

    sources = build_sources(settings, "auto")
    service = DataSyncService(
        store,
        sources,
        cross_check=settings.cross_source_check,
        preferred_sources=settings.data_source_priority,
    )
    total = 0
    if dataset == "calendar":
        # Seed enough history for validation/gap checks, not just the edges.
        results = [
            service.sync_calendar(
                today - timedelta(days=730), today + timedelta(days=60)
            )
        ]
    elif dataset == "status":
        results = service.sync_trading_status(codes, today - timedelta(days=15), today)
    elif dataset == "adjust":
        results = service.sync_adjust_factors(codes, today - timedelta(days=30), today)
    else:
        results = service.sync_daily_bars(codes, today - timedelta(days=15), today)
    for item in results:
        if item.errors:
            raise RuntimeError("; ".join(item.errors[:3]))
        total += item.rows
    return total


def _import_arms(store: PersonalStore, arms_dir: str | Path, *, log: Callable[[str], None]) -> ScheduledJobResult:
    from .datahub.breadth import load_easy_daily_snapshots

    started = time_module.monotonic()
    directory = Path(arms_dir)
    try:
        if not directory.exists():
            raise FileNotFoundError(f"snapshots directory not found: {directory}")
        rows = list(load_easy_daily_snapshots(directory))
        count = store.upsert_market_breadth(rows)
        result = ScheduledJobResult(
            dataset="arms",
            ok=True,
            rows=count,
            message="",
            seconds=time_module.monotonic() - started,
        )
        log(f"[schedule] arms: ok, {count} rows ({result.seconds:.1f}s)")
    except Exception as exc:  # noqa: BLE001
        result = ScheduledJobResult(
            dataset="arms",
            ok=False,
            rows=0,
            message=str(exc),
            seconds=time_module.monotonic() - started,
        )
        log(f"[schedule] arms: FAILED: {exc}")
    store.record_sync_state(
        "arms",
        ok=result.ok,
        rows=result.rows,
        message=result.message,
        ok_date=date.today() if result.ok else None,
    )
    return result


def run_schedule_loop(
    settings: Settings,
    *,
    at: str = DEFAULT_AT,
    datasets: Sequence[str] = DEFAULT_DATASETS,
    arms_dir: str | Path | None = None,
    once: bool = False,
    log: Callable[[str], None] = print,
) -> None:
    """Run the syncs once (--once) or sleep to the daily time(s) and repeat."""
    run_times = parse_times(at)
    if once:
        log(f"[schedule] one-shot run (datasets: {', '.join(datasets)})")
        run_scheduled_sync(settings, datasets=datasets, arms_dir=arms_dir, log=log)
        return

    log(
        f"[schedule] daily sync at {', '.join(item.strftime('%H:%M') for item in run_times)} "
        f"(datasets: {', '.join(datasets)}); Ctrl+C to stop"
    )
    while True:
        target = next_run_time(datetime.now(), run_times)
        wait_seconds = max(1.0, (target - datetime.now()).total_seconds())
        log(f"[schedule] next run {target.isoformat(sep=' ', timespec='seconds')}")
        time_module.sleep(wait_seconds)
        try:
            run_scheduled_sync(settings, datasets=datasets, arms_dir=arms_dir, log=log)
        except Exception as exc:  # noqa: BLE001 - outer loop must survive too
            log(f"[schedule] unexpected failure: {exc}")
