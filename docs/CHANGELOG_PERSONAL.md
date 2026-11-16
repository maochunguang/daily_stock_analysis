# Personal Layer Changelog

> Structured, AI/agent-friendly change log. Every change gets one `CHG-XXXX`
> entry with fixed headings. Do not include secrets, tokens, or account ids.

## Entry template

```md
## [YYYY-MM-DD] CHG-XXXX — Title

### Metadata
- id: CHG-XXXX
- date: YYYY-MM-DD
- status: done | in-progress | rolled-back
- area: scaffold | contracts | datahub | backtest | plugins | web | qmt | docs
- related: CHG-XXXX, issue/PR links

### Summary
One paragraph.

### Files
| Path | Change |
|---|---|

### Commands
```bash
...
```

### Verification
- `pytest`: N passed
- manual checks

### Notes / Migration
Compatibility, data migration, known issues.

### Next
Follow-up items.
```

---

## [2026-11-12] CHG-0001 — Phase 0 scaffold and upstream contracts

### Metadata
- id: CHG-0001
- date: 2026-11-12
- status: done
- area: scaffold, contracts
- related: CHG-0002

### Summary
Created the low-coupling personal layer: `personal/` package, config, CLI,
read-only upstream SQLite adapter, contract detection, and test harness. The
upstream repository was cloned to `upstream/` and pinned in `UPSTREAM_VERSION`.

### Files
| Path | Change |
|---|---|
| `personal/__init__.py` | Package/version |
| `personal/config.py` | Env/config loader, `Settings` |
| `personal/contracts/models.py` | Typed upstream records |
| `personal/contracts/upstream_db.py` | Read-only SQLite adapter |
| `personal/contracts/version.py` | Capability detection |
| `personal/cli/main.py` | CLI entry point |
| `scripts/check_contracts.py` | Contract validation |
| `scripts/sync_upstream.sh` | Upstream sync |
| `pyproject.toml` | Package, extras, pytest config |
| `README.md` | Quick start and layout |
| `UPSTREAM_VERSION` | Pinned upstream commit |

### Commands
```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m personal.cli.main info
.venv/bin/python scripts/check_contracts.py --allow-missing
```

### Verification
- `pytest`: 54 passed at final state.
- `info` reports upstream missing gracefully.
- Contract tests build a temporary upstream SQLite DB and read it.

### Notes / Migration
- `upstream/` is read-only and must not be edited.
- `personal/contracts/` is the only upstream data boundary.

### Next
Implement the personal data hub and backtest engine.

---

## [2026-11-12] CHG-0002 — Data hub: SQLite, adjustment, tradability, quality

### Metadata
- id: CHG-0002
- date: 2026-11-12
- status: done
- area: datahub
- related: CHG-0001, CHG-0006, CHG-0007

### Summary
Added the personal SQLite schema and repository, canonical models, qfq/hfq
adjustment, A-share tradability rules, and data-quality checks. Multiple
sources are retained for cross-checking; reads select one source.

### Files
| Path | Change |
|---|---|
| `personal/datahub/models.py` | `DailyBar`, `AdjustFactor`, `TradingStatus`, `FundNav`, `EtfSnapshot`, `QualityIssue` |
| `personal/datahub/store.py` | SQLite schema, upsert/read, stats, coverage |
| `personal/datahub/normalize.py` | Code/date normalization, ETF detection |
| `personal/datahub/adjust.py` | qfq/hfq adjustment |
| `personal/datahub/tradability.py` | T+1, lots, suspension, price limits |
| `personal/datahub/quality.py` | OHLC/duplicate/jump/cross-source checks |
| `personal/datahub/sources/base.py` | Source protocol, synthetic source |
| `personal/datahub/sync.py` | Fallback sync, adjust sync |

### Commands
```bash
.venv/bin/python -m personal.cli.main init-db
.venv/bin/python -m personal.cli.main sync --source synthetic \
  --code 600519 --start 2026-01-01 --end 2026-03-01
```

### Verification
- Tests: normalize, adjust, tradability, quality, store, sync.
- Synthetic sync writes bars and quality events.

### Notes / Migration
- `daily_bar` primary key includes `source`; multiple sources coexist.
- `get_bars()` must be called with `preferred_sources` in real flows to avoid
  mixing sources (fixed in CHG-0007).

### Next
Build the portfolio backtest engine.

---

## [2026-11-12] CHG-0003 — Cost-aware portfolio backtest and replay

### Metadata
- id: CHG-0003
- date: 2026-11-12
- status: done
- area: backtest
- related: CHG-0002

### Summary
Implemented FIFO portfolio accounting, A-share cost model, next-open execution,
T+1/limit/suspension checks, benchmark and performance metrics, and replay of
upstream AI advice/decision signals through the portfolio engine.

### Files
| Path | Change |
|---|---|
| `personal/backtest/costs.py` | Commission, stamp duty, transfer fee, slippage, dividend tax |
| `personal/backtest/portfolio.py` | FIFO lots, T+1 availability, cash/P&L |
| `personal/backtest/execution.py` | Next-open execution and constraints |
| `personal/backtest/engine.py` | Daily event-driven backtest |
| `personal/backtest/metrics.py` | Return/risk/trade metrics, Wilson interval |
| `personal/backtest/types.py` | `Signal`, `Trade`, `BacktestConfig`, `BacktestResult` |
| `personal/backtest/replay.py` | Advice/action mapping and replay |
| `personal/backtest/demo.py` | Shared synthetic demo |
| `CLI replay/demo` | `dsa-personal replay`, `dsa-personal demo` |

### Commands
```bash
.venv/bin/python -m personal.cli.main demo --days 400
.venv/bin/python -m personal.cli.main replay --start 2025-01-01 --end 2026-11-12
```

### Verification
- Tests: costs, portfolio, engine, metrics, replay, replay integration.
- `demo` runs end-to-end and can save `backtest_run`/`backtest_trade`.

### Notes / Migration
- Signals execute at the next day's open to avoid look-ahead and respect T+1.
- ETF sell orders are exempt from stamp duty.

### Next
Add plugins and a local UI.

---

## [2026-11-12] CHG-0004 — Plugin SDK and OBV example

### Metadata
- id: CHG-0004
- date: 2026-11-12
- status: done
- area: plugins
- related: CHG-0001

### Summary
Added a stable plugin API, manifest validation, directory discovery, isolated
loading, and an OBV indicator example. Plugins depend only on
`personal.plugins.api`.

### Files
| Path | Change |
|---|---|
| `personal/plugins/api.py` | `IndicatorPlugin`, `StrategyPlugin`, `PluginContext` |
| `personal/plugins/manifest.py` | `plugin.yaml` validation |
| `personal/plugins/registry.py` | Plugin registry |
| `personal/plugins/loader.py` | Discovery + isolated import |
| `personal/plugins/builtin/obv.py` | OBV implementation |
| `plugins/obv/plugin.yaml` | Example manifest |
| `plugins/obv/plugin.py` | Example entry |
| `personal/tests/test_plugins.py` | Loader/OBV tests |

### Commands
```bash
.venv/bin/dsa-personal plugins
```

### Verification
- Tests: manifest validation, directory load, OBV compute/summarize.

### Notes / Migration
- `api_version` is currently `1.0`; unknown versions are rejected.
- One bad plugin is reported but does not block other plugins.

### Next
Add a Web console for non-CLI operation.

---

## [2026-11-12] CHG-0005 — QMT bridge scaffold

### Metadata
- id: CHG-0005
- date: 2026-11-12
- status: done
- area: qmt
- related: CHG-0001

### Summary
Added the Windows-only QMT bridge and a stdlib macOS HTTP client. Default mode
is `mock`; `xtquant` mode is opt-in. Trading remains disabled by default.

### Files
| Path | Change |
|---|---|
| `qmt-bridge/app.py` | FastAPI bridge, mock/xtquant adapters, token auth |
| `qmt-bridge/requirements.txt` | Bridge dependencies |
| `qmt-bridge/README.md` | Setup and safety notes |
| `personal/execution/qmt_client.py` | Stdlib HTTP client |

### Commands
```bash
# on the Windows QMT machine
QMT_MODE=mock python app.py
```

### Verification
- `compileall` passes.
- Not yet tested against a real 中信建投 QMT instance.

### Notes / Migration
- `QMT_USERDATA_MINI` and `QMT_ACCOUNT_ID` are required for `xtquant` mode.
- Never expose the bridge to the public internet.

### Next
Mock HTTP contract → simulated account → small live size.

---

## [2026-11-12] CHG-0006 — Real data sources: Tushare raw HTTP, BaoStock, fallback

### Metadata
- id: CHG-0006
- date: 2026-11-12
- status: done
- area: datahub
- related: CHG-0002, CHG-0007

### Summary
Added Tushare (raw HTTP, no SDK/lxml), BaoStock, and AkShare adapters. Tushare
adapter handles rate-limit errors; BaoStock is the current free daily fallback.
Verified real bars for 600519, 000001, 510050.

### Files
| Path | Change |
|---|---|
| `personal/datahub/sources/tushare_source.py` | Raw HTTP Tushare adapter |
| `personal/datahub/sources/baostock_source.py` | BaoStock daily adapter |
| `personal/datahub/sources/akshare_source.py` | AkShare stock/ETF adapter |
| `personal/datahub/sync.py` | Source chain and fallback |
| `personal/cli/main.py` | `sync --source`, `--dataset adjust` |
| `personal/tests/test_tushare_source.py` | Parsing/permission tests |

### Commands
```bash
.venv/bin/dsa-personal sync --source auto --code 510050 \
  --start 2026-01-01 --end 2026-03-01
```

### Verification
- BaoStock: 34 bars each for 600519.SH, 000001.SZ, 510050.SH; 0 quality issues.
- Tushare vs BaoStock cross-check: 0 price/volume mismatches.
- Tushare free tier matrix:
  - `daily`, `daily_basic`, `index_daily`, `opt_basic`, `opt_daily`: available.
  - `adj_factor`: available but 1 request/hour.
  - `fund_*`, `index_weight`: no permission.

### Notes / Migration
- Do not install the `tushare` SDK; the adapter uses stdlib HTTP.
- Free Tushare fund data is unavailable; use AkShare/天天基金 or upgrade points.

### Next
Fix mixed-source reads (CHG-0007).

---

## [2026-11-12] CHG-0007 — Fix mixed-source bar reads

### Metadata
- id: CHG-0007
- date: 2026-11-12
- status: done
- area: datahub
- related: CHG-0002, CHG-0006

### Summary
`get_bars()` previously returned all sources for a code/date range, so synthetic
and real bars were interleaved (600519 showed 19 CNY and 1455 CNY in the same
series). It now selects exactly one source: `preferred_sources` first, then the
source with the most rows/latest ingest.

### Files
| Path | Change |
|---|---|
| `personal/datahub/store.py` | Source selection in `get_bars()` |
| `personal/backtest/replay.py` | Pass `preferred_sources` |
| `personal/cli/main.py` | Pass `preferred_sources` |
| `personal/tests/test_store.py` | Regression test |

### Commands
```bash
.venv/bin/python -m pytest personal/tests/test_store.py -q
```

### Verification
- Regression test inserts two sources and asserts one source is returned.
- Real-data backtest after fix produced a plausible result.

### Notes / Migration
- Existing DB rows are kept; no migration needed.
- All real read paths must pass `preferred_sources` (settings priority).

### Next
Add a Web console.

---

## [2026-11-12] CHG-0008 — Local Web console

### Metadata
- id: CHG-0008
- date: 2026-11-12
- status: done
- area: web
- related: CHG-0003, CHG-0004

### Summary
Added a local FastAPI Web console for non-CLI operation: overview, data sync,
coverage/quality, demo/replay backtest, plugins, upstream recent records, and
QMT health check. It uses plain HTML/CSS/JS (no build step) and inline SVG
charts.

### Files
| Path | Change |
|---|---|
| `personal/api/app.py` | FastAPI app and `/api/*` routes |
| `personal/api/static/index.html` | Console shell |
| `personal/api/static/style.css` | Styles |
| `personal/api/static/app.js` | Data loading, forms, SVG chart |
| `personal/cli/main.py` | `dsa-personal web` |
| `personal/tests/test_api.py` | API tests |
| `pyproject.toml` | `web` extra |

### Commands
```bash
.venv/bin/dsa-personal web --host 127.0.0.1 --port 8765
# open http://127.0.0.1:8765/
```

### Verification
- `GET /` returns 200.
- `GET /api/status` returns plugins/storage/coverage.
- `POST /api/backtest/demo` returns metrics/equity.
- Headless Chrome screenshot at 1440px verified the overview layout and data loading.
- `pytest`: 54 passed.

### Notes / Migration
- The console is local-only; no auth. Bind to `127.0.0.1`.
- It reads/writes the personal DB; upstream remains read-only.

### Next
Phase 2 fund analytics and trade journal UI.

---

## [2026-11-12] CHG-0009 — Agent documentation and changelog standard

### Metadata
- id: CHG-0009
- date: 2026-11-12
- status: done
- area: docs
- related: CHG-0001..CHG-0008

### Summary
Added `AGENTS.md`, `docs/AI_CONTEXT.md`, and this changelog. Established the
rule that every change must add a structured `CHG-XXXX` entry and update
`AI_CONTEXT.md` when architecture/contracts/commands/limitations change.

### Files
| Path | Change |
|---|---|
| `AGENTS.md` | Agent operating manual and invariants |
| `docs/AI_CONTEXT.md` | Compact machine-readable context |
| `docs/CHANGELOG_PERSONAL.md` | This file |
| `README.md` | Links to the new docs |

### Commands
```bash
.venv/bin/python -m pytest -q
```

### Verification
- `pytest`: 54 passed.
- Documentation paths checked against the repository.

### Notes / Migration
- New changes must follow the entry template at the top of this file.
- Do not include tokens or account ids in docs.

### Next
Continue with Phase 2, following the documentation rule.

---

## [2026-11-12] CHG-0010 — Integrate personal page into upstream Web UI

### Metadata
- id: CHG-0010
- date: 2026-11-12
- status: done
- area: web, upstream-patch
- related: CHG-0008, CHG-0009

### Summary
Moved the personal UI into the upstream DSA Web UI. Added a `个人扩展` sidebar
entry and `/personal` route, using upstream components/theme. Mounted the
personal FastAPI app at `/personal-api` before the SPA catch-all, so one
`python main.py --webui` starts both services. The standalone console remains
available.

### Files
| Path | Change |
|---|---|
| `upstream/api/app.py` | Mount personal app at `/personal-api` (optional, env-gated) |
| `upstream/api/middlewares/auth.py` | Protect `/personal-api/*` when auth is enabled |
| `upstream/apps/dsa-web/src/components/layout/SidebarNav.tsx` | New `个人扩展` nav item |
| `upstream/apps/dsa-web/src/components/layout/ShellHeader.tsx` | Route title/description |
| `upstream/apps/dsa-web/src/App.tsx` | `/personal` route |
| `upstream/apps/dsa-web/src/i18n/uiText.ts` | zh/en nav + route keys |
| `upstream/apps/dsa-web/src/pages/PersonalPage.tsx` | New integrated page |
| `upstream/apps/dsa-web/src/api/personal.ts` | `/personal-api` client |
| `upstream/apps/dsa-web/src/types/personal.ts` | Response types |
| `patches/0001-personal-web-integration.patch` | Reproducible upstream patch |
| `scripts/start_webui.sh` | One-command startup for the integrated UI |
| `AGENTS.md` | Patch exception + UI integration contract |
| `docs/AI_CONTEXT.md` | Entry points, prefixes, invariants |

### Commands
```bash
# one service: upstream + personal API + built UI
PYTHON_BIN=/path/to/upstream-env/bin/python scripts/start_webui.sh
# or: cd upstream && python main.py --webui

# build after editing apps/dsa-web/src
cd upstream/apps/dsa-web && npm run build

# re-apply after upstream sync
cd upstream && git apply --check ../patches/0001-personal-web-integration.patch \
  && git apply ../patches/0001-personal-web-integration.patch
```

### Verification
- `npm run build` succeeded; `PersonalPage-*.js` emitted.
- Headless Chrome verified `/personal` in the upstream dark theme: sidebar item,
  header, overview cards, coverage table, recent runs, quality panel all render.
- `/personal-api/api/status` returns 200 from a mounted parent app.
- `pytest`: 54 passed (backend unchanged).

### Notes / Migration
- This is the **only intentional upstream code change**. Keep it confined to the
  files above and regenerate the patch when they change.
- The upstream Python environment must have its own dependencies installed;
  the personal layer is imported from the repo root via `sys.path` fallback.
- `PERSONAL_API_ENABLED=false` disables the mount without breaking upstream.
- Personal API is protected by upstream auth when `ADMIN_AUTH_ENABLED=true`.

### Next
Add fund analytics and trade journal tabs to the integrated page (Phase 2).

---

## [2026-11-16] CHG-0011 — Self-contained fork and upstream sync

### Metadata
- id: CHG-0011
- date: 2026-11-16
- status: done
- area: fork, release
- related: CHG-0010

### Summary
Rebased the personal UI commit onto the latest upstream `main` (`c820915`,
18 commits ahead of the previous pinned version), then copied the full personal
extension layer into the fork so the repository is self-contained. Added fork
layout auto-detection, fork-specific config/docs, README section, gitignore
rules, and `UPSTREAM_VERSION`. Pushed `main` to
`https://github.com/maochunguang/daily_stock_analysis`.

### Files
| Path | Change |
|---|---|
| `personal/` | Full personal layer copied into the fork |
| `qmt-bridge/` | QMT bridge copied into the fork |
| `plugins/obv/` | OBV example plugin |
| `config/personal.example.env` | Fork-layout config template (direct `data/` paths) |
| `scripts/check_contracts.py` | Contract check available in the fork |
| `scripts/start_webui.sh` | Layout-aware one-command startup |
| `docs/AI_CONTEXT.md` | Fork layout note; upstream commit updated |
| `docs/CHANGELOG_PERSONAL.md` | This entry |
| `docs/EXTENSION_ASSESSMENT.md` | Assessment copied |
| `docs/PERSONAL_EXTENSION_ARCHITECTURE.md` | Architecture copied |
| `docs/PHASE01_IMPLEMENTATION.md` | Phase notes copied |
| `PERSONAL_AGENTS.md` | Agent operating manual copied |
| `patches/0001-personal-web-integration.patch` | Regenerated against `c820915` |
| `README.md` | Personal extension section |
| `.gitignore` | Ignore personal DB/config; keep example env |
| `UPSTREAM_VERSION` | `c820915ea0119b1b7952652d7fb148575400f2d9` |

### Commands
```bash
cd upstream
git fetch --depth 50 origin main
git rebase origin/main
# copy personal layer into the fork root
cd apps/dsa-web && npm run build
cd ../.. && python -m pytest personal/tests -q
git push fork main
```

### Verification
- Rebase onto `origin/main` succeeded.
- Fork-layout import check: `personal/config.py` resolves `data/stock_analysis.db`
  and `data/personal.db` in the repo root.
- `pytest personal/tests`: 54 passed.
- `npm run build`: succeeded; `PersonalPage-*.js` emitted.
- Patch regenerated against `c820915`; no secrets or personal DB staged.

### Notes / Migration
- The fork is now self-contained: DSA code at repo root, personal layer at
  `personal/`, integrated page at `/personal`, API at `/personal-api`.
- The local dev workspace remains different: it keeps the upstream clone under
  `upstream/`; `personal/config.py` auto-detects both layouts.
- `config/personal.env` and `data/personal.db` are never committed.
- Re-apply `patches/0001-personal-web-integration.patch` after future upstream
  merges, then rebuild `apps/dsa-web`.

### Next
Phase 2: fund analytics and trade journal tabs in the integrated page.
