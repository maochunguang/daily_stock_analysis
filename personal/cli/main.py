"""Command line entry point for the personal layer."""

from __future__ import annotations

import argparse
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

from personal.backtest.demo import DEMO_CODES, run_demo_backtest
from personal.backtest.replay import replay_upstream
from personal.backtest.types import BacktestConfig
from personal.config import get_settings
from personal.contracts.upstream_db import UpstreamDB
from personal.contracts.version import detect
from personal.datahub.store import PersonalStore
from personal.datahub.sync import DataSyncService, build_sources
from personal.plugins.loader import load_plugins


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dsa-personal", description="Personal extension layer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="create the personal SQLite database")
    subparsers.add_parser("info", help="show configuration and upstream status")

    demo = subparsers.add_parser("demo", help="run a synthetic portfolio backtest")
    demo.add_argument("--days", type=int, default=500, help="synthetic history length")
    demo.add_argument("--save", action="store_true", help="save the run to personal.db")

    subparsers.add_parser("plugins", help="list discovered plugins")

    sync = subparsers.add_parser("sync", help="sync daily bars into the personal database")
    sync.add_argument(
        "--source",
        default="auto",
        choices=("auto", "synthetic", "tushare", "baostock", "akshare"),
    )
    sync.add_argument(
        "--dataset",
        default="bars",
        choices=("bars", "adjust", "calendar", "status", "futures", "margin"),
    )
    sync.add_argument("--code", action="append", default=[])
    sync.add_argument("--start", default="")
    sync.add_argument("--end", default="")
    sync.add_argument(
        "--cross-check",
        dest="cross_check",
        action="store_true",
        default=None,
        help="compare the primary source with a second source",
    )
    sync.add_argument(
        "--no-cross-check",
        dest="cross_check",
        action="store_false",
        help="disable cross-source validation",
    )

    replay = subparsers.add_parser(
        "replay", help="replay upstream AI advice as a portfolio backtest"
    )
    replay.add_argument("--start", default="")
    replay.add_argument("--end", default="")
    replay.add_argument(
        "--include",
        default="both",
        choices=("both", "analyses", "signals"),
    )
    replay.add_argument("--save", action="store_true")

    import_arms = subparsers.add_parser(
        "import-arms",
        help="import TRIN daily snapshots from easy-daily-trading cache/arms_index/daily",
    )
    import_arms.add_argument(
        "--dir",
        default="",
        help="directory containing {date}.json snapshots (default: cache/arms_index/daily)",
    )

    breadth = subparsers.add_parser(
        "breadth", help="show stored market breadth (TRIN) rows"
    )
    breadth.add_argument("--days", type=int, default=5, help="number of recent days")

    schedule = subparsers.add_parser(
        "schedule", help="run scheduled incremental syncs daily (RM-05)"
    )
    schedule.add_argument("--at", default="06:00", help="daily run time HH:MM (default 06:00)")
    schedule.add_argument(
        "--datasets",
        default="calendar,status,bars,adjust,futures,margin",
        help="comma-separated dataset list",
    )
    schedule.add_argument(
        "--arms-dir",
        default="",
        help="optional easy-daily-trading cache/arms_index/daily to import breadth",
    )
    schedule.add_argument("--once", action="store_true", help="run all syncs now and exit")

    web = subparsers.add_parser("web", help="run the local Web console")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--reload", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()

    if args.command == "init-db":
        store = PersonalStore(settings.personal_db)
        store.close()
        print(f"personal database ready: {settings.personal_db}")
        return 0

    if args.command == "info":
        return _info(settings)

    if args.command == "demo":
        return _demo(settings, days=args.days, save=args.save)

    if args.command == "plugins":
        registry, errors = load_plugins(settings.plugin_dirs, settings.plugin_allowlist)
        print(f"plugins: {len(registry)}")
        for plugin in registry.all():
            print(f"  - {plugin.manifest.name} {plugin.manifest.version} ({plugin.manifest.type})")
        for error in errors:
            print(f"  ! {error}")
        return 0 if not errors else 1

    if args.command == "sync":
        return _sync(settings, args)

    if args.command == "replay":
        return _replay(settings, args)

    if args.command == "import-arms":
        return _import_arms(settings, args)

    if args.command == "breadth":
        return _breadth(settings, args)

    if args.command == "schedule":
        return _schedule(settings, args)

    if args.command == "web":
        return _web(args)

    return 1


def _info(settings) -> int:
    print(f"root: {settings.root}")
    print(f"upstream dir: {settings.upstream_dir}")
    print(f"upstream db: {settings.upstream_db}")
    print(f"personal db: {settings.personal_db}")
    print(f"stock list: {', '.join(settings.stock_list) or '<empty>'}")
    print(f"data source priority: {', '.join(settings.data_source_priority)}")
    print(f"backtest adjust: {settings.backtest_adjust_mode}")
    print(f"cross-source check: {settings.cross_source_check}")
    capabilities = detect(settings.upstream_db)
    print(f"upstream available: {capabilities.available}")
    print(f"analysis_history: {capabilities.has_analysis_history}")
    print(f"portfolio: {capabilities.has_portfolio}")
    print(f"decision_signals: {capabilities.has_decision_signals}")
    if capabilities.missing:
        print("contract issues:")
        for item in capabilities.missing:
            print(f"  - {item}")
    registry, errors = load_plugins(settings.plugin_dirs, settings.plugin_allowlist)
    print(f"plugins: {len(registry)} loaded, {len(errors)} failed")
    return 0


def _sync(settings, args) -> int:
    if args.dataset in ("futures", "margin"):
        return _sync_market(settings, args)
    codes = list(args.code) or list(settings.stock_list)
    if not codes and args.dataset != "calendar":
        print("no codes: pass --code or set PERSONAL_STOCK_LIST")
        return 2
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=730)
    try:
        sources = build_sources(settings, args.source)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot build data sources: {exc}")
        return 2

    cross_check = (
        settings.cross_source_check
        if args.cross_check is None
        else bool(args.cross_check)
    )
    store = PersonalStore(settings.personal_db)
    try:
        service = DataSyncService(
            store,
            sources,
            cross_check=cross_check,
            preferred_sources=settings.data_source_priority,
        )
        if args.dataset == "adjust":
            results = service.sync_adjust_factors(codes, start, end)
        elif args.dataset == "calendar":
            results = [service.sync_calendar(start, end)]
        elif args.dataset == "status":
            results = service.sync_trading_status(codes, start, end)
        else:
            results = service.sync_daily_bars(codes, start, end)
    finally:
        store.close()

    ok = 0
    for result in results:
        if result.rows:
            ok += 1
            extras = []
            if result.cross_source_issues:
                extras.append(f"{result.cross_source_issues} cross-source diffs")
            if result.missing_days:
                extras.append(f"{result.missing_days} missing days")
            if result.suspended_days:
                extras.append(f"{result.suspended_days} suspended days")
            suffix = f", {', '.join(extras)}" if extras else ""
            print(
                f"{result.code}: {result.rows} {args.dataset} rows from "
                f"{result.source} ({result.quality_issues} quality issues{suffix})"
            )
        else:
            print(f"{result.code}: FAILED")
        for error in result.errors:
            print(f"  - {error}")
    print(f"synced {ok}/{len(results)} symbols")
    return 0 if ok else 1


def _sync_market(settings, args) -> int:
    from personal.datahub.market import (
        sync_index_futures,
        sync_margin_balance,
    )

    end = date.fromisoformat(args.end) if args.end else date.today()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=10)
    store = PersonalStore(settings.personal_db)
    try:
        if args.dataset == "futures":
            result = sync_index_futures(store, start=start, end=end)
        else:
            result = sync_margin_balance(store, start=start, end=end)
    except Exception as exc:  # noqa: BLE001
        print(f"sync failed: {exc}")
        return 2
    finally:
        store.close()
    print(
        f"{result.dataset}: {result.rows} rows "
        f"({result.start} -> {result.end}, latest {result.latest_date})"
    )
    if result.message:
        print(f"note: {result.message}")
    return 0 if result.rows else 1


def _replay(settings, args) -> int:
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=365)
    db = UpstreamDB(settings.upstream_db)
    if not db.available:
        print(f"upstream database missing: {settings.upstream_db}")
        return 2

    store = PersonalStore(settings.personal_db)
    config = BacktestConfig(
        start=start,
        end=end,
        initial_cash=settings.backtest_initial_cash,
        benchmark=settings.backtest_benchmark or None,
        adjust_mode=settings.backtest_adjust_mode,
    )
    try:
        result, signals = replay_upstream(
            db,
            store,
            config,
            include_analyses=args.include in {"both", "analyses"},
            include_signals=args.include in {"both", "signals"},
            preferred_sources=settings.data_source_priority,
        )
        if args.save:
            run_id = f"replay-{uuid.uuid4().hex[:12]}"
            store.save_backtest_run(
                run_id,
                "signal_replay",
                start,
                end,
                {
                    "benchmark": settings.backtest_benchmark,
                    "signals": len(signals),
                    "include": args.include,
                },
                result.metrics,
            )
            store.save_backtest_trades(run_id, result.trades)
            print(f"saved run: {run_id}")
    except ValueError as exc:
        print(f"replay failed: {exc}")
        return 1
    finally:
        db.close()
        store.close()

    print(f"replay: {start} -> {end}, signals={len(signals)}")
    _print_metrics(result.metrics)
    print(f"final_cash={result.final_cash:.2f} positions={result.final_positions}")
    return 0


def _import_arms(settings, args) -> int:
    from personal.datahub.breadth import load_easy_daily_snapshots

    directory = Path(args.dir or Path("cache/arms_index/daily"))
    if not directory.exists():
        print(f"snapshots directory not found: {directory}")
        return 1
    rows = list(load_easy_daily_snapshots(directory))
    if not rows:
        print(f"no usable snapshots in {directory}")
        return 1
    store = PersonalStore(settings.personal_db)
    try:
        count = store.upsert_market_breadth(rows)
    finally:
        store.close()
    latest = rows[-1]
    print(f"imported {count} breadth days from {directory} (source easy_daily_trading)")
    print(f"range: {rows[0].trade_date} -> {latest.trade_date}")
    if latest.trin is not None:
        print(f"latest TRIN: {latest.trin} ({latest.band}) {latest.interpretation}")
    return 0


def _breadth(settings, args) -> int:
    store = PersonalStore(settings.personal_db)
    try:
        rows = store.get_market_breadth(limit=max(1, args.days))
    finally:
        store.close()
    if not rows:
        print("no market breadth rows; run: python -m personal.cli.main import-arms")
        return 1
    print(f"{'date':<12}{'up':>6}{'down':>6}{'TRIN':>8}{'pct%':>7}  判读")
    print("-" * 90)
    for row in rows:
        trin = f"{row.trin:.3f}" if row.trin is not None else "—"
        pct = f"{row.trin_pct:.0f}" if row.trin_pct is not None else "—"
        print(
            f"{row.trade_date.isoformat():<12}{row.up_count:>6}{row.down_count:>6}"
            f"{trin:>8}{pct:>7}  {row.interpretation}"
        )
    return 0


def _schedule(settings, args) -> int:
    from personal.datahub.schedule import run_schedule_loop

    datasets = [item.strip() for item in args.datasets.split(",") if item.strip()]
    try:
        run_schedule_loop(
            settings,
            at=args.at,
            datasets=datasets,
            arms_dir=args.arms_dir or None,
            once=bool(args.once),
        )
    except KeyboardInterrupt:
        print("\nschedule stopped")
        return 0
    except ValueError as exc:
        print(f"schedule failed: {exc}")
        return 2
    return 0


def _web(args) -> int:
    try:
        import uvicorn
    except ImportError:
        print('uvicorn is not installed; run: uv pip install -e ".[web]"')
        return 2
    print(f"personal console: http://{args.host}:{args.port}")
    uvicorn.run(
        "personal.api.app:app",
        host=args.host,
        port=args.port,
        reload=bool(args.reload),
    )
    return 0


def _print_metrics(metrics) -> None:
    for key in (
        "total_return",
        "cagr",
        "annual_vol",
        "sharpe",
        "max_drawdown",
        "calmar",
        "benchmark_return",
        "excess_return",
        "trade_count",
        "closed_trade_count",
        "win_rate",
        "profit_factor",
        "turnover",
        "total_fees",
    ):
        if key in metrics and metrics[key] is not None:
            value = metrics[key]
            if isinstance(value, float):
                print(f"  {key:22s} {value:12.4f}")
            else:
                print(f"  {key:22s} {value}")


def _demo(settings, *, days: int, save: bool) -> int:
    run = run_demo_backtest(settings, days=days)
    start, end = run.start, run.end
    result = run.result
    metrics = result.metrics
    print(f"demo backtest: {metrics['start']} -> {metrics['end']}")
    for key in (
        "total_return",
        "cagr",
        "annual_vol",
        "sharpe",
        "max_drawdown",
        "calmar",
        "benchmark_return",
        "excess_return",
        "trade_count",
        "closed_trade_count",
        "win_rate",
        "profit_factor",
        "turnover",
        "total_fees",
    ):
        if key in metrics and metrics[key] is not None:
            value = metrics[key]
            if isinstance(value, float):
                print(f"  {key:22s} {value:12.4f}")
            else:
                print(f"  {key:22s} {value}")
    print(f"  final_cash            {result.final_cash:12.2f}")
    print(f"  positions             {result.final_positions}")

    if save:
        run_id = f"demo-{uuid.uuid4().hex[:12]}"
        store = PersonalStore(settings.personal_db)
        try:
            store.save_backtest_run(
                run_id,
                "demo",
                start,
                end,
                {"codes": list(DEMO_CODES), "days": days},
                metrics,
            )
            store.save_backtest_trades(run_id, result.trades)
        finally:
            store.close()
        print(f"  saved run             {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
