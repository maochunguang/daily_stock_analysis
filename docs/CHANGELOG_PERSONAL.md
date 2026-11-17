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

---

## [2026-11-16] CHG-0012 — Docker and NAS deployment support

### Metadata
- id: CHG-0012
- date: 2026-11-16
- status: done
- area: docker, deployment
- related: CHG-0010, CHG-0011

### Summary
Made the integrated personal layer available in the upstream Docker image. The
Dockerfile now copies `personal/`, `config/` and `plugins/`, and smoke-imports
the personal API at build time. Compose sets personal paths/env defaults and
documents the optional plugin mount. Added a NAS deployment guide with SQLite,
ARM64, auth, QMT and troubleshooting notes.

### Files
| Path | Change |
|---|---|
| `docker/Dockerfile` | Copy personal/config/plugins; `import personal.api.app` build check |
| `docker/docker-compose.yml` | Personal env defaults; optional plugin hot-reload mount |
| `docs/DOCKER_PERSONAL.md` | NAS/Docker deployment guide |
| `README.md` | Link to Docker guide |
| `docs/AI_CONTEXT.md` | Docker entry/notes |
| `PERSONAL_AGENTS.md` | Docker build/up commands |

### Commands
```bash
docker compose -f docker/docker-compose.yml build server
docker compose -f docker/docker-compose.yml up -d server
```

### Verification
- Docker/Compose is not installed on the current macOS host, so the image was
  not built locally; the Compose YAML and Dockerfile COPY sources were checked
  statically.
- Personal API import path was already verified with `pytest` (54 passed) and
  the mounted-prefix test.
- On the NAS, build then check:
  `curl -f http://NAS_IP:8000/personal-api/api/health`.

### Notes / Migration
- `QMT` bridge cannot run in the NAS container (Windows-only); point
  `QMT_BRIDGE_URL` to a Windows machine or leave it unset.
- Keep `data/` on a local NAS volume or Docker volume; avoid SMB/NFS for SQLite.
- `PERSONAL_API_ENABLED=false` disables the personal API mount.
- Personal DB `data/personal.db` and upstream DB `data/stock_analysis.db` are
  both persisted under `/app/data`.

### Next
Build the image on the target NAS and run the browser smoke test.

## [2026-11-16] CHG-0013 — Docker runtime verification on macOS arm64

### Metadata
- id: CHG-0013
- date: 2026-11-16
- status: done
- area: docker, deployment, verification
- related: CHG-0012

### Summary
Built and ran the integrated image with Docker Desktop for Mac (Apple Silicon),
then verified the upstream API, the personal API mount, the `/personal` page in
a real browser, a demo backtest through the UI, and persistence across a
container restart. No code changes were needed; the image and Compose setup
worked as designed. Documentation now records the actual build/run results and
the host-port conflict workaround.

### Files
| Path | Change |
|---|---|
| `docs/DOCKER_PERSONAL.md` | Add macOS arm64 verification record; `API_PORT` override; port/build-time troubleshooting rows |
| `docs/AI_CONTEXT.md` | Replace "Docker not built locally" limitation with verified status; add CHG-0013 |
| `docs/CHANGELOG_PERSONAL.md` | This entry |

### Commands
```bash
docker --version                       # 29.9.3
docker compose version                 # v5.7.0
cp .env.example .env                   # local only, gitignored

docker compose -f docker/docker-compose.yml build server
API_PORT=8010 docker compose -f docker/docker-compose.yml up -d server

curl -f http://127.0.0.1:8010/api/health
curl -f http://127.0.0.1:8010/personal-api/api/health
curl -f http://127.0.0.1:8010/personal-api/api/status
curl -f http://127.0.0.1:8010/personal
```

### Verification
- Build succeeded on `linux/aarch64`; image `daily-stock-analysis-server:latest`
  is 2.36GB; build-time `RUN python -c "import personal.api.app"` passed.
- Container `stock-server` reported `Up (healthy)`.
- Startup log contains `Personal extension API mounted at /personal-api`.
- Endpoints: `/api/health` 200; `/personal-api/api/health` 200 with
  `{"ok":true,"version":"0.1.0"}`; `/personal-api/api/status` 200 with
  `/app/data/personal.db`; `/personal` 200 (SPA).
- Browser: upstream sidebar shows `个人扩展`; overview cards, 数据覆盖,
  最近回测, 数据质量 render; 个人回测 tab ran the demo (45 trades, metrics and
  equity curve rendered); 插件 tab lists `obv`.
- `POST /personal-api/api/backtest/demo {"save":true}` created
  `demo-b7668fe7044f`; after `docker restart stock-server` it was still returned
  by `GET /personal-api/api/backtest/runs`, proving bind-mount persistence.
- NumPy/pandas executed in the ARM64 container without OpenBLAS SIGILL.
- Container logs contain no traceback or mount failure.

### Notes / Migration
- Host port 8000 was occupied by an unrelated local service; Compose's
  `API_PORT` shell override (`API_PORT=8010`) was used. On the NAS use any free
  port.
- First build takes about 10 minutes (Qt dependencies for `wkhtmltopdf` plus pip);
  subsequent builds reuse cache.
- `data/stock_analysis.db` does not exist until the first upstream analysis, so
  the personal page correctly shows "上游 DSA 未生成".
- `.env` used for the test is gitignored and contains no real secrets.

### Next
Build on the target NAS and repeat the minimal checks in
`docs/DOCKER_PERSONAL.md` §9–§10.

## [2026-11-16] CHG-0014 — Personal user guide and mandatory manual rule

### Metadata
- id: CHG-0014
- date: 2026-11-16
- status: done
- area: docs, usability
- related: CHG-0008, CHG-0010, CHG-0012, CHG-0013

### Summary
Added `docs/USER_GUIDE_PERSONAL.md`, an end-user manual covering the integrated
`/personal` page, the standalone console, CLI commands, configuration, data
sources, backtest rules and metrics, plugin usage/development, QMT, Docker/NAS,
backup, upgrade and troubleshooting. Also made user-guide updates a hard
requirement for every future user-facing feature, in both agent manuals and the
changelog documentation rules.

### Files
| Path | Change |
|---|---|
| `docs/USER_GUIDE_PERSONAL.md` | New user manual (13 sections, page + CLI + config + rules + FAQ) |
| `PERSONAL_AGENTS.md` | Read-first list, hard invariant 9, feature table, doc rules |
| `docs/AI_CONTEXT.md` | Add `user_guide` pointer and CHG-0014 |
| `docs/CHANGELOG_PERSONAL.md` | This entry |
| `README.md` | Link the user guide in the personal docs list |

### Commands
```bash
# Validate relative links in the guide
python3 - <<'PY'
import re, pathlib
p = pathlib.Path('docs/USER_GUIDE_PERSONAL.md')
text = p.read_text()
for m in re.finditer(r'\[[^\]]+\]\(([^)]+)\)', text):
    target = m.group(1)
    if not target.startswith(('http://', 'https://', '#')):
        assert (p.parent / target.split('#')[0]).exists(), target
print('ok')
PY
```

### Verification
- Relative-link check: 5 links, 0 missing.
- Guide content cross-checked against the implementation:
  `personal/cli/main.py` (commands/options/defaults),
  `personal/config.py` (env vars/defaults/precedence),
  `personal/api/app.py` (routes and request bodies),
  `personal/datahub/sync.py` (source fallback, 730-day default),
  `personal/backtest/costs.py` (fees), `personal/backtest/metrics.py`
  (metric formulas), `personal/backtest/replay.py` (advice mapping),
  `personal/plugins/*` (manifest/protocol/loader), and
  `apps/dsa-web/src/pages/PersonalPage.tsx` (tabs/labels).
- No Python code changed; existing 54 tests and Docker verification from
  CHG-0012/CHG-0013 remain valid.

### Notes / Migration
- The guide is the single human-facing reference; `AI_CONTEXT.md` stays the
  agent-facing index.
- `PERSONAL_AGENTS.md` invariant 9 now requires a guide update in the same
  commit as any user-facing change, including the guide in the changelog
  `Files` table.
- Commands use `python -m personal.cli.main` because the self-contained fork
  does not define the `dsa-personal` console script in its `pyproject.toml`.

### Next
Extend the guide when Phase 2 adds fund NAV analytics, trade journal UI and
review reports.

## [2026-11-16] CHG-0015 — Adjustment-aware backtest, calendar/status sync, cross-source checks

### Metadata
- id: CHG-0015
- date: 2026-11-16
- status: done
- area: datahub, backtest, api, ui
- related: CHG-0002, CHG-0003, CHG-0006, CHG-0014
- roadmap: RM-01, RM-02, RM-03, RM-04

### Summary
Closed the four P0 data-correctness gaps from the roadmap. Backtests now apply
adjustment factors (default hfq) and consume derived suspension/ST/limit status;
a trading calendar table drives suspension detection and missing-day quality
events; and sync can compare the primary source with a second source.

### Files
| Path | Change |
|---|---|
| `personal/datahub/status.py` | New: derive suspension/ST/limit-up/down from bars, calendar, name, factors |
| `personal/datahub/tradability.py` | Execution checks open vs limit price; close flags no longer block (look-ahead fix) |
| `personal/datahub/store.py` | `trading_calendar` table + calendar/bar-date methods; stats count |
| `personal/datahub/sync.py` | Calendar/status sync, missing-day checks, optional cross-source validation |
| `personal/datahub/sources/tushare_source.py` | `trade_cal`, `stock_basic` name |
| `personal/datahub/sources/baostock_source.py` | `query_trade_dates`, `query_stock_basic` name |
| `personal/datahub/sources/akshare_source.py` | trade-date history, instrument name |
| `personal/backtest/types.py` | `BacktestConfig.adjust_mode` (default `hfq`) |
| `personal/backtest/engine.py` | Apply adjustment factors to bars before simulation |
| `personal/backtest/replay.py` | Load factors/status; scale limit prices into adjusted space |
| `personal/config.py` | `PERSONAL_BACKTEST_ADJUST`, `PERSONAL_CROSS_SOURCE_CHECK` |
| `personal/cli/main.py` | `--dataset calendar|status`, `--cross-check` / `--no-cross-check` |
| `personal/api/app.py` | Sync datasets calendar/status + `cross_check`; replay `adjust` |
| `personal/api/static/*` | Standalone console dataset options + cross-check checkbox |
| `apps/dsa-web/src/pages/PersonalPage.tsx` | Integrated UI dataset options, cross-check, Cross/Missing columns |
| `apps/dsa-web/src/api/personal.ts`, `types/personal.ts` | New sync fields |
| `patches/0001-personal-web-integration.patch` | Regenerated for the new sync UI |
| `config/personal.example.env`, `.env.example`, `docker/docker-compose.yml` | New env defaults |
| `docs/USER_GUIDE_PERSONAL.md` | Sync workflow, fields, backtest adjustment, limitations, FAQ |
| `docs/ROADMAP_PERSONAL.md` | New roadmap; RM-01..RM-04 marked done |
| `docs/AI_CONTEXT.md` | Modules, schema, CLI/API, data-source matrix, CHG-0015 |
| `docs/CHANGELOG_PERSONAL.md` | This entry |

### Commands
```bash
# tests
PYTHONPATH="$PWD" ../.venv/bin/python -m pytest -q personal/tests

# real calendar / bars / status
python -m personal.cli.main sync --dataset calendar --source baostock \
  --start 2026-01-01 --end 2026-03-31
python -m personal.cli.main sync --dataset bars --source baostock \
  --code 600519 --start 2026-01-01 --end 2026-03-31
python -m personal.cli.main sync --dataset status --code 600519 \
  --start 2026-01-01 --end 2026-03-31

# real adjustment factors
python -m personal.cli.main sync --dataset adjust --source tushare \
  --code 600519 --start 2025-01-01 --end 2026-03-31

# frontend + image
cd apps/dsa-web && npm run build
docker compose -f docker/docker-compose.yml build server
API_PORT=8010 docker compose -f docker/docker-compose.yml up -d server
```

### Verification
- `pytest personal/tests`: **66 passed** (was 54; +12 for adjustment, calendar,
  status derivation, cross-check, missing days, source coverage, look-ahead
  regression, API sync).
- Real BaoStock: calendar `2026-01-01..2026-03-31` → 56 open days; 600519 bars
  → 56 rows; status → 56 rows (55 with limits, 0 suspended).
- Real Tushare: 600519 `adj_factor` 2025-01-01..2026-03-31 → 299 rows;
  `trade_cal` and `stock_basic` also work on the free tier.
- Adjusted backtest smoke test: 600519 buy/sell with real factors and 1,000,000
  cash executed 2 trades, hfq prices, return +0.46%.
- Source selection now prefers the best coverage inside the requested range:
  a 5-row Tushare top-up no longer shadows a 56-row BaoStock series (regression
  test added).
- Frontend `npm run build`: success.
- Docker image rebuilt; container healthy on 8010; `/personal-api/api/status`
  shows `trading_calendar=56`, `trading_status=56`, `adjust_factor=299`;
  `POST /personal-api/api/data/sync` with `dataset=status` returned 56 rows and
  `dataset=calendar` returned 56 rows from baostock.
- Browser: `/personal` → 数据同步 shows `交易日历 Calendar`, `交易状态 Status`
  and a checked `跨源校验` box.

### Notes / Migration
- Existing personal DBs get the new `trading_calendar` table automatically on
  open (`CREATE TABLE IF NOT EXISTS`). No manual migration.
- Default backtest mode is now `hfq`; set `PERSONAL_BACKTEST_ADJUST=none` to
  reproduce raw-price results.
- Cross-source checking is on by default and doubles network calls; disable it
  with `PERSONAL_CROSS_SOURCE_CHECK=false` or the UI checkbox.
- ST detection needs an instrument name. Tushare `stock_basic` may require
  points; BaoStock/AkShare are the free fallbacks.
- Trading status is derived, not provider-native. The first bar of a series has
  no previous close, so no limit flags.

### Next
RM-05 scheduled incremental sync and RM-06 dividend/fee completion.

## [2026-11-17] CHG-0016 — DeepSeek official web-search provider + settings schema

### Metadata
- id: CHG-0016
- date: 2026-11-17
- status: done
- area: search, upstream-integration, config-ui
- related: CHG-0010, CHG-0015
- patch: patches/0002-deepseek-news-search.patch

### Summary
Added DeepSeek's official web-search API as a news-search provider. The
provider posts to `POST https://api.deepseek.com/v1/tools/search` (Bearer
auth), prefers the model-friendly `summary` field over `snippet`, maps
RFC 3339 dates to `YYYY-MM-DD`, and implements freshness via the documented
`after:` query operator (the API has no freshness parameter and a hard
128-character query limit, so queries are truncated before appending it).
`DEEPSEEK_SEARCH_API_KEYS` (comma-separated, independent from the LLM's
`DEEPSEEK_API_KEYS`) is registered in the config registry as a `data_source`
password/multi-value field, so it appears in the existing Web settings page
with the same add/remove multi-key UI as the other providers. Search priority
is now Bocha → Tavily → Brave → SerpAPI → Anspire → MiniMax → DeepSeek →
SearXNG.

### Files
| Path | Change |
|---|---|
| `src/search_service.py` | `DeepseekSearchProvider` (endpoint/auth/payload/error mapping/RetryError unwrap); `SearchService` kwarg + priority slot; singleton wiring |
| `src/config.py` | `deepseek_search_api_keys` field, `DEEPSEEK_SEARCH_API_KEYS` parsing, capability gate, validation message |
| `src/core/config_registry.py` | `DEEPSEEK_SEARCH_API_KEYS` field definition (data_source/password/multi_value, display_order 55) + help metadata |
| `apps/dsa-web/src/utils/systemConfigI18n.ts` | zh title/description for the new field |
| `.env.example` | DeepSeek search block in the search-engine section (fork-maintained file) |
| `README.md` | News-source table row |
| `docs/full-guide.md` | 搜索服务配置 table row + updated priority sentence |
| `.github/workflows/00-daily-analysis.yml` | `DEEPSEEK_SEARCH_API_KEYS` secret mapping + startup echo |
| `patches/0002-deepseek-news-search.patch` | New patch covering the DSA-side files above (verified against pristine `c820915`) |
| `tests/test_search_deepseek_provider.py` | New: query building, response mapping, count clamp, 402/timeout mapping, service wiring |
| `tests/test_deepseek_search_registry.py` | New: registry category/ui/docs/schema assertions |
| `docs/AI_CONTEXT.md`, `docs/USER_GUIDE_PERSONAL.md`, `PERSONAL_AGENTS.md` | Patch inventory, invariant update, config table row |
| `docs/CHANGELOG_PERSONAL.md` | This entry |

### Commands
```bash
# new tests + contract tests (run in the Docker container which has all deps)
docker exec -w /app stock-server python -m pytest \
  tests/test_search_deepseek_provider.py tests/test_deepseek_search_registry.py \
  --no-header -p no:cacheprovider

cd apps/dsa-web && npm run build
docker compose -f docker/docker-compose.yml build server
API_PORT=8010 docker compose -f docker/docker-compose.yml up -d server
```

### Verification
- `tests/test_search_deepseek_provider.py` (14 tests) +
  `tests/test_deepseek_search_registry.py` (5 tests): **19 passed**.
- Regression: `test_search_tavily_provider.py`, `test_search_serpapi_provider.py`,
  `test_search_searxng.py`, `test_anspire_search.py`, `test_config_registry.py`,
  `test_searxng_env_docs.py` — **93 passed** (contract tests needed
  `.env.example`/workflows/locales/docs copied into the container; the image
  intentionally omits them).
- Config wiring in container: `DEEPSEEK_SEARCH_API_KEYS=k1,k2` parses to
  `['k1','k2']`, `has_search_capability_enabled()` becomes true, and
  `get_search_service()` instantiates the `DeepSeek` provider.
- `GET /api/v1/system/config?include_schema=true` returns
  `DEEPSEEK_SEARCH_API_KEYS` under `data_source` with
  `ui_control=password`, `is_sensitive=true`, `display_order=55`.
- Browser: 设置页 → 数据源 shows `DeepSeek Search API Keys`（敏感 + 多 Key 增删，
  位于 MiniMax 之后）；截图确认样式与其他 provider 一致。
- Frontend `npm run build` and Docker image build both succeeded; container
  healthy on 8010.
- `git apply --check` on a pristine `c820915` worktree: both `0001` and `0002`
  patches apply cleanly.

### Notes / Migration
- Priority slot: DeepSeek sits after MiniMax and before SearXNG; configure
  DeepSeek keys and it is used automatically (no other provider configured →
  it is the only engine).
- Billing: DeepSeek Search charges ~¥5 per 1,000 successful requests
  (empty `results` are not billed); QPS 100 per account, 429 on excess.
- `DEEPSEEK_SEARCH_API_KEYS` is independent from `DEEPSEEK_API_KEYS`
  (LLM). The registry infers `DEEPSEEK_*` as `ai_model`, so the field is
  explicitly registered as `data_source`.
- Freshness uses the documented `after:YYYY-MM-DD` operator; DeepSeek has no
  freshness parameter and a 128-char query limit, so long queries are
  truncated before appending the operator.
- `.env.example` and `README.md` are fork-maintained (they already carry the
  personal-layer block), so they are not part of patch 0002; re-add the
  DeepSeek lines manually after an upstream sync.
- EN/繁中 translations (`README_EN/README_CHT/full-guide_EN/DEPLOY*`) were
  left unchanged in this pass.

### Next
RM-05 scheduled incremental sync; RM-06 dividend/fee completion. Optionally
add a live DeepSeek search smoke test once a funded key is configured.

## [2026-11-17] CHG-0017 — Market breadth (TRIN) data layer from easy-daily-trading

### Metadata
- id: CHG-0017
- date: 2026-11-17
- status: done
- area: datahub, web, docs
- related: CHG-0015, RM-31

### Summary
Ported the user's proven A-share TRIN (Arms Index) methodology from their
local `easy-daily-trading` project into the personal layer, and imported its
accumulated snapshots: 265 trading days (2025-10-16 ~ 2026-11-17) with
up/down/flat counts, up/down volume & amount, TRIN (volume basis) and
TRIN (amount basis), the A-share empirical percentile bands (median ≈0.78,
negative-skewed — not the US 1.0 center), 上涨占比-aware interpretation
text, and index-divergence tags against the Shanghai Composite. Data comes
from `easy-daily-trading/cache/arms_index/daily/{date}.json`; refresh is a
two-step manual flow (run `tools/arms_index.py` there, `import-arms` here).
The 深度复盘 page (TRIN + index-futures short data + margin balance) and the
futures/margin datasets are the next phase of RM-31.

### Files
| Path | Change |
|---|---|
| `personal/datahub/breadth.py` | New: `A_SHARE_BANDS`, `trin_band`, `interpret`, `percentile_of`, `compute_trin`, `load_easy_daily_snapshots` (tolerant parser, provenance `easy_daily_trading`) |
| `personal/datahub/models.py` | `MarketBreadth` dataclass (volume in 亿股, amount in 亿元 per `_yi` column convention) |
| `personal/datahub/store.py` | `market_breadth` table, `upsert_market_breadth` (idempotent by `trade_date`), `get_market_breadth(start/end/limit)`, stats count |
| `personal/cli/main.py` | `import-arms --dir`, `breadth --days` commands |
| `personal/api/app.py` | `GET /api/market/breadth?days=N` (1-500, oldest → newest) |
| `personal/tests/test_breadth.py` | New: bands/interpretation regression vs the 2026-11-17 snapshot, loader tolerance, store roundtrip/idempotency |
| `personal/tests/test_api.py` | Breadth endpoint test (empty + populated + 422 on days=0) |
| `docs/USER_GUIDE_PERSONAL.md` | §0 nav row, §5 CLI rows + example, §7.1 table row, new §7.5 口径与更新流程 |
| `docs/AI_CONTEXT.md` | test_count 76, breadth module/schema/CLI/API rows, limitation note |
| `docs/ROADMAP_PERSONAL.md` | RM-31 status: data layer done, page + futures/margin data pending |

### Commands
```bash
cd upstream
.venv/bin/python -m personal.cli.main import-arms \
  --dir /Users/mao/vibecoding/easy-daily-trading/cache/arms_index/daily
.venv/bin/python -m personal.cli.main breadth --days 3
.venv/bin/python -m pytest personal/tests -q
```

### Verification
- 265 days imported (idempotent re-import verified); latest row
  2026-11-17 TRIN 0.652 (中低位/33 pct, 上证 3584.58 −0.5%).
- `personal/tests`: 76 passed (9 new breadth + 1 API test), `compileall` OK.
- Interpretation strings byte-identical to the source project for the
  2026-11-17 snapshot (`中低位｜普跌+量能尚可 → 弱势整理`).

### Notes / Migration
- `market_breadth` is keyed by `trade_date` only — one row per day, latest
  import wins (source provenance stored per row).
- Volume/amount columns store 亿股/亿元 (rounding as produced by the source
  project); recomputing TRIN from these columns may differ in the 3rd
  decimal — always read the stored `trin` column.
- Daily refresh is manual: `python3 tools/arms_index.py --days 3` in
  easy-daily-trading, then `import-arms`. Automation lands with RM-05.

### Next
RM-31 continued: 深度复盘 page + 股指期货做空数据 + 融资余额 ingestion; RM-05
scheduled sync for automated daily refresh.


## [2026-11-17] CHG-0018 — Deep review tab: index futures + margin balance + extensible cards

### Metadata
- id: CHG-0018
- date: 2026-11-17
- status: done
- area: datahub, web, docs
- related: CHG-0017, RM-31

### Summary
Completed RM-31 with the 深度复盘 (deep review) tab in the integrated UI and the
two remaining datasets. 股指期货: CFFEX main contracts IF/IH/IC/IM via AkShare
with spot-index basis (贴水 = short pressure) and open interest + OI change,
stored per (trade_date, symbol). 融资余额: exchange summaries (沪市 via SSE
summary, 深市 via SZSE summary converted from 亿元) plus per-board splits
(沪主板/科创板/深主板/创业板) aggregated from daily per-stock detail — the SSE
detail endpoint caps pages at 2000 rows, so the source paginates with
`pageHelp.pageNo` until `pageHelp.total` is covered. Board rows count stock
instruments only; market rows use official summaries; 总计 = 沪 + 深. The
review tab renders a card registry (`REVIEW_CARDS` in
`apps/dsa-web/src/components/personal/ReviewCards.tsx`): new indicators are one
component + one registry entry, no PersonalPage changes. Ships with a
placeholder card listing planned indicators (member rankings, ETF flows,
industry-level margin).

### Files
| Path | Change |
|---|---|
| `personal/datahub/models.py` | `IndexFutures`, `MarginBalance` dataclasses |
| `personal/datahub/store.py` | `index_futures` + `margin_balance` tables, upsert/get methods, stats |
| `personal/datahub/sources/futures_source.py` | New: main-contract daily + spot closes -> basis/basis_pct/oi_chg |
| `personal/datahub/sources/margin_source.py` | New: SSE/SZSE summaries + board aggregation + SSE pagination (`classify_board`) |
| `personal/datahub/market.py` | New: `sync_index_futures` / `sync_margin_balance` (margin capped at 120 days/run) |
| `personal/cli/main.py` | `sync --dataset futures\|margin` |
| `personal/api/app.py` | `GET /api/market/futures`, `GET /api/market/margin`, `POST /api/market/sync` |
| `personal/tests/test_market.py` | New: board classification, sync roundtrips, range cap, API wiring with fake sources |
| `personal/tests/conftest.py` | Shared `client` fixture (moved from test_api.py) |
| `apps/dsa-web/src/components/personal/ReviewCards.tsx` | New: card registry + 市场宽度/期指/融资余额/占位 cards (recharts) |
| `apps/dsa-web/src/pages/PersonalPage.tsx` | `review` tab, lazy data load, market-sync refresh handlers |
| `apps/dsa-web/src/api/personal.ts`, `src/types/personal.ts` | breadth/futures/margin/marketSync client + types |
| `patches/0001-personal-web-integration.patch` | Regenerated (2060 lines), applies on pristine `c820915` |
| `docs/USER_GUIDE_PERSONAL.md` | §0 nav, §4.6 深度复盘, §5 rows, §7.1 tables, new §7.6 口径 |
| `docs/AI_CONTEXT.md`, `docs/ROADMAP_PERSONAL.md` | test_count 83, module/schema/API/CLI rows, RM-31 done |

### Commands
```bash
cd upstream
.venv/bin/python -m personal.cli.main sync --dataset futures --start 2026-11-04 --end 2026-11-17
.venv/bin/python -m personal.cli.main sync --dataset margin  --start 2026-11-10 --end 2026-11-17
.venv/bin/python -m pytest personal/tests -q
cd apps/dsa-web && npm run build
docker compose -f docker/docker-compose.yml build server && API_PORT=8010 docker compose -f docker/docker-compose.yml up -d server
```

### Verification
- 83 tests green; `compileall` OK; patch 0001 + 0002 both apply on pristine
  `c820915`; reverse check matches the fork tree.
- Real data in `personal.db`: futures 40 rows (latest 2026-11-17, IM basis
  −69.4 / −1.14%), margin 35 rows (latest 2026-11-16; 总计 22283.7 亿, boards
  沪主板 7947.4 / 深主板 5672.3 / 创业板 4548.7 / 科创板 2840.1; board sums <
  market summaries by the ETF/bond scope, as documented).
- Browser (container on :8010): 深度复盘 tab renders all cards with real data;
  TRIN 30-day curve, futures 4-line basis% chart with tooltip, margin board
  table; per-card 更新 buttons trigger `/api/market/sync` then reload.

### Notes / Migration
- Margin data is T+1 published; today's numbers appear tomorrow morning.
- `sync --dataset margin` default window is 10 days; hard cap 120 days/run
  (per-day exchange detail requests).
- Futures basis uses Sina main-contract series — values jump on contract rolls.
- Industry-level margin split and member position rankings are future cards.
- Port note: host :8000 is occupied locally; verified with `API_PORT=8010`.

### Next
RM-05 scheduled sync (auto-refresh breadth/futures/margin after close);
optional industry-level margin split card.


## [2026-11-17] CHG-0019 — Patch 0003: self-hosted news intel sources on private hosts

### Metadata
- id: CHG-0019
- date: 2026-11-17
- status: done
- area: upstream-integration, search
- related: CHG-0016
- patch: patches/0003-news-intel-private-hosts.patch

### Summary
Formalized the user's local TrendRadar change as patch 0003 (DSA-side edit,
kept out of earlier batches because it was still uncommitted work).
`NEWS_INTEL_ALLOW_PRIVATE_HOSTS=false|true` gates the intel-source SSRF guard
in `IntelligenceService._validate_url` and the DNS-guarded fetch path: when
enabled, self-hosted sources such as a local TrendRadar RSS output
(localhost / LAN addresses) are accepted; the default stays closed so the
public-internet-only protection is unchanged. Env documentation already lives
in `.env.example` (fork-maintained); the patch applies after patch 0002 on
pristine `c820915` (shared `src/config.py`).

### Files
| Path | Change |
|---|---|
| `src/services/intelligence_service.py` | `_validate_url` + DNS guard honor the config gate |
| `src/config.py` | `news_intel_allow_private_hosts` field + `NEWS_INTEL_ALLOW_PRIVATE_HOSTS` parsing |
| `patches/0003-news-intel-private-hosts.patch` | New patch (80 lines) |
| `tests/test_intel_private_hosts.py` | New: gate default-closed, private IP/localhost/LAN allowed when enabled, invalid URLs still rejected |
| `PERSONAL_AGENTS.md`, `docs/AI_CONTEXT.md` | Patch inventory now lists 0003 |
| `docs/CHANGELOG_PERSONAL.md` | This entry |

### Commands
```bash
docker cp tests/test_intel_private_hosts.py stock-server:/app/tests/
docker exec -w /app stock-server python -m pytest tests/test_intel_private_hosts.py -q
git apply --check patches/0003-news-intel-private-hosts.patch   # after 0002, on pristine c820915
```

### Verification
- 6/6 tests pass in the Docker container.
- Patch 0003 applies cleanly on a pristine `c820915` worktree with 0002
  applied first.

### Notes / Migration
- The gate is default-off; only enable on trusted LAN/NAS networks.
- Upstream sync: re-apply 0001 → 0002 → 0003 in order.

### Next
RM-05 scheduled sync (next commit).

## [2026-11-18] CHG-0020 — RM-05: daily scheduled sync (personal-sync sidecar)

### Metadata
- id: CHG-0020
- date: 2026-11-18
- status: done
- area: datahub, docker, web
- related: CHG-0017, CHG-0018, RM-05

### Summary
Added the scheduled incremental sync requested by the user ("每天 5 点或者 6
点跑这些数据", default 06:00 Asia/Shanghai, `--at` configurable). The
`personal-sync` compose sidecar shares `data/personal.db` with the server and
runs `python -m personal.cli.main schedule --at 06:00`. Per-dataset results
land in a new `sync_state` table (last run / last success / data date / rows /
error); failures are recorded and the remaining datasets still run, and the
next day's loop retries naturally. `/api/status` exposes `sync_state`; the
overview tab renders a 数据新鲜度 card. AkShare 1.19/1.20 compat handled in
the futures source (`index_zh_daily_sina` vs pre-rename
`stock_zh_index_daily`). Note: this entry's docs were accidentally applied to
the parent workspace copy during the original RM-05 commit (`d3e76a0`) and
lost in the follow-up sync; restored verbatim here alongside CHG-0021.

### Files
| Path | Change |
|---|---|
| `personal/datahub/schedule.py` | `parse_at`, `next_run_at`, `run_scheduled_sync`, `run_schedule_loop`, `--once` |
| `personal/datahub/store.py` | `sync_state` table + `record_sync_state` (failure preserves last success) |
| `personal/cli/main.py` | `schedule --at HH:MM --datasets --arms-dir --once` |
| `personal/api/app.py` | `/api/status` gains `sync_state` |
| `docker/docker-compose.yml` | `personal-sync` sidecar (06:00, shared data volume) |
| `apps/dsa-web/src/pages/PersonalPage.tsx` | 数据新鲜度 card on overview |

### Verification
- Container `schedule --once` executed all datasets against the real DB;
  freshness card browser-verified.

## [2026-11-18] CHG-0021 — P1/P2 deep-market indicator cards (RM-32..RM-40)

### Metadata
- id: CHG-0021
- date: 2026-11-18
- status: done
- area: datahub, web, docs
- related: CHG-0017, CHG-0018, CHG-0020, RM-32..RM-40

### Summary
Implemented the institutional-grade deep-market indicator set agreed with the
user (8 new datasets + composite score), all free data sources. P1: margin
trading ratio (existing data, zero new fetches), limit-up ladder / break rate
/ prev-limit-up carry (Eastmoney pools), ETF-option PCR (Tushare opt_daily,
volume basis, opt_basic cached 7 days, opt_daily rate-limited 1/min), CFFEX
top-20 member positions (official GBK CSV aggregated across all listed
contracts per product). P2: industry crowding (THS 90-board turnover share +
250-day percentile), broad-base ETF share snapshots (7 funds, self-built
series — no vendor history), CN/US yield spreads (full-history backfill,
2663 days), restricted-release calendar (next 45 days). The review tab's card
registry grows to 11 cards topped by a composite market-state score (each
metric mapped to a ~1-year rolling percentile, averaged with pro-cyclical /
contrarian direction labels, <20 samples skipped).

### Files
| Path | Change |
|---|---|
| `personal/datahub/models.py` | 8 new dataclasses (turnover/limit-up/PCR/rank/sector/ETF-share/bond/release) |
| `personal/datahub/store.py` | 8 tables + upsert/get + `_range_query`/`_upsert_generic` helpers |
| `personal/datahub/sources/sentiment_source.py` | LimitUpSource (zt/zbgc/previous pools) |
| `personal/datahub/sources/flows_source.py` | TurnoverSource + EtfShareSource + SectorSource (akshare 1.19/1.20 dual-name) |
| `personal/datahub/sources/rates_source.py` | BondSource + ReleaseSource |
| `personal/datahub/sources/option_source.py` | OptionPcrSource (raw Tushare HTTP, contract cache) |
| `personal/datahub/sources/cffex_source.py` | CffexRankSource (GBK CSV, stdlib HTTP) |
| `personal/datahub/market.py` | 8 new sync functions + range cap |
| `personal/datahub/composite.py` | Percentile engine + composite score |
| `personal/cli/main.py` | `sync --dataset` gains turnover/zt/pcr/cffex_rank/sector/etf_share/bond/release |
| `personal/api/app.py` | GET limitup/pcr/cffex-rank/flows/crowding/macro/composite + POST sync dispatch |
| `personal/datahub/schedule.py` | DEFAULT_DATASETS grows to 14 |
| `personal/tests/test_indicators.py` | 9 tests: CFFEX parse, PCR aggregation, store roundtrips, composite percentiles |
| `apps/dsa-web/src/components/personal/ReviewCards.tsx` | 7 new cards + registry (11 total) |
| `apps/dsa-web/src/pages/PersonalPage.tsx`, `api/personal.ts`, `types/personal.ts` | review data loading + types |
| `patches/0001-personal-web-integration.patch` | Regenerated (2953 lines); 0002→0003→0001 chain verified on pristine `c820915` |
| `docs/USER_GUIDE_PERSONAL.md` | §4.6 11-card table, §4.7 14-dataset table, CLI rows, §7.1 tables, §7.7 口径 |
| `docs/AI_CONTEXT.md`, `docs/ROADMAP_PERSONAL.md` | test_count 99, module/schema/API rows, RM-05 restored done + RM-32..RM-40 |

### Commands
```bash
cd upstream
.venv/bin/python -m personal.cli.main sync --dataset bond          # 2663 days
.venv/bin/python -m personal.cli.main sync --dataset turnover --start 2026-10-25 --end 2026-11-18
.venv/bin/python -m personal.cli.main sync --dataset zt --start 2026-10-25 --end 2026-11-18
.venv/bin/python -m personal.cli.main sync --dataset cffex_rank --start 2026-11-05 --end 2026-11-18
.venv/bin/python -m personal.cli.main sync --dataset sector / etf_share / release
.venv/bin/python -m personal.cli.main sync --dataset pcr            # 1/min, accumulate daily
.venv/bin/python -m pytest personal/tests -q
```

### Verification
- 99 tests green; compileall OK; patch chain applies on pristine c820915.
- Real data: limit-up (break rate 48.6% on 11-12), margin ratio 8.7%→7.58%,
  CFFEX IM net_ratio 6.8%, crowding 半导体 share 15.1%, CN-US 10Y spread
  −3.50, composite score 18.6 = 冰点/机会区 (adv_ratio component first; others
  accumulate samples). PCR backfill of 15 trading days runs at 1/min in the
  background.
- Browser: 11 cards render in the review tab (DOM-verified headings + data).

### Notes / Migration
- Crowding / ETF-share / PCR percentile series accumulate from adoption day;
  the composite card gains components as samples cross 20.
- PCR is volume-basis by design (opt_daily per-trade-date rows cover all
  traded contracts); OI PCR is a reference column only.
- THS board naming differs from Eastmoney — keep the crowding series
  single-source.
