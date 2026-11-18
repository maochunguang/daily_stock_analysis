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
| `test_count` | 115 |
| `last_updated` | 2026-11-16 |
| `web_console` | Integrated: `python main.py --webui` → `/personal` |
| `standalone_web` | `.venv/bin/dsa-personal web --host 127.0.0.1 --port 8765` |
| `ui_patch` | `patches/0001-personal-web-integration.patch` |
| `search_patch` | `patches/0002-deepseek-news-search.patch` (DeepSeek news search) + `patches/0003-news-intel-private-hosts.patch` (self-hosted intel source gate) |
| `docker_doc` | `docs/DOCKER_PERSONAL.md` |
| `user_guide` | `docs/USER_GUIDE_PERSONAL.md` (required for every user-facing feature) |
| `roadmap` | `docs/ROADMAP_PERSONAL.md` |

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

1. In this fork, the DSA code is the repo root. DSA-side changes are confined
   to three patches: `patches/0001-personal-web-integration.patch` (personal
   page/API mount), `patches/0002-deepseek-news-search.patch` (DeepSeek news
   search provider + settings schema), and
   `patches/0003-news-intel-private-hosts.patch` (NEWS_INTEL_ALLOW_PRIVATE_HOSTS
   gate for self-hosted intel sources; applies after 0002). `docker/` packaging
   and the personal block in `.env.example` are fork-maintained directly;
   re-apply the patches and re-check these files after upstream sync. Never import upstream
   internals from personal business code.
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
| `personal/datahub/quality.py` | OHLC/duplicate/jump/cross-source/missing-day checks |
| `personal/datahub/breadth.py` | TRIN (Arms Index) bands/interpretation + easy-daily-trading snapshot import |
| `personal/datahub/market.py` | Market-level syncs: index futures + margin balance |
| `personal/datahub/sources/futures_source.py` | CFFEX main contracts (IF/IH/IC/IM) + spot index basis via AkShare |
| `personal/datahub/sources/margin_source.py` | Exchange margin summaries + per-board splits (SSE detail pagination) |
| `personal/datahub/schedule.py` | RM-05 daily scheduler: ordered dataset syncs + sync_state freshness |
| `personal/datahub/composite.py` | Composite market-state score (rolling percentiles, pro/contrarian) |
| `personal/datahub/validate.py` | RM-41 data passport: identities, ranges, trading days, jumps, cross-metric ratios, optional external spot checks |
| `personal/datahub/sources/sentiment_source.py` | Limit-up ladder stats (Eastmoney pools) |
| `personal/datahub/sources/flows_source.py` | Exchange turnover + broad ETF shares + THS sector crowding |
| `personal/datahub/sources/rates_source.py` | CN/US bond yields + restricted-release calendar |
| `personal/datahub/sources/option_source.py` | ETF-option PCR via SSE official daily stats (complete volume+OI basis, no vendor rate limit) |
| `personal/datahub/sources/cffex_source.py` | CFFEX top-20 member position rank (official GBK CSV) |
| `personal/datahub/status.py` | Derive suspension/ST/limit-up/down rows from bars/calendar/name/factors |
| `personal/datahub/sync.py` | Source fallback, bars/adjust/calendar/status sync, cross-check |
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
| `trading_calendar` | `trade_date`; open days only |
| `trading_status` | `(code, trade_date)`; suspension/ST/limit flags |
| `fund_nav` | `(code, nav_date, source)` |
| `etf_snapshot` | `(code, trade_date, source)` |
| `market_breadth` | `trade_date`; TRIN/涨跌家数/量额日汇总（量单位亿股、额单位亿元） |
| `index_futures` | `(trade_date, symbol)`; IF/IH/IC/IM close/OI/basis vs spot |
| `margin_balance` | `(trade_date, scope_type, scope)`; rzye/rqye/rzrqye/rzye_buy in yuan |
| `market_turnover` | `trade_date`; SSE/SZSE stock turnover (margin-ratio denominator) |
| `limit_up_stats` | `trade_date`; zt/first/streak/zb_rate/prev-zt carry |
| `option_pcr` | `(trade_date, underlying)`; volume PCR (50ETF/300ETF) |
| `futures_rank` | `(trade_date, symbol)`; CFFEX top-20 buy/sell/net_ratio |
| `sector_amount` | `(trade_date, board)`; THS industry amount/share |
| `etf_share` | `(trade_date, code)`; broad-ETF share snapshots (self-built series) |
| `bond_yield` | `trade_date`; CN/US 2Y/10Y + spreads (full history) |
| `restricted_summary` | `release_date`; release count/shares/MV |
| `sync_state` | `dataset`; last_run/last_ok/last_ok_date/rows/last_error freshness |
| `data_quality_event` | auto id; quality warnings/errors |
| `backtest_run` | `run_id`; config + metrics JSON |
| `backtest_trade` | run trades |
| `trade_journal` | manual trade log |

**Read rule:** `PersonalStore.get_bars()` never mixes sources. It selects one
source: among `preferred_sources`, the one with the most rows in the requested
range (priority breaks ties); otherwise the source with the most rows overall.
This prevents a short priority sync from shadowing a longer fallback series.

## CLI commands

| Command | Purpose |
|---|---|
| `python -m personal.cli.main init-db` | Create personal DB |
| `python -m personal.cli.main info` | Config, upstream capability, plugin count |
| `python -m personal.cli.main demo --days N` | Synthetic portfolio backtest |
| `python -m personal.cli.main sync --source S --code C --start D --end D` | Bars sync |
| `python -m personal.cli.main sync --dataset adjust --source tushare ...` | Adjustment factors |
| `python -m personal.cli.main sync --dataset calendar --source baostock ...` | Trading calendar |
| `python -m personal.cli.main sync --dataset status --code C ...` | Trading status |
| `python -m personal.cli.main replay --start D --end D` | Replay upstream signals |
| `python -m personal.cli.main sync --dataset futures` | CFFEX main-contract futures + basis |
| `python -m personal.cli.main sync --dataset margin` | Margin balance (market + board scopes, T+1, ≤120d/run) |
| `python -m personal.cli.main import-arms --dir D` | Import TRIN snapshots (easy-daily-trading `cache/arms_index/daily`) |
| `python -m personal.cli.main breadth --days N` | Show stored market breadth rows |
| `python -m personal.cli.main schedule --at 06:00[,12:00] [--once]` | RM-05 daily scheduler (compose service personal-sync); runs post-sync validation |
| `python -m personal.cli.main validate [--days N] [--dataset D] [--online] [--json]` | RM-41 indicator data health report |
| `python -m personal.cli.main sync --dataset futures\|margin\|turnover\|zt\|pcr\|cffex_rank\|sector\|etf_share\|bond\|release` | Market indicator datasets |
| `python -m personal.cli.main plugins` | List plugins |
| `python -m personal.cli.main web --host H --port P` | Local Web console |

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
| GET | `/api/market/breadth?days=N` | Market breadth / TRIN rows (oldest → newest) |
| GET | `/api/market/limitup?days=N` | Limit-up ladder stats |
| GET | `/api/market/pcr?days=N&underlying=` | Option PCR rows |
| GET | `/api/market/cffex-rank?days=N` | CFFEX member rank rows |
| GET | `/api/market/flows?days=N` | Margin-buy ratio + turnover + ETF shares |
| GET | `/api/market/crowding?days=N` | Industry crowding + percentiles |
| GET | `/api/market/macro?days=N` | CN/US spreads + release calendar |
| GET | `/api/market/composite` | Composite market-state score |
| GET | `/api/market/validate?days=N&online=bool` | RM-41 data health report (11 datasets, offline by default) |
| GET | `/api/market/futures?days=N` | Index futures rows (oldest → newest) |
| GET | `/api/market/margin?days=N` | Margin balance rows (oldest → newest) |
| POST | `/api/market/sync` | Sync futures/margin (default last 10 days) |
| POST | `/api/data/sync` | Sync bars / adjustment / calendar / status |
| GET | `/api/backtest/runs` | Recent runs |
| POST | `/api/backtest/demo` | Synthetic demo backtest |
| POST | `/api/backtest/replay` | Upstream signal replay |
| GET | `/api/upstream/recent` | Recent analyses/signals |
| GET | `/api/qmt/health` | QMT bridge health |

Web UI tabs: `总览` (status/coverage/runs/quality + sync freshness), `深度复盘` (card grid: data-health, composite, TRIN breadth, index futures, member rank, margin, limit-up, PCR, flows, crowding, macro — registry `apps/dsa-web/src/components/personal/ReviewCards.tsx`), `数据` (sync + coverage),
`回测` (demo/replay + metrics/SVG chart/trades), `插件`, `上游`
(analyses/signals), `QMT` (health check).

Sync request body:

```json
{
  "dataset": "bars|adjust|calendar|status",
  "source": "auto|synthetic|tushare|baostock|akshare",
  "codes": ["600519"],
  "start": "2026-01-01",
  "end": "2026-03-01",
  "cross_check": true
}
```

Backtest request bodies:

```json
{"days": 400, "save": false}
{"start": "2025-01-01", "end": "2026-11-12", "include": "both", "save": false, "adjust": "hfq"}
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

| Source | Daily bars | Adjust factors | Calendar | Name/status | Funds | Options | Notes |
|---|---|---|---|---|---|---|---|
| Tushare free | ✅ | ⚠️ 1/hour | ✅ `trade_cal` | ✅ `stock_basic` | ❌ | ✅ `opt_basic/opt_daily` | Token in `config/personal.env` |
| BaoStock | ✅ | ❌ | ✅ `query_trade_dates` | ✅ `query_stock_basic` name | ❌ | ❌ | Stable free fallback |
| AkShare | ✅ | planned | ✅ `tool_trade_date_hist_sina` | ✅ `stock_individual_info_em` | planned | planned | Optional dependency |
| Synthetic | ✅ | ❌ | derived from bars | ❌ | ❌ | ❌ | Offline demo/tests |

Trading status is derived: suspension from calendar-vs-bar gaps; ST from the
instrument name; limit prices from previous close + board rules.

## Known limitations

- Upstream DB does not exist until the upstream app runs once.
- Adjustment factors via Tushare free tier are rate-limited to 1/hour.
- Fund interfaces require Tushare 2000/5000 points or AkShare.
- Trading status is derived, not provider-native. ST detection depends on a
  name lookup; without a name, the limit percentage may be too wide. Status
  rows only cover the first-to-last bar range; trailing suspensions are not
  distinguishable from un-downloaded data.
- Cross-source validation needs a second usable source and doubles network
  calls; synthetic syncs skip it. Disable with `PERSONAL_CROSS_SOURCE_CHECK=false`.
- RM-41 validation only judges trading-day alignment inside the stored calendar
  coverage; backfill `calendar` (2 years) for full-history checks. Online
  spot checks are manual (`validate --online`) and cover margin, futures, bond
  and breadth only; turnover/PCR/sector have no usable independent second source.
  Validation history keeps only the latest snapshot (`data_quality_event`
  rows prefixed `validate:` are replaced each run).
- Snapshot-only datasets (sector amounts, ETF shares) are stamped with the last
  completed trading day; all implicit sync ends are capped at the last close so
  pre-open/partial data never enters the series.
- `market_breadth` data comes from the user's local `easy-daily-trading`
  snapshots (imported 265 days through 2026-11-17). It is not auto-refreshed;
  run `tools/arms_index.py` there and re-run `import-arms`.
- Futures/margin sync requires the optional `akshare` dependency; margin data
  is T+1 published and a run is capped at 120 days. Board rows count stock
  instruments only (gap vs market summary ≈ ETF/bond scope). Futures basis
  uses Sina main-contract series, which jumps on contract rolls.
- Backtests default to hfq (backward-adjusted) prices; limit prices are scaled
  into the same space. `none` reproduces raw-price behavior for debugging.
- Fund analytics, trade journal UI, review reports are Phase 2.
- QMT bridge is a scaffold; not tested against real 中信建投 QMT.
- Standalone web console is local-only and has no authentication (bind to
  `127.0.0.1`). The integrated `/personal-api/*` is covered by upstream auth
  middleware when `ADMIN_AUTH_ENABLED=true`.
- Integrated UI requires the upstream Python environment plus
  `cd apps/dsa-web && npm run build`; the patch must be re-applied
  after upstream sync.
- Docker image includes `personal/`, `config/`, `plugins/`; QMT bridge is
  Windows-only and cannot run in the container. Verified on macOS arm64
  (Docker Desktop 29.9.3, Compose v5.7.0): build, `/personal`, personal APIs,
  demo backtest and persistence across restart all pass. See
  `docs/DOCKER_PERSONAL.md` §10.
- WebUI-saved settings (LLM keys, `STOCK_LIST`) live in upstream's `ENV_FILE`,
  not in the DB. In Docker set `ENV_FILE` to a file on a writable volume
  (NAS: `/app/data/runtime.env`); the default `/app/.env` is container-local and
  is lost on `--force-recreate`. Never bind-mount host `.env` over `/app/.env`.
- Upstream DB `data/stock_analysis.db` is created only after the first upstream
  analysis; before that the personal page shows “上游 DSA 未生成”.

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
| `CHG-0012` | Docker/NAS deployment support |
| `CHG-0013` | Docker runtime verification on macOS arm64 |
| `CHG-0014` | Personal user guide + mandatory manual rule |
| `CHG-0015` | Adjustment-aware backtest, calendar/status sync, cross-source checks |
| `CHG-0016` | DeepSeek official web-search provider + settings schema |
