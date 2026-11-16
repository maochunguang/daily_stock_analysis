# AI Context — DSA Personal Extension Layer

> Machine-readable context for AI agents. Keep this file factual and path-exact.
> Update it whenever architecture, contracts, commands, or limitations change.

> **Fork layout:** This is the self-contained fork. The repo root is the DSA
> upstream code; there is no `upstream/` subdirectory. The personal layer lives
> at `personal/`, the upstream DB is `data/stock_analysis.db`, and the personal
> DB is `data/personal.db`. Paths below that start with `upstream/` map to the
> repo root in this fork.

## Snapshot

| Key | Value |
|---|---|
| `personal_version` | `0.1.0` |
| `upstream_repo` | `maochunguang/daily_stock_analysis` (fork of `ZhuLinsen/daily_stock_analysis`) |
| `upstream_commit` | `c820915ea0119b1b7952652d7fb148575400f2d9` |
| `python` | 3.11 |
| `personal_db` | `data/personal.db` (SQLite, WAL) |
| `upstream_db` | `data/stock_analysis.db` (read-only) |
| `test_count` | 54 |
| `last_updated` | 2026-11-16 |
| `web_console` | Integrated: `python main.py --webui` → `/personal` |
| `standalone_web` | `.venv/bin/dsa-personal web --host 127.0.0.1 --port 8765` |
| `ui_patch` | `patches/0001-personal-web-integration.patch` |

## Purpose and boundary

The personal layer extends the upstream DSA project without modifying it. It
adds:

- A-share data quality: adjustment factors, suspension/ST/price-limit flags,
  cross-source validation.
- A cost-aware portfolio backtest engine for upstream AI advice and personal
  strategies.
- Fund analytics, trade journal, and review reports (later phases).
- A local Web console for non-CLI operation.
- A Windows QMT bridge for future execution.

**Not in scope:** institutional RBAC/multi-tenant, OMS/EMS, full VaR platform,
multi-asset derivatives beyond future ETF options.

## Architecture invariants

1. In this fork, the DSA code is the repo root. Keep DSA-side changes confined
   to the UI integration patch (`patches/0001-personal-web-integration.patch`);
   never import upstream internals from personal business code.
2. `personal/contracts/` is the only upstream data boundary.
3. Personal DB is separate from the upstream DB.
4. Plugin code may import only `personal.plugins.api`.
5. Trading is disabled by default; QMT bridge is a separate Windows service.
6. Report integration is post-processing first; upstream prompt patches are a
   last resort under `patches/`.

## Entry points

| Path | Role |
|---|---|
| `personal/cli/main.py` | CLI entry (`dsa-personal`) |
| `personal/api/app.py` | FastAPI app and `/api/*` routes |
| `personal/api/static/index.html` | Web console shell |
| `personal/api/static/app.js` | Web console logic |
| `personal/api/static/style.css` | Web console styles |
| `qmt-bridge/app.py` | Windows QMT HTTP bridge |
| `api/app.py` | Mounts personal app at `/personal-api` (patched) |
| `apps/dsa-web/src/pages/PersonalPage.tsx` | Integrated `个人扩展` page (patched) |
| `apps/dsa-web/src/components/layout/SidebarNav.tsx` | Sidebar entry (patched) |
| `patches/0001-personal-web-integration.patch` | Upstream UI integration patch |
| `scripts/check_contracts.py` | Read-only upstream contract validation |
| `scripts/start_webui.sh` | Start upstream + personal API + built UI |

## Key modules

| Module | Responsibility |
|---|---|
| `personal/config.py` | Env/config; `config/personal.env` is gitignored |
| `personal/contracts/upstream_db.py` | Read-only SQLite adapter; typed queries |
| `personal/contracts/models.py` | `AnalysisRecord`, `PortfolioAccount`, `PortfolioTradeRecord`, `DecisionSignalRecord` |
| `personal/contracts/version.py` | Capability detection and missing-contract report |
| `personal/datahub/models.py` | `DailyBar`, `AdjustFactor`, `TradingStatus`, `FundNav`, `EtfSnapshot`, `QualityIssue` |
| `personal/datahub/store.py` | SQLite schema + repository; `stats()`, `coverage()`, `get_bars()` |
| `personal/datahub/adjust.py` | qfq/hfq adjustment; Tushare `adj_factor` convention |
| `personal/datahub/tradability.py` | T+1, 100-share lots, suspension, price limits |
| `personal/datahub/quality.py` | OHLC/duplicate/jump/cross-source checks |
| `personal/datahub/sync.py` | Source fallback, `sync_daily_bars`, `sync_adjust_factors` |
| `personal/datahub/sources/` | `synthetic`, `tushare`, `akshare`, `baostock` adapters |
| `personal/backtest/costs.py` | Commission, stamp duty, transfer fee, slippage, dividend tax |
| `personal/backtest/portfolio.py` | FIFO lots, T+1 availability, cash/P&L |
| `personal/backtest/execution.py` | Next-open execution, limit/suspension checks |
| `personal/backtest/engine.py` | Daily event-driven portfolio backtest |
| `personal/backtest/metrics.py` | Return/risk/trade metrics, Wilson interval |
| `personal/backtest/replay.py` | Upstream advice/signal → backtest signals |
| `personal/backtest/demo.py` | Synthetic demo shared by CLI/Web |
| `personal/plugins/api.py` | Stable plugin protocols |
| `personal/plugins/manifest.py` | `plugin.yaml` validation |
| `personal/plugins/loader.py` | Directory discovery + isolated loading |
| `personal/execution/qmt_client.py` | Stdlib HTTP client for QMT bridge |

## Upstream DB contracts

Tables currently read:

| Table | Used columns |
|---|---|
| `analysis_history` | `id, code, name, report_type, sentiment_score, operation_advice, trend_prediction, analysis_summary, raw_result, created_at, ideal_buy, secondary_buy, stop_loss, take_profit` |
| `portfolio_accounts` | `id, name, market, base_currency, is_active, broker` |
| `portfolio_trades` | `id, account_id, symbol, trade_date, side, quantity, price, fee, tax, currency, note` |
| `decision_signals` | `id, stock_code, market, action, created_at, score, confidence, entry_low, entry_high, stop_loss, target_price, horizon, reason` |

If a table/column is missing, `personal.contracts.version.detect()` returns a
degraded capability report. The Web `/api/status` and CLI `info` surface it.

## Personal DB schema

| Table | Primary key / purpose |
|---|---|
| `daily_bar` | `(code, trade_date, source)`; raw bars from one source |
| `adjust_factor` | `(code, ex_date, source)`; cumulative share factor |
| `trading_status` | `(code, trade_date)`; suspension/ST/limit flags |
| `fund_nav` | `(code, nav_date, source)` |
| `etf_snapshot` | `(code, trade_date, source)` |
| `data_quality_event` | auto id; quality warnings/errors |
| `backtest_run` | `run_id`; config + metrics JSON |
| `backtest_trade` | run trades |
| `trade_journal` | manual trade log |

**Read rule:** `PersonalStore.get_bars()` never mixes sources. It selects one
source by `preferred_sources` (settings priority), then by row count/last
ingest. This is intentional.

## CLI commands

| Command | Purpose |
|---|---|
| `dsa-personal init-db` | Create personal DB |
| `dsa-personal info` | Config, upstream capability, plugin count |
| `dsa-personal demo --days N` | Synthetic portfolio backtest |
| `dsa-personal sync --source S --code C --start D --end D` | Bars sync |
| `dsa-personal sync --dataset adjust --source tushare ...` | Adjustment factors |
| `dsa-personal replay --start D --end D` | Replay upstream signals |
| `dsa-personal plugins` | List plugins |
| `dsa-personal web --host H --port P` | Local Web console |

## Web API

Standalone console: `/api/*` on port 8765.
Integrated upstream UI: `/personal-api/api/*` (the React page calls this prefix);
the page route is `/personal`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Web console |
| GET | `/api/health` | App health |
| GET | `/api/status` | Config, upstream, storage, coverage, plugins, runs |
| GET | `/api/plugins` | Plugin list/errors |
| GET | `/api/data/coverage` | Code/source coverage + stats |
| GET | `/api/data/quality?limit=N` | Quality events |
| POST | `/api/data/sync` | Sync bars/adjust factors |
| GET | `/api/backtest/runs` | Recent runs |
| POST | `/api/backtest/demo` | Synthetic demo backtest |
| POST | `/api/backtest/replay` | Upstream signal replay |
| GET | `/api/upstream/recent` | Recent analyses/signals |
| GET | `/api/qmt/health` | QMT bridge health |

Web UI tabs: `总览` (status/coverage/runs/quality), `数据` (sync + coverage),
`回测` (demo/replay + metrics/SVG chart/trades), `插件`, `上游`
(analyses/signals), `QMT` (health check).

Sync request body:

```json
{
  "dataset": "bars|adjust",
  "source": "auto|synthetic|tushare|baostock|akshare",
  "codes": ["600519"],
  "start": "2026-01-01",
  "end": "2026-03-01"
}
```

Backtest request bodies:

```json
{"days": 400, "save": false}
{"start": "2025-01-01", "end": "2026-11-12", "include": "both", "save": false}
```

## Plugin contract

Manifest: `plugins/<name>/plugin.yaml`

```yaml
api_version: "1.0"
name: obv
version: "0.1.0"
type: indicator
entry: plugin:OBVIndicator
requires:
  personal: ">=0.1.0"
permissions: [market_data:read]
config_schema:
  window: {type: integer, default: 20}
```

`IndicatorPlugin` methods: `compute(df, params)`, `summarize(df, params)`,
`render(summary, language)`. Plugins may import only `personal.plugins.api`.

## Data source matrix

| Source | Daily bars | Adjust factors | Funds | Options | Notes |
|---|---|---|---|---|---|
| Tushare free | ✅ | ⚠️ 1/hour | ❌ | ✅ `opt_basic/opt_daily` | Token in `config/personal.env` |
| BaoStock | ✅ | ❌ | ❌ | ❌ | Stable free daily fallback |
| AkShare | planned | planned | planned | planned | Optional dependency not installed yet |
| Synthetic | ✅ | ❌ | ❌ | ❌ | Offline demo/tests |

## Known limitations

- Upstream DB does not exist until the upstream app runs once.
- Adjustment factors via Tushare free tier are rate-limited to 1/hour.
- Fund interfaces require Tushare 2000/5000 points or AkShare.
- Trading status sync (suspension/ST/limits) is stored/supported by the engine
  but not yet batch-ingested from providers.
- Fund analytics, trade journal UI, review reports are Phase 2.
- QMT bridge is a scaffold; not tested against real 中信建投 QMT.
- Standalone web console is local-only and has no authentication (bind to
  `127.0.0.1`). The integrated `/personal-api/*` is covered by upstream auth
  middleware when `ADMIN_AUTH_ENABLED=true`.
- Integrated UI requires the upstream Python environment plus
  `cd apps/dsa-web && npm run build`; the patch must be re-applied
  after upstream sync.

## Changelog index

| ID | Summary |
|---|---|
| `CHG-0001` | Phase 0 scaffold and upstream contracts |
| `CHG-0002` | Data hub: SQLite, adjustment, tradability, quality |
| `CHG-0003` | Cost-aware portfolio backtest and replay |
| `CHG-0004` | Plugin SDK and OBV example |
| `CHG-0005` | QMT bridge scaffold |
| `CHG-0006` | Real data sources: Tushare raw HTTP, BaoStock, source fallback |
| `CHG-0007` | Fix mixed-source bar reads |
| `CHG-0008` | Local Web console |
| `CHG-0009` | Agent documentation and changelog standard |
| `CHG-0010` | Integrated upstream Web UI (`/personal`) + `/personal-api` mount |
| `CHG-0011` | Rebase onto upstream `c820915` + self-contained fork |
