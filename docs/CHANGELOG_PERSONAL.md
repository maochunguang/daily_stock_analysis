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

## [2026-11-18] CHG-0022 — PCR source switched to SSE official daily statistics

### Metadata
- id: CHG-0022
- date: 2026-11-18
- status: done
- area: datahub, docs
- related: CHG-0021, RM-34

### Summary
Tushare's free tier limits `opt_basic`/`opt_daily` to 1 request/hour (observed
during backfill — a 6-month history would need days of polling), so the PCR
source now uses the SSE official option daily statistics
(AkShare `option_daily_stats_sse`, one request per day, no vendor rate limit).
This is strictly better: both volume PCR and OI PCR are complete exchange
aggregates (the old OI column only covered traded contracts). The official
"认沽/认购" percentage is normalized to a ratio (/100) on ingest. Per-day
exchange loops across sentiment/cffex/flows/margin sources now sleep
0.2–0.3s between calls so long backfills stay polite.

### Files
| Path | Change |
|---|---|
| `personal/datahub/sources/option_source.py` | Rewritten on SSE official stats; Tushare token/cache logic removed |
| `personal/datahub/market.py`, `personal/datahub/schedule.py` | PCR window back to 10 days; no token wiring |
| `personal/tests/test_indicators.py` | PCR tests rewritten for the official-stats parser (100 tests) |
| `personal/datahub/sources/*` | 0.2–0.3s inter-day throttling for backfills |
| `docs/USER_GUIDE_PERSONAL.md`, `docs/AI_CONTEXT.md` | PCR source/口径 rows |

### Verification
- 100 tests green; live fetch returns 50ETF volume PCR 0.6252 (=官方 62.52%).
- 6-month backfill completes in minutes instead of days.

## [2026-11-18] CHG-0023 — RM-41: indicator data validation + cross-source spot checks

### Metadata
- id: CHG-0023
- date: 2026-11-18
- status: done
- area: datahub | web | docs
- related: CHG-0017, CHG-0018, CHG-0021, CHG-0022, RM-41

### Summary
Added a read-only validation layer for every deep-market indicator dataset.
It checks internal identities, value ranges, trading-day alignment, day-over-day
jumps, coverage gaps, cross-metric ratios (sector turnover vs market turnover,
board margin vs market total) and optionally spot-checks four independent
external sources (exchange margin details, ChinaBond official yields, CFFEX
official futures quotes, Legulegu breadth). Results are exposed via
`dsa-personal validate`, `GET /api/market/validate`, a new "数据体检" review
card, and a post-sync hook that persists findings to `data_quality_event`.

The audit that motivated this change also found and fixed two real data bugs:
- `etf_share.share_yi` stored raw fund units (份) instead of 亿份.
- Snapshot datasets (sector/ETF shares, limit-up pools) were stamped with
  `date.today()` even when fetched before the close, shifting them one day
  forward (and duplicating yesterday's limit-up pool under today).

### Files
| Path | Change |
|---|---|
| `personal/datahub/validate.py` | New: rule engine, per-dataset checkers, online spot checks, report models |
| `personal/datahub/store.py` | `clear_quality_events(prefix)` for repeatable validation snapshots |
| `personal/datahub/market.py` | `last_completed_trade_date()` + `_default_end()`; snapshot date fix; all implicit ends capped at last close |
| `personal/datahub/sources/flows_source.py` | ETF `最新份额` (份) → 亿份 conversion |
| `personal/datahub/schedule.py` | Multi-time `--at` support; post-run validation; `as_of` cap; 730-day calendar seed |
| `personal/cli/main.py` | `validate` command; schedule `--at` help |
| `personal/api/app.py` | `GET /api/market/validate`; sector/ETF snapshot date defaults |
| `apps/dsa-web/src/components/personal/ReviewCards.tsx` | `HealthCard` + registry entry + zh/en copy |
| `apps/dsa-web/src/pages/PersonalPage.tsx` | validation state/load/handler and card props |
| `apps/dsa-web/src/api/personal.ts`, `types/personal.ts` | `marketValidate` client + response types |
| `personal/tests/test_validate.py` | 14 tests: identities, ranges, cross-metric, snapshot date, ETF units, online futures check |
| `personal/tests/test_api.py` | `/api/market/validate` contract test |
| `docker/docker-compose.yml` | personal-sync runs 06:00 and 12:00 |
| `docs/USER_GUIDE_PERSONAL.md` | §4.6 数据体检, §4.7 two runs + as-of rule, §5 validate |
| `docs/DOCKER_PERSONAL.md` | NAS repair/migration steps |
| `docs/ROADMAP_PERSONAL.md` | RM-41 done |
| `patches/0001-personal-web-integration.patch` | Regenerated with the health card |

### Commands
```bash
python -m personal.cli.main validate
python -m personal.cli.main validate --dataset margin --dataset pcr --json
python -m personal.cli.main validate --online
python -m personal.cli.main schedule --once
cd apps/dsa-web && npm run build
```

### Verification
- `pytest personal/tests`: 115 passed.
- Local run against a copy of the NAS DB: 8/11 datasets `ok`; only the known
  ETF unit rows (old data) and the future-dated snapshot rows flagged `error`,
  exactly the two bugs this change fixes. After the simulated repair: 100/100.
- NAS after migration (2026-11-18 18:00): 10/11 datasets `ok`, health 95;
  only `etf_share` is `empty` because Eastmoney push2 rate-limited the IP after
  repeated runs (the 06:00 schedule fills it). Calendar backfilled with 727
  trading days (2024-01-01..2026-12-31), margin now has 11-17, zt/sector have
  real 11-18 rows.
- NAS `validate --online`: margin details 97.0%/99.1%, CFFEX four products
  0.00% close difference, ChinaBond 10Y 0.0bp, Legulegu skipped on date mismatch.
- `npm run build`: PersonalPage bundle rebuilt successfully.

### Notes / Migration
- Existing installs must delete the one-day `etf_share` / `sector_amount` rows
  and the future-dated `limit_up_stats` row, then re-sync; see
  `docs/DOCKER_PERSONAL.md` §9.
- Freshness allows one trading-day lag for every market dataset because data
  for day D is fetched by the next 06:00 run (12:00 adds late-published margin);
  a real failure is reported after two missed sessions.
- Validation only judges trading-day alignment inside the stored calendar
  coverage; backfill `calendar` (2 years) to enable full-history checks.
- Online spot checks are manual only (`--online`), never part of the scheduled
  run, to avoid extra external requests and Tushare quota use.

### Next
- Add more external comparisons when a stable second source exists (turnover,
  PCR, sector amounts).
- Consider persisting validation history (currently latest snapshot only).

## [2026-11-18] CHG-0024 — Fix WebUI config loss on container recreate (LLM keys / watchlist)

### Metadata
- id: CHG-0024
- date: 2026-11-18
- status: done
- area: docs | docker
- related: CHG-0020, CHG-0023

### Summary
The upstream WebUI persists settings (LLM keys, `STOCK_LIST`, notification and
search keys) into its active `.env` file, which defaults to `/app/.env` — inside
the container writable layer. The NAS compose only mounted `data/logs/reports`
and used the host `.env` for `${VAR}` interpolation, so every
`docker compose up --force-recreate` discarded the container-local `.env` and
the app came back with an empty watchlist and no LLM channels.

Fix: set `ENV_FILE=/app/data/runtime.env` for the server (inside the bind-mounted
`data/` volume) and seed that file once from the host `.env`. The app now reads
and writes a persistent config file; `refreshing the image` no longer touches it.
Host `.env` remains only for compose variable substitution (`TUSHARE_TOKEN`).
Binding the host `.env` over `/app/.env` is explicitly avoided because Docker
single-file mount points break the config service's atomic replace.

### Files
| Path | Change |
|---|---|
| `docker/docker-compose.yml` | `ENV_FILE=/app/data/runtime.env` for all services + precedence note |
| `docs/DOCKER_PERSONAL.md` | New §"WebUI 配置持久化": incident cause, current layout, verification, forbidden pattern |
| `docs/USER_GUIDE_PERSONAL.md` | §3.1 note on Docker WebUI config persistence |
| `docs/AI_CONTEXT.md` | Deployment limitation recorded |
| NAS `docker-compose.yml` | Server environment adds `ENV_FILE`; `data/runtime.env` seeded (host-side change) |

### Commands
```bash
# NAS (one-time migration)
cp .env data/runtime.env && chmod 600 data/runtime.env
# compose: server environment -> ENV_FILE=/app/data/runtime.env
docker compose up -d --force-recreate server
# verify
docker exec daily_stock_analysis-2 sh -c 'echo $ENV_FILE; ls -l /app/data/runtime.env'
```

### Verification
- Before: `Config.get_instance().stock_list == []`, `llm_channels == []`,
  `litellm_model == ""`, no `/app/.env` in the container.
- After seeding + recreate: `stock_list` has 11 codes, `llm_channels` has 1
  (MiniMax), `litellm_model = openai/MiniMax-M2.7-highspeed`,
  `ConfigManager().env_path = /app/data/runtime.env`.
- Wrote via the real `SystemConfigService.update()` path as the container user
  (uid 1000), then `--force-recreate` again: the 11-code watchlist and LLM
  channel/model still present.
- `runtime.env` is mode 600, owned by the app user; app can write it.

### Notes / Migration
- Keys previously entered only through the WebUI are not recoverable; the host
  `.env` (2026-05 snapshot) was used as the seed (watchlist + MiniMax channel).
  Re-enter any newer keys once in the WebUI — they now persist.
- If the same key exists in compose `env_file`/`environment`, the startup value
  overrides `runtime.env` on restart (upstream `setup_env(override=False)`);
  remove the duplicate from startup config if WebUI should win.
- The personal-sync sidecar does not need `ENV_FILE`; it uses
  `PERSONAL_STOCK_LIST` / `TUSHARE_TOKEN`.

## [2026-11-18] CHG-0025 — ETF share sync: per-symbol fallback when Eastmoney list API is blocked

### Metadata
- id: CHG-0025
- date: 2026-11-18
- status: done
- area: datahub
- related: CHG-0021, CHG-0023

### Summary
`fund_etf_spot_em` pulls all ETFs through `push2delay.eastmoney.com/api/qt/clist/get`
with pagination. After repeated backfills that endpoint started answering with
`RemoteDisconnected` (list endpoint blocked while single-security quotes still
worked), leaving `etf_share` empty. Added a fallback that asks the
single-security quote API for `f84` (总股本 = fund shares for ETFs) once per
watchlist ETF — 7 small requests instead of all pages, with one retry per symbol.
Primary path still returns all rows when available.

### Files
| Path | Change |
|---|---|
| `personal/datahub/sources/flows_source.py` | `_from_frame()` + `_from_quotes()` fallback, `_quote_share()` with retry |
| `personal/tests/test_validate.py` | fallback test (7 codes, 亿份 conversion) |
| `docs/AI_CONTEXT.md` | source row mentions the fallback |

### Commands
```bash
python -m personal.cli.main sync --dataset etf_share
```

### Verification
- Unit tests: 116 passed.
- NAS: `etf_share: 7 rows (2026-11-18)`, values 94.58–1035.51 亿份 (510050 =
  164.58 亿份), health score back to 100/100 with all 11 datasets `ok`.
- Live fallback returned 6/7 symbols before the wider cooldown; the deployed
  run returned all 7.

### Notes
- `f84`/`f85` on the quote API equal fund shares for ETFs (verified against the
  `最新份额` values from the list API).
- 0.2s spacing between symbols keeps the daily request volume modest.

## [2026-11-18] CHG-0026 — 18:00 same-day sync for the deep-review page

### Metadata
- id: CHG-0026
- date: 2026-11-18
- status: done
- area: datahub | web | docs
- related: CHG-0020, CHG-0023

### Summary
Added a third daily personal-sync run at 18:00. The 06:00/12:00 runs cap at the
last completed trading day, so same-day close data (futures basis, turnover,
limit-up ladder, PCR, member rank, ETF shares, sector amounts, bond yields)
only landed the next morning. At 18:00 (after the 15:00 close) `as_of` is today,
so the evening run brings today's close data into the deep-review page the same
night. Margin stays T+1 (published next morning) and is filled by the 12:00 run.

### Files
| Path | Change |
|---|---|
| `docker/docker-compose.yml` | personal-sync `--at 06:00,12:00,18:00` |
| NAS `docker-compose.yml` | same (host-side edit, sidecar recreated) |
| `apps/dsa-web/src/pages/PersonalPage.tsx` | freshness hint mentions the three runs |
| `docs/USER_GUIDE_PERSONAL.md` | §4.7 explains each run's purpose |
| `docs/AI_CONTEXT.md`, `docs/DOCKER_PERSONAL.md` | schedule rows updated |

### Commands
```bash
python -m personal.cli.main schedule --once   # immediate full round
```

### Verification
- Manual `schedule --once` at 22:30 (2026-11-18): breadth/futures/turnover/zt/
  pcr/rank/sector/etf_share/bond all dated 2026-11-18 (futures basis IC -1.40%,
  zt 41 家/炸板率 36.92%/4 板, PCR 50ETF 0.525), margin 2026-11-17 (T+1, expected);
  post-run validation score 100.
- Imported the same-day TRIN snapshot from easy-daily-trading (0.463 偏低) via
  `import-arms` after copying the cache JSON to `data/arms_daily/daily/`.
- Sidecar recreated and shows "next run 2026-11-19 06:00:00".

### Notes
- ETF share returned 0 rows in this run (Eastmoney still blocking the list
  endpoint from this IP); the 11-18 rows synced earlier remain in the table and
  the fallback retries on later runs.

## [2026-11-18] CHG-0027 — Broker ledger: statement import, decision snapshots, per-stock margin

### Metadata
- id: CHG-0027
- date: 2026-11-18
- status: done
- area: datahub | web | docs
- related: RM-12, RM-15, RM-42, CHG-0023

### Summary
Three capabilities that turn the market-monitor layer into a personal operating
system:

1. **交割单导入** (`personal/datahub/broker.py`): parses broker deal statements
   (CSV/TSV/XLSX, GBK/UTF-8 auto-detected) via a broad header-alias map plus
   explicit `column_map` overrides; normalizes sides (buy/sell/dividend/interest/
   fee/other; zero-qty rows like 配号/申购 never enter positions); sums fee
   columns; dedupes by row hash. Positions use moving-average cost including
   fees, with realized P&L and oversell warnings.
2. **决策快照** (`personal/datahub/decision.py`): every imported buy/sell gets a
   journal entry whose `snapshot` JSON records the market state at that trade —
   composite score + component percentiles (as of that date), TRIN band,
   limit-up structure, sector crowding top-1, turnover, and the stock's own
   margin balance with its 5-period change.
3. **持仓股两融 (RM-42)**: the exchange detail rows (previously aggregated into
   board rows and discarded) are now also kept per stock for
   `自选股 ∪ 交割单持仓`; synced with the margin dataset using the same per-day
   requests, exposed via `/api/margin/stocks` and a new review card.

New UI: `/personal` → **账本** tab (import / positions / journal with snapshot
chips) and the 持仓股两融 review card.

### Files
| Path | Change |
|---|---|
| `personal/datahub/models.py` | `BrokerTrade`, `BrokerPosition`, `MarginStockRow` |
| `personal/datahub/store.py` | `broker_trade`/`broker_position`/`margin_stock` tables; `trade_journal` column migration (`source`/`snapshot`/`broker_trade_id`); accessors |
| `personal/datahub/broker.py` | New: parser, classifier, cost engine, import pipeline |
| `personal/datahub/decision.py` | New: `snapshot_market_state()` |
| `personal/datahub/sources/margin_source.py` | `fetch_margin_all(start, end, stock_codes)` + SSE/SZSE stock-row extractors |
| `personal/datahub/market.py` | `sync_margin_balance(..., stock_codes)` upserts `margin_stock` |
| `personal/datahub/schedule.py`, `personal/api/app.py` | margin dataset passes `自选股 ∪ 持仓` codes |
| `personal/api/app.py` | `/api/broker/import` (JSON base64 body), `/api/broker/positions`, `/api/broker/journal`, `/api/margin/stocks` |
| `personal/cli/main.py` | `broker-import` / `broker-positions` / `journal`; margin sync accepts `--code` |
| `apps/dsa-web/src/components/personal/LedgerPanel.tsx` | New 账本 tab panel |
| `apps/dsa-web/src/components/personal/ReviewCards.tsx` | `MarginStocksCard` + registry + copy |
| `apps/dsa-web/src/pages/PersonalPage.tsx`, `api/personal.ts`, `types/personal.ts` | ledger tab, marginStocks slice, client methods, types |
| `personal/tests/test_broker.py` | 12 tests: parse/classify/cost/dedupe/snapshot/API |
| docs | guide §4.8 + card table, AI_CONTEXT, roadmap RM-12/15/42 |

### Commands
```bash
python -m personal.cli.main broker-import --file 交割单.csv
python -m personal.cli.main broker-positions
python -m personal.cli.main journal --days 60 --code 600519
python -m personal.cli.main sync --dataset margin --code 600519 --code 300274
cd apps/dsa-web && npm run build
```

### Verification
- `pytest personal/tests`: 128 passed.
- End-to-end smoke on a synthetic 中信建投-style statement (GBK CSV, 8 rows):
  sides/fee sums correct; 600519 realized 5687.94 (= 155764.44 − 150076.5),
  300274 remains 200 @ 80.044 avg, dividend 842 booked; re-import is idempotent
  (journal unchanged); journal snapshot contains breadth/limit_up/sector_top for
  the trade date.
- `npm run build` passes with the new tab and card.

### Notes / Migration
- Quantity unit is 股; statements exported in 手 need conversion before import.
- Statement rows without 日期/代码 are skipped and reported.
- Per-stock margin covers SSE/SZSE listed 融资标的 only; SSE rows have no 融券余额
  column in the public detail (kept null).
- Importing fills history for the snapshot only as far as stored indicator data
  allows; earlier missing legs are null, not fabricated.

### Next
- Manual journal entries with reason editing; link analyses/decision signals.
- Per-stock daily bars so the ledger can show market value.
- Margin-stock history backfill for newly imported holdings (120-day chunks).

## [2026-11-19] CHG-0028 — Trade plans, portfolio risk, and D+N decision outcomes

### Metadata
- id: CHG-0028
- date: 2026-11-19
- status: done
- area: analytics | datahub | web | docs
- related: RM-11, RM-43, RM-44, CHG-0027, CHG-0029

### Summary
Adds the missing pre-trade and post-trade decision loop:

1. **Trade plans** (`trade_plan`): price-range entry, stop/target, risk budget
   (percent or fixed amount), max position, requested quantity, thesis,
   catalyst, invalidation, horizon, status, and optional account snapshot.
   Broker statement imports can link matching fills via `trade_journal.plan_id`;
   plan lists show fill count, cumulative quantity, VWAP and last fill.
2. **Risk preview** (`analytics/trade_plans.py`): pure read-only calculation
   using the latest/selected account snapshot. Buy plans use the range high,
   stop-exit fees, whole lots, risk budget, cash, and max position (including an
   existing same-code holding). Sell plans cap at snapshot available quantity.
   Returns planned loss, risk-used %, reward/risk, post-trade cash/weight/Top5,
   warnings and blockers. Saving re-runs preview and rejects blockers.
3. **Portfolio risk** (`analytics/portfolio_risk.py`): snapshot-based cash,
   stock/ETF mix, Top1/Top5, HHI, 60-day beta, covariance volatility, top
   correlations, 20-day liquidity/exit days. Local-bar coverage is explicit;
   coverage below 80% is labeled incomplete. Snapshot >7 days warns.
4. **Decision outcomes** (`analytics/journal_outcomes.py`): D+1/5/20/60 using the
   Nth bar strictly after the trade date, adjusted entry price, benchmark
   excess, MAE/MFE, sell-side aligned direction, plan entry range/quantity
   deviation, market-state context, completed/pending/unavailable states, and
   Wilson intervals. No outcome table: results are recalculated on demand.
5. **UI**: new `交易计划` and `决策结果` tabs; risk card; plan editor drawer;
   outcome summary/table/detail drawer. Ledger import gains optional plan link.

No continuous account NAV/TWR/XIRR: snapshots are point-in-time observations.

### Files
| Path | Change |
|---|---|
| `personal/datahub/models.py` | `AccountSnapshot`, `AccountPositionSnapshot`, `TradePlan` |
| `personal/datahub/store.py` | account snapshot/position snapshot/trade-plan schema; `trade_journal.plan_id` migration; CRUD/fill progress |
| `personal/analytics/trade_plans.py` | New: fee-aware risk-budget sizing and post-trade preview |
| `personal/analytics/portfolio_risk.py` | New: concentration, Beta/volatility/correlation/liquidity with coverage |
| `personal/analytics/journal_outcomes.py` | New: D+N/MAE/MFE/benchmark/plan-vs-fill analytics |
| `personal/datahub/broker.py` | optional `plan_id`; matching code/side fills only |
| `personal/config.py` | OCR + risk thresholds (`PERSONAL_OCR_*`, `PERSONAL_RISK_*`) |
| `personal/api/app.py` | snapshot/risk/plan/outcome routes; broker import `plan_id` |
| `personal/cli/main.py` | `plans`, `journal-outcomes`, broker `--plan-id` |
| `apps/dsa-web/src/components/personal/TradePlanPanel.tsx` | New |
| `apps/dsa-web/src/components/personal/TradePlanEditor.tsx` | New |
| `apps/dsa-web/src/components/personal/PortfolioRiskCard.tsx` | New |
| `apps/dsa-web/src/components/personal/DecisionOutcomePanel.tsx` | New |
| `apps/dsa-web/src/pages/PersonalPage.tsx`, `api/personal.ts`, `types/personal.ts` | tabs, client methods, types |
| `personal/tests/test_trade_plans.py`, `test_portfolio_risk.py`, `test_journal_outcomes.py`, `test_plan_api.py` | 24 tests |
| `apps/dsa-web/src/api/__tests__/personal.test.ts` | client tests |
| `docs/USER_GUIDE_PERSONAL.md` | §4.9, §4.10, §4.8 plan link, CLI/env/tables |
| docs | AI_CONTEXT, ROADMAP, architecture |

### Commands
```bash
python -m personal.cli.main plans --status active
python -m personal.cli.main journal-outcomes --horizon 20 --days 365
python -m personal.cli.main broker-import --file 交割单.csv --plan-id 3
cd apps/dsa-web && npm run build
```

### Verification
- `pytest personal/tests`: 163 passed (includes real OCR smoke).
- New backend tests cover fee-aware sizing, min commission, lot rounding,
  existing-position cap, sell availability, preview no-write, concentration,
  Beta/vol, D+N bar selection, buy/sell MAE/MFE, splits, pending/unavailable,
  benchmark missing, plan comparison, Wilson summary, API routes and error paths.
- Real API E2E with a generated Tonghuashun-style PNG: OCR parsed equity +
  two holdings, confirmed snapshot, created a plan with 9,900 suggested shares
  and no blockers, risk endpoint returned Top1/cash, plan list persisted.
- `npm run build` passes; changed-file ESLint passes; new Vitest tests 5 pass.
- Full Vitest suite: 1,385 passed, 2 pre-existing unrelated failures
  (`DesktopUpdateIndicator` native `title` governance; DecisionSignalsPage
  timeline refresh test). Not caused by these files.

### Notes / Migration
- Old DBs get `trade_journal.plan_id` via `_migrate`; new tables use `IF NOT EXISTS`.
- Plans require a confirmed account snapshot for preview/save; otherwise 400.
- Plan status is user-maintained; linked fills do not auto-close a plan.
- Portfolio risk and outcomes use local bars only and never fetch fallback data.
- Screenshot snapshots are separate from statement positions; no overwrite.
- Per-stock margin sync covers `watchlist ∪ broker_position ∪ latest account
  snapshot`, so screenshot-only holdings also get margin detail.
- Personal settings now read Docker/WebUI `ENV_FILE` and fall back to upstream
  `STOCK_LIST` when `PERSONAL_STOCK_LIST` is empty. Daily bars/status/adjust
  sync covers watchlist ∪ broker positions ∪ latest snapshot holdings, so
  screenshot-only holdings get local bars for risk/outcomes without a manual
  code list.

### Next
- Manual journal entry/edit and outcome mistake tags.
- Finish RM-11 attribution/industry exposure; then strategy executor/walk-forward.
- Automated daily/weekly review reports and actionable alerts.

## [2026-11-19] CHG-0029 — Tonghuashun screenshot OCR account snapshots

### Metadata
- id: CHG-0029
- date: 2026-11-19
- status: done
- area: datahub | web | docker | docs
- related: RM-45, CHG-0028

### Summary
Adds local-only Tonghuashun screenshot import for the real account input the user
will use. PNG/JPEG/WebP/HEIC/HEIF up to 8MB are decoded with Pillow (+
`pillow-heif`), OCR’d with bundled RapidOCR ONNX models, and parsed into an
**editable draft** (account totals + holdings rows). Confirmation writes
`account_snapshot` / `account_position_snapshot`; the image, raw OCR text, full
account number and original account id are never stored or logged. Manual entry
uses the same form if OCR is unavailable.

Parsing handles:
- account aliases 总资产/可用资金/现金/持仓市值 and nearest numeric value;
- holdings header detection by code/name/quantity/available/cost/price/value/P&L;
- OCR coordinate-based row grouping and column assignment;
- `1,234.56`, `1.23万`, `1.23亿`, and OCR comma/dot confusion such as
  `123.456.78` → `123456.78`;
- missing account fields with explicit derivation warnings (cash+market value,
  etc.);
- same alias+date re-confirm replaces that day’s snapshot; positions are atomic.

Docker adds `libgl1`, `libglib2.0-0`, `libgomp1`; requirements add Pillow,
pillow-heif and `rapidocr-onnxruntime`. Models are bundled in the wheel and
verified local (no runtime download).

### Files
| Path | Change |
|---|---|
| `personal/datahub/screenshot.py` | New: image decode/limits, RapidOCR adapter, account/table parser, draft validation/confirm |
| `personal/datahub/models.py`, `store.py` | account snapshot tables + accessors |
| `personal/api/app.py` | `/api/account-snapshots/parse`, confirm/latest/list |
| `personal/cli/main.py` | `account-import --file ... [--save]` |
| `apps/dsa-web/src/components/personal/TonghuashunImport.tsx` | Upload → preview → editable rows → confirm; latest snapshot view; manual entry |
| `apps/dsa-web/src/components/personal/LedgerPanel.tsx` | Mount screenshot import and plan link |
| `requirements.txt`, `docker/Dockerfile` | OCR dependencies/runtime libs |
| `personal/tests/test_screenshot_import.py`, `test_screenshot_ocr_smoke.py` | Parser/confirmation + real OCR smoke |
| `apps/dsa-web/src/components/personal/__tests__/TonghuashunImport.test.tsx` | Manual-entry/confirm and empty state |
| `docs/USER_GUIDE_PERSONAL.md` | §4.8.1, env, tables, limitations |
| docs | CHANGELOG, AI_CONTEXT, ROADMAP, architecture, `.env.example`, `config/personal.example.env` |

### Commands
```bash
python -m personal.cli.main account-import --file 同花顺.png
python -m personal.cli.main account-import --file 同花顺.png --as-of 2026-11-19 --save
cd apps/dsa-web && npm run build
```

### Verification
- Real OCR smoke on a generated 980×260 Chinese Tonghuashun-style holdings
  screenshot: 总资产 1,234,567.89, 可用资金 123,456.78, 600519 100 股 @1500 /
  现价 1600 / 市值 160000 / 盈亏 10000 all parsed correctly; OCR confidence
  ~0.996-0.999.
- OCR model files verified inside site-packages (`ch_PP-OCRv4_det/rec`,
  classifier), so initialization is offline.
- API E2E with the same image: parse 200, confirm 200, snapshot positions 2;
  resulting portfolio risk top1 12.96%, cash 10%.
- `pytest`: 163 passed; `npm run build` passes; changed-file ESLint passes;
  manual-entry Vitest passes.
- Full frontend suite has the same two pre-existing unrelated failures noted in
  CHG-0028.

### Notes / Migration
- HEIC support requires `pillow-heif`; if missing, use PNG/JPEG or manual entry.
- OCR is intentionally a draft, never auto-confirm; account numbers are ignored.
- Screenshot snapshots are not continuous NAV; risk uses latest snapshot.
- `_load_image` caps file size; API strict-validates base64.
- Docker image grows by OCR/OpenCV/ONNX dependencies (~100MB+).

### Next
- Optional multiple account aliases and reconciliation against statement-derived
  positions (explicitly user-confirmed, never automatic overwrite).
- OCR aliases for more brokers/apps; screenshot date/account metadata detection.
- Continuous cash/NAV import (CSV/QMT) for TWR/XIRR in a later batch.

## [2026-11-19] CHG-0030 — Index valuation percentile card for deep review

### Metadata
- id: CHG-0030
- date: 2026-11-19
- status: done
- area: datahub | analytics | web | docs
- related: RM-46, CHG-0018, CHG-0023

### Summary
Added a deep-review card that shows daily PE-TTM and trailing 1/3/5-year
percentiles for 沪深300 (`000300.SH`), 创业板指 (`399006.SZ`), 创业板50
(`399673.SZ`) and 科创50 (`000688.SH`). The free Legulegu endpoint only exposes
daily history to paid users, so the stored series is **weekly** (about 52
points/year, 156/3y, 260/5y); the current week keeps the latest trading-day
value and is collapsed to one sample per ISO week to avoid over-weighting
recent days. Percentiles are computed locally over the personal database; the
card shows the weighted PE-TTM (`addTtmPe`) plus equal-weight PE for reference,
and each percentile is followed by the current/window-high ratio (e.g. `1.9%
(最高 49.3%)`) so rank and magnitude cannot be confused.

The scheduler now refreshes the `valuation` dataset in every 06:00/12:00/18:00
round. A manual refresh button re-runs only this dataset.

Added an on-demand **official cross-check**: CSI `市盈率1（总股本）` for
沪深300/科创50 is compared with Legulegu static PE, and CNI `PE滚动` for
创业板指/创业板50 is compared with Legulegu TTM PE. The card shows the official
value, date/source, percentage difference and a status (`一致` ≤5%,
`口径差异` 5%-15%, `需复核` >15%). Official endpoints only expose current
values, so they validate the level but never replace the weekly history.

### Files
| Path | Change |
|---|---|
| `personal/datahub/models.py` | New `IndexValuation` model |
| `personal/datahub/store.py` | `index_valuation` table (code/date/source), replace/get/upsert methods, stats |
| `personal/datahub/sources/valuation_source.py` | New: Legulegu weekly fetch, cookie/token, payload parsing, ISO-week dedupe |
| `personal/datahub/sources/valuation_check_source.py` | New: CSI/CNI official current PE fetch for cross-check |
| `personal/datahub/market.py` | `sync_index_valuation` with per-index atomic replace and partial-failure reporting |
| `personal/analytics/index_valuation.py` | New: 1/3/5-year window percentile, sample floors, sample frequency, stale days, metric-aware cross-check |
| `personal/api/app.py` | `GET /api/market/index-valuation`, `GET /api/market/index-valuation/check`; `valuation` in market sync |
| `personal/datahub/schedule.py` | `valuation` dataset in the default daily run |
| `personal/cli/main.py` | `sync --dataset valuation` |
| `apps/dsa-web/src/components/personal/ReviewCards.tsx` | New `IndexValuationCard` + registry entry + cross-check table |
| `apps/dsa-web/src/pages/PersonalPage.tsx`, `api/personal.ts`, `types/personal.ts` | Load/refresh/cross-check/type wiring |
| `personal/tests/test_index_valuation.py`, `personal/tests/test_schedule.py` | Parser/store/percentile/sync/API/cross-check tests |
| `apps/dsa-web/src/components/personal/__tests__/IndexValuationCard.test.tsx`, `src/api/__tests__/personal.test.ts` | Card render/refresh/cross-check + exact route tests |
| `patches/0001-personal-web-integration.patch` | Regenerated with the card, page wiring and API types |
| `docs/USER_GUIDE_PERSONAL.md` | §4.6 card/caliber/cross-check, §4.7 dataset, §7.1 table |
| `docs/AI_CONTEXT.md`, `docs/ROADMAP_PERSONAL.md`, `docs/PERSONAL_EXTENSION_ARCHITECTURE.md`, `docs/DOCKER_PERSONAL.md` | Modules/routes/tables/limitations, RM-46, valuation flow and weekly-source note |

### Commands
```bash
python -m personal.cli.main sync --dataset valuation
python -m personal.cli.main sync --dataset valuation --start 2026-11-01 --end 2026-11-19
cd apps/dsa-web && npm run build
```

### Verification
- Real Legulegu fetch (4 indexes, 3,141 weekly rows) parsed and stored in a
  temporary DB. Latest 2026-11-19: 沪深300 PE 12.69, 1y/3y/5y percentiles
  19.2%/63.9%/74.5%; 创业板指 22.12, 1.9%/3.9%/2.4%; 创业板50 19.72,
  1.9%/0.6%/0.4%; 科创50 60.19, 7.7%/57.4%/74.1%.
- Weekly sample counts 52/155/255; `sample_freq=weekly`; stale_days=0.
- `pytest personal/tests`: **178 passed**.
- `compileall personal` passes.
- `npm run build` passes; `npm run lint` passes.
- Targeted Vitest: 9 passed (API endpoint + card render/empty/refresh/cross-check).
- Full Vitest: 1,391 passed, 2 pre-existing unrelated failures
  (`DesktopUpdateIndicator` native `title` governance; DecisionSignalsPage
  timeline refresh test); 2 skipped.
- API test: `GET /api/market/index-valuation` returns 4 rows and percentiles;
  `GET /api/market/index-valuation/check` returns metric-aware statuses.
- Real official cross-check on 2026-11-19: 沪深300 乐咕静态 13.25 vs 中证 PE1
  13.77 (-3.8%, 一致); 科创50 95.85 vs 85.57 (+12.0%, 口径差异); 创业板指
  22.12 vs 国证 22.69 (-2.5%, 一致); 创业板50 19.72 vs 20.12 (-2.0%, 一致).
- Ratio display: 创业板指 1y `1.9%（最高 49.3%）`; the hint explicitly states
  percentile is rank, not current/high ratio.
- Container E2E: built a local image, seeded a temp `personal.db` via
  `sync --dataset valuation`, opened `/personal` in the browser; the
  「指数估值分位」card rendered all four indexes with PE, equal-weight PE,
  1/3/5-year percentiles, 52-week sample count, and update date; the
  cross-check table rendered official values and status badges.
- NAS deployment (linux/amd64): built the image, `docker load` +
  `docker compose up -d --force-recreate`; both containers reached healthy,
  `GET /personal-api/api/market/index-valuation` returned 200, and the
  deep-review page rendered the card and cross-check.
- NAS ratio display verified in the rendered DOM: 沪深300 `19.2%（最高 91.2%）`,
  创业板指 `1.9%（最高 49.3%）`, 创业板50 `1.9%（最高 44.7%）`,
  科创50 `7.7%（最高 49.5%）`.

### Notes / Migration
- New table is created automatically by `CREATE TABLE IF NOT EXISTS`; no backfill
  migration needed. The first sync fetches full history per index.
- Percentile floors: 1y 10, 3y 30, 5y 50 observations. Below that the UI shows
  `样本不足` instead of a misleading percentile.
- A single index failure marks the whole dataset run failed in `sync_state`
  (so the scheduler retries) while successful indexes remain updated.
- `addTtmPe` is the cap-weighted rolling PE; `ttmPe` is equal-weight. The card
  labels the main PE as PE-TTM and shows 等权 as a secondary line. Historical
  position, not a buy/sell signal.
- Stale rows (>7 days) get a warning at the bottom of the card.
- Cross-check is metric-aware: CSI PE1 (total-share) is compared with
  Legulegu static PE; CNI PE滚动 is compared with Legulegu TTM. Comparing the
  card's TTM value against CSI's PE1 would be misleading.
- Status thresholds: ≤5% consistent, 5%-15% methodology difference, >15%
  review. A difference is not automatically a data bug (weights/share base/
  earnings timing). Cross-check is on demand and does not affect the scheduled
  valuation sync.
- CSI is fetched directly from the official `indicator/{code}indicator.xls`
  because the Docker image pins akshare 1.19.x, which lacks
  `index_value_csindex`; `pandas`+`xlrd` are already present. CNI still uses
  the installed akshare `index_all_cni`.

### Next
- Optional intraday/daily official PE source if a permitted feed becomes
  available; currently weekly is the free-tier basis.
- Add percentile history/valuation zone to the composite market-state score
  after observing a few weeks of data.

## [2026-11-19] CHG-0031 — Fix missing Shanghai margin names

### Metadata
- id: CHG-0031
- date: 2026-11-19
- status: done
- area: datahub | api | docs
- related: RM-42, CHG-0027

### Summary
The 「持仓股两融」card showed blank names for Shanghai codes. The SSE margin
detail endpoint names the field `securityAbbr`, but the adapter only read
`stockName`, so every Shanghai row was stored with an empty name. The adapter
now falls back to `securityAbbr`. The API also keeps the latest non-empty name
instead of taking the first (oldest) row, so legacy blank rows do not mask a
newly backfilled name. Margin sync now includes codes already present in
`margin_stock`, allowing old rows for codes removed from the watchlist to be
refreshed rather than staying blank forever.

### Files
| Path | Change |
|---|---|
| `personal/datahub/sources/margin_source.py` | Read `stockName` or `securityAbbr` |
| `personal/datahub/store.py` | `margin_stock_codes()` for legacy-code refresh |
| `personal/api/app.py` | Latest non-empty name wins; margin sync includes legacy codes |
| `personal/datahub/schedule.py`, `personal/cli/main.py` | Margin code union includes existing margin history |
| `personal/tests/test_market.py` | SSE `securityAbbr` fallback test |
| `docs/USER_GUIDE_PERSONAL.md` | §4.6 name-source note |
| docs | CHANGELOG, AI_CONTEXT |

### Commands
```bash
docker exec daily_stock_analysis-2 python -m personal.cli.main sync --dataset margin
docker exec daily_stock_analysis-2 python -m personal.cli.main sync --dataset margin --code 510300 --code 600519
```

### Verification
- `pytest personal/tests`: **178 passed**.
- NAS API after backfill: 000063 中兴通讯, 510300 300ETF, 563230 卫星ETF,
  600197 伊力特, 600519 贵州茅台, 603160 汇顶科技, 688008 澜起科技,
  688525 佰维存储; no blank names remain.
- NAS deep-review 持仓股两融 table renders all names; valuation card and
  official cross-check also render after deployment.

### Notes / Migration
- Existing rows were backfilled by re-running the 10-day margin sync; the
  `--code` form was used for legacy codes that are no longer in the current
  watchlist.
- SSE abbreviations are exchange short names (e.g. 510300 → `300ETF`), not
  fund full names; the card now shows a name rather than `—`.

## [2026-11-19] CHG-0032 — Documentation: AI context completeness for RM-46

### Metadata
- id: CHG-0032
- date: 2026-11-19
- status: done
- area: docs
- related: CHG-0030, CHG-0031

### Summary
No code changes. This entry records the documentation pass that makes the
index-valuation change set fully machine-readable: a dedicated RM-46 section in
`docs/AI_CONTEXT.md` (storage, metrics, formulas, freshness, cross-check
mapping, API/CLI/frontend entry points, operational semantics), the Legulegu
source row in the data-source matrix, the valuation flow/caliber block in the
architecture document, the optional cross-check degradation note in the Docker
guide, and CHG-0030/0031/0032 in the changelog index. It also adds the NAS
deployment and rendered-ratio verification that was previously only in the
session record.

### Files
| Path | Change |
|---|---|
| `docs/AI_CONTEXT.md` | New "Index valuation (RM-46)" section; Legulegu source row; market-sync body; changelog index entries |
| `docs/PERSONAL_EXTENSION_ARCHITECTURE.md` | Valuation caliber bullets: rank vs ratio, sample floors, metric-matched cross-check, status thresholds |
| `docs/DOCKER_PERSONAL.md` | Cross-check failure is isolated to `不可用` and never affects the weekly series |
| `docs/CHANGELOG_PERSONAL.md` | CHG-0030 files/verification amended; new CHG-0032 |

### Commands
```bash
python -m pytest personal/tests -q --collect-only
grep -n "Index valuation (RM-46)" docs/AI_CONTEXT.md
```

### Verification
- `pytest personal/tests -q --collect-only`: **178 tests collected**, matching
  `test_count` in `docs/AI_CONTEXT.md`.
- Documentation paths and route names checked against
  `personal/api/app.py`, `personal/analytics/index_valuation.py`,
  `personal/datahub/sources/valuation_source.py`,
  `personal/datahub/sources/valuation_check_source.py`,
  `apps/dsa-web/src/components/personal/ReviewCards.tsx` and
  `apps/dsa-web/src/types/personal.ts`.
- No code paths changed; build/test results from CHG-0030/0031 remain valid.

### Notes
- `docs/AI_CONTEXT.md` is the single machine-readable entry point; the
  changelog holds the historical change set.
- Older changelog entries intentionally keep their historical test counts; only
  the current snapshot and the latest entries use 178.

### Next
- Commit/push and redeploy remain separate user decisions.

## [2026-11-20] CHG-0033 — Valuation switches to daily Tushare with Legulegu fallback

### Metadata
- id: CHG-0033
- date: 2026-11-20
- status: done
- area: datahub | analytics | web | docs
- related: RM-46, CHG-0030

### Summary
The user upgraded the Tushare account to 2000 points, unlocking
`index_dailybasic`. The `valuation` dataset now prefers the **daily** Tushare
series for the four broad indexes and falls back to the weekly Legulegu feed
per index when the token is missing, lacks permission, or fails. Percentile
windows therefore hold ~244/727/1212 daily samples (1y/3y/5y) instead of 52
weekly ones, and the deep-review card adapts: a source chip
(`Tushare 日频` / `乐咕周频`) and sample suffix (`日`/`周`/`月`) follow the
detected source. The analytics layer picks one storage source per index by
newest trade date (row count tie-break) and never mixes frequencies inside a
window. A fully successful Tushare sync purges the superseded weekly Legulegu
rows. Requests are paced: ~380-day chunks with ≥0.5s spacing (~20 calls per
run, well under the 2000-point interface limit) and the existing
minute/hourly rate-limit handling. The cross-check now labels the compared
series generically (本地静态/TTM) because it works against whichever source is
stored; measured with Tushare daily data: 沪深300 +1.4% (一致), 创业板50 +0.9%
(一致), 创业板指 +11.6% (口径差异), 科创50 static +127% (需复核 — Tushare's
static profit base diverges on STAR constituents; the card still shows PE-TTM).

### Files
| Path | Change |
|---|---|
| `personal/datahub/sources/tushare_source.py` | Public `fetch_index_dailybasic` (ts_code/date range, minimal fields) |
| `personal/datahub/sources/valuation_tushare_source.py` | New: chunked daily fetch, YYYYMMDD parsing, 200-row floor, `is_daily` flag |
| `personal/datahub/market.py` | `sync_index_valuation` Tushare-first with per-index Legulegu fallback (auto mode only), daily/weekly floors, legulegu purge |
| `personal/datahub/store.py` | `delete_index_valuations(code, source)` |
| `personal/analytics/index_valuation.py` | `_preferred_source` auto-selection, `daily` sample frequency, per-row `source`, source-neutral cross-check wording |
| `personal/datahub/sources/valuation_check_source.py` | Source-neutral `legu_label` (静态 PE（总股本）/PE-TTM（滚动）), docstring |
| `apps/dsa-web/src/components/personal/ReviewCards.tsx` | `日` suffix + source chip + updated hint (Tushare daily primary) |
| `apps/dsa-web/src/types/personal.ts` | Row `source`, `sample_freq` gains `daily`, response `source` nullable |
| `personal/tests/test_index_valuation.py` | Tushare parse/chunk/fallback/purge/detection/cross-check tests |
| `apps/dsa-web/src/components/personal/__tests__/IndexValuationCard.test.tsx` | Daily suffix + source chip test; fixture updates |
| `docs/USER_GUIDE_PERSONAL.md`, `docs/AI_CONTEXT.md`, `docs/ROADMAP_PERSONAL.md`, `docs/PERSONAL_EXTENSION_ARCHITECTURE.md`, `docs/DOCKER_PERSONAL.md` | Daily-first semantics, fallback rule, pacing, methodology notes |

### Commands
```bash
export TUSHARE_TOKEN=...  # 2000-point token in config/personal.env (gitignored)
python -m personal.cli.main sync --dataset valuation
cd apps/dsa-web && npm run build
```

### Verification
- `pytest personal/tests`: **185 passed** (was 178; 7 new tests).
- `compileall personal` passes.
- Targeted Vitest 10 passed; full Vitest **1,392 passed**, 2 skipped, and the
  only 2 failures are the pre-existing unrelated ones
  (`DesktopUpdateIndicator` title governance, `DecisionSignalsPage` timeline
  refresh).
- Real Tushare fetch (2000-point token) into a temp DB: 4,964 daily rows,
  range 2021-10-12 → 2026-11-20, `source=tushare`, `sample_freq=daily`;
  percentiles 1y/3y/5y = 沪深300 17.7/64.0/76.0% (n=243/727/1212), 创业板指
  0.4/7.2/4.3%, 创业板50 0.4/0.1/0.1%, 科创50 2.5/42.0/65.2%.
- Real cross-check on 2026-11-20 (Tushare source): 沪深300 静态 13.97 vs 中证
  PE1 13.78 (+1.4%, 一致); 创业板50 20.14 vs 国证 19.95 (+0.9%, 一致);
  创业板指 25.08 vs 国证 22.47 (+11.6%, 口径差异); 科创50 静态 187.76 vs 中证
  82.73 (+127%, 需复核 — methodology, card main metric stays PE-TTM).
- NAS deployment (linux/amd64 image, compose recreate): valuation sync
  reported 1,823 net rows (4,964 daily Tushare rows inserted minus 3,141
  superseded weekly Legulegu rows), `GET /personal-api/api/market/index-valuation`
  returns `source=tushare`, `sample_freq=daily`, as_of 2026-11-20, percentiles
  matching the local run; 科创50's 1y window now reaches the October spike
  (window high 263.9) that the weekly sampling missed.
- NAS config fix: `TUSHARE_TOKEN=` was left empty in the NAS `.env`, and the
  compose line `TUSHARE_TOKEN=${TUSHARE_TOKEN}` injected that empty string into
  `stock-personal-sync`, shadowing the real token in `data/runtime.env`
  (`_load_env_file` never overrides existing env keys). Removed the line from
  the NAS compose (backup `docker-compose.yml.bak-20261120`); both containers
  now load the token via `ENV_FILE`. Pitfall documented in
  `docs/DOCKER_PERSONAL.md`.

### Notes / Migration
- Requires `TUSHARE_TOKEN` with 2000 points for the daily series; without it
  the behaviour is unchanged (weekly Legulegu) — no config migration needed.
- `_preferred_source` is read-time only; existing weekly rows keep working and
  are replaced/purged by the next successful Tushare sync.
- The daily fetch runs ~20 paced requests per sync round (06:00/12:00/18:00),
  far below the 2000-point per-interface limit; `index_dailybasic` publishes
  the current day around the evening close, so the 18:00 round already carries
  same-day PE.
- Tushare PE methodology differs from CSI/CNI on some indexes; the cross-check
  surfaces this as `口径差异`/`需复核` instead of silently accepting it.

### Next
- Candidate follow-ups on the 2000-point tier: `margin`/`margin_detail` as a
  fallback for exchange margin, `fut_daily` for CFFEX contracts, `share_float`
  for restricted-release; keep exchange/official sources primary where they
  already work.

## [2026-11-20] CHG-0034 — Tushare sources for futures/margin/release + backfill path

### Metadata
- id: CHG-0034
- date: 2026-11-20
- status: done
- area: datahub | cli | docs
- related: CHG-0033, RM-42, RM-05

### Summary
With the 2000-point Tushare tier, three more deep-review datasets gained a
Tushare-backed source beside the official/exchange adapters:

- **Index futures (primary)**: official CFFEX data rebuilt from
  `fut_mapping` (continuous → main contract per day) + `fut_daily` (per
  contract) + `index_daily` spot closes. `oi_chg` is recomputed across the
  assembled continuous series so contract rolls do not fake a jump. The
  AkShare/Sina adapter remains the fallback.
- **Margin balance (fallback + forced backfill)**: `margin` provides
  exchange summaries including 融资买入额 (`rzmre`), so 沪市/深市/总计 market
  rows are fully equivalent to the exchange official source; `margin_detail`
  is queried per code, making long-range per-stock history cost one request
  per code instead of one per day. The exchange scrape stays primary (it also
  yields board splits); Tushare takes over when the scrape returns nothing or
  when `sync --dataset margin --via-tushare` is set (no 120-day cap). Tushare
  detail rows carry no instrument name and the store now guards upserts so a
  blank name never overwrites a stored one.
- **Release calendar (fallback)**: `share_float` aggregates per float-date
  (count, shares in 股 matching the Eastmoney unit); market value is estimated
  from latest closes and omitted entirely for any day with a missing price
  rather than showing a partial estimate. Eastmoney (official 实际解禁市值)
  stays primary.

### Files
| Path | Change |
|---|---|
| `personal/datahub/sources/tushare_source.py` | Raw adapters: `fetch_margin_summary`, `fetch_margin_detail`, `fetch_fut_mapping`, `fetch_fut_daily`, `fetch_index_daily`, `fetch_share_float`, `fetch_daily_close_map` |
| `personal/datahub/sources/margin_tushare_source.py` | New: summary parser (SSE/SZSE→沪市/深市/总计, BSE excluded) + per-code detail parser + throttled client |
| `personal/datahub/sources/futures_tushare_source.py` | New: mapping→contract→daily assembly, continuous `oi_chg`, basis math |
| `personal/datahub/sources/release_tushare_source.py` | New: float-date aggregation + latest-close MV estimate |
| `personal/datahub/market.py` | `sync_index_futures` Tushare primary; `sync_margin_balance` fallback + `prefer_tushare` (cap skip); `sync_restricted_release` fallback |
| `personal/datahub/store.py` | `margin_stock` upsert name guard |
| `personal/cli/main.py` | `sync --via-tushare` flag |
| `personal/tests/test_market.py` | Parser/source/fallback/CLI/name-guard tests |
| docs | USER_GUIDE §5/§7.6/§7.7, AI_CONTEXT, DOCKER_PERSONAL, ROADMAP |

### Commands
```bash
python -m personal.cli.main sync --dataset futures --start 2025-05-01   # Tushare primary
python -m personal.cli.main sync --dataset margin --via-tushare --start 2025-05-01
python -m personal.cli.main sync --dataset valuation
```

### Verification
- `pytest personal/tests`: **196 passed**; `compileall` passes.
- Real fetches (2000-point token, temp DB):
  - futures 2026-05-01→2026-11-19: 540 rows in ~7.5s (~25 requests), basis_pct
    2026-11-19: IF -1.48%, IH -1.52%, IM -1.05% (贴水), `source=tushare_futures`.
  - margin via-tushare 2026-09-01→2026-11-19 with 3 codes: 312 rows in ~1.3s
    (56 trading days × 3 market rows + 144 stock rows); 600519.SH 2026-11-19
    rzye 14.49亿 matches the exchange-detail value; 总计 = 沪市 + 深市 exact.
  - release December window: daily aggregates with MV estimates (close map
    complete); unit check confirmed Eastmoney 实际解禁数量 is also 股.
- Parser tests cover BSE exclusion, 总计 summation, rzmre mapping, roll-aware
  `oi_chg`, missing-close MV omission, CLI flag routing, and the name guard.

### Notes / Migration
- `fut_mapping`/`fut_daily` row caps at 2000 points are far above the per-run
  needs (272-day mapping ≈ 272 rows; contracts live ≤ ~8 months).
- Roll-day `oi_chg`: NAS validate flagged `futures/oi_chg_out_of_range` on
  contract-switch days (e.g. 2026-09-18) because OI levels of two different
  contracts are not comparable during migration. The Tushare source now sets
  `oi_chg=None` on the first day of a new main contract and the futures
  history was re-backfilled. Remaining warnings (e.g. IC 2025-12-18,
  持仓 -66%) are **genuine same-contract OI decay during roll season** — the
  expiring contract bleeds OI to the next contract for a few days *before*
  the volume-based mapping switches, so the continuous OI dip is real and
  informative; these validate warnings are expected artifacts of roll weeks,
  not data errors.
- Pre-existing 2026-11-19 `sector/amount_vs_turnover` error (66% vs the
  85%-115% band) is unrelated to this change: the THS snapshot stored that
  day is partial and snapshot-only sources cannot be re-fetched. The 2026-11-20
  snapshot ratio is 100.5%, so the pipeline is healthy; the stale error ages
  out of validate's window.
- Tushare margin summary rows use the exchange-official totals (including
  ETF/bond instruments) exactly like the scraped summary; board rows stay
  exchange-only, so mixing sources never creates inconsistent board math.
- `prefer_tushare` ignores the `source` injection (CLI backfill path).
- Futures/margin tables have no source column (PK date+key); a Tushare re-run
  overwrites rows in place, which is the intended history refresh path.
- Tushare detail rows arrive nameless; `sync_margin_balance` prefills blank
  names from the latest non-empty name already stored per code
  (`PersonalStore.margin_stock_names()`), and the upsert guard keeps any
  stored name from being blanked. NAS margin backfill: 5,727 rows across 16
  codes (2025-05-19 → 2026-11-19) in ~6s with names preserved.

### Next
- Optionally route `turnover` through `index_daily` amounts as a third-source
  fallback; keep exchange/official primary elsewhere.

## [2026-11-21] CHG-0035 — TRIN breadth computed from Tushare, import-arms demoted to fallback

### Metadata
- id: CHG-0035
- date: 2026-11-21
- status: done
- area: datahub | cli | docs
- related: CHG-0033/0034, RM-17, RM-31

### Summary
The deep-review TRIN no longer depends on the external easy-daily-trading
snapshot project. A new `breadth` dataset computes the Arms Index locally from
Tushare full-market `daily` data (2000 points, one request per trading day):
up/down/flat counts by `change`, volume/amount sums (converted to 亿股/亿元),
`TRIN` plus the amount-based `trin_amount` cross-value, `adv_ratio`, the
A-share band/interpretation text, the 上证指数 anchor (`index_daily`
000001.SH) and the rolling `trin_pct` percentile against stored history.

Universe matches the imported series: 沪深A股 excluding `.BJ` (北交所) and
ST/退市 instruments via `stock_basic` names. Dual-source check on
2026-11-17: Tushare 1197/3713/117 (total 5027, TRIN 0.654) vs the imported
easy-daily row 1192/3717/117 (total 5026, TRIN 0.652) — the small delta is
that Tushare uses real exchange amounts while the old snapshot estimated
amounts as 股数×收盘价. The scheduled 06:00/12:00/18:00 rounds now include
`breadth` (last 10 days); the free `import-arms` snapshot import stays
available as the manual fallback and previously imported rows remain until a
Tushare row overwrites the same date. easy-daily's 指数背离 signal tags are
not reproduced by this path (card shows `—`).

### Files
| Path | Change |
|---|---|
| `personal/datahub/sources/tushare_source.py` | `fetch_daily_by_date` (full market), `fetch_stock_name_map`; `fetch_index_daily` gains `pre_close` |
| `personal/datahub/sources/arms_source.py` | New: `aggregate_market_rows` (universe/unit filters, TRIN math) + `TushareArmsSource` |
| `personal/datahub/market.py` | `sync_market_breadth` (calendar days, 450-trading-day cap, percentile enrichment) |
| `personal/datahub/schedule.py` | `breadth` dataset in DEFAULT_DATASETS + dispatch |
| `personal/cli/main.py` | `sync --dataset breadth` routing |
| `personal/tests/test_schedule.py`, `personal/tests/test_market.py` | Dataset coverage, aggregation units/universe/identity, percentile storage, token requirement, CLI routing |
| docs | USER_GUIDE §0/§4.6/§4.7/§5/§7.5, AI_CONTEXT, DOCKER_PERSONAL, ROADMAP |

### Commands
```bash
python -m personal.cli.main sync --dataset breadth --start 2025-10-16
python -m personal.cli.main breadth --days 5
```

### Verification
- `pytest personal/tests`: **200 passed**; `compileall` passes.
- Real fetch (temp DB, 3 days): 2026-11-17 Tushare 1197/3713/117 total 5027
  TRIN 0.654 adv 23.81% vs imported easy-daily 1192/3717/117 total 5026
  TRIN 0.652 adv 23.7%; 2026-11-19 TRIN 0.466 (up 606), 2026-11-20 TRIN 0.207
  (up 266, 恐慌区) — the gap left by the snapshot dependency is closed.
- `count_identity` / `adv_ratio_recompute` / `trin_range` validate rules hold
  on the computed rows by construction.

### Notes / Migration
- One full-market `daily` call per trading day: ~370 requests (~3 min) for a
  1.5-year backfill; scheduled rounds only fetch the last 10 trading days.
- Trading days come from the local calendar, so calendar must be synced first
  (it already is, dataset #1 in every round).
- BREADTH_MAX_DAYS=450 caps a single run; narrow the range instead.
- 指数背离/signal tags remain an easy-daily snapshot feature; if that signal
  is wanted from Tushare data later, port the divergence rules into
  `personal/datahub/breadth.py`.

### Next
- Port the 指数背离 (index-vs-TRIN divergence) rules to the Tushare path.
- Optionally compute an equal-weight turnover version (TRIN by amount only)
  if the volume basis ever looks skewed.

## [2026-11-21] CHG-0036 — Deep-review history uniformly backfilled to 2020-01-01

### Metadata
- id: CHG-0036
- date: 2026-11-21
- status: done
- area: datahub | validate | docs
- related: CHG-0033/0034/0035

### Summary
All deep-review datasets that physically support history were backfilled to
2020-01-01 on the NAS. Vendor row caps discovered by probing required chunked
fetches and one new source:

- **Caps probed**: `margin` truncates at **4000 rows** (2020→2026 range came
  back as exactly 4000, newest-first) → summary chunked at 500 calendar days;
  `share_float` returns one row per **holder** and truncates at **6000** (a
  single month runs 5k+ rows) → chunked at 30 days; `fut_mapping`,
  `index_daily` and `margin_detail` return the full 6.7-year range (~1700
  rows) in one call.
- **Valuation**: `sync_index_valuation` gained a `start` override so the
  daily series extends to 2020-01-02 (`index_dailybasic` covers 2020+).
- **Turnover**: new `TushareTurnoverSource` — 上证指数 `000001.SH` +
  深证综指 `399106.SZ` `index_daily` amounts equal SSE/SZSE stock turnover
  (deviation ~0.1% vs stored exchange figures on 2026-11-19). Wired as the
  automatic fallback when the exchange scrape returns nothing and via
  `sync_turnover(prefer_tushare=True)` for the long-range backfill.
- **Release**: `share_float` chunking; the Eastmoney primary covers the whole
  2020 range in one call with official 实际解禁市值, cross-checked against
  Tushare (2020-01-02: 6 家 both).
- **Validate**: `margin/incomplete_scopes` now expects 3 scopes on dates
  without board rows (Tushare backfill is market-rows-only; board rows come
  exclusively from the exchange detail) and 7 when board rows exist.

### Files
| Path | Change |
|---|---|
| `personal/datahub/sources/base.py` | Shared `date_chunks` helper |
| `personal/datahub/sources/margin_tushare_source.py` | 500-day summary chunking |
| `personal/datahub/sources/release_tushare_source.py` | 30-day `share_float` chunking (holder rows) |
| `personal/datahub/sources/turnover_tushare_source.py` | New: index-amount turnover fallback |
| `personal/datahub/sources/valuation_tushare_source.py` | Explicit `start` override |
| `personal/datahub/sources/tushare_source.py` | `fetch_index_daily` gains `amount` |
| `personal/datahub/market.py` | `sync_index_valuation(start=...)`, `sync_turnover(prefer_tushare=...)` + fallback |
| `personal/datahub/validate.py` | margin scope expectation 3/7 |
| `personal/tests/test_market.py`, `personal/tests/test_validate.py` | Chunking, unit conversion, fallback, scope-rule tests |

### Commands
```bash
# staged backfills on NAS (2020-01-01 -> now)
python -m personal.cli.main sync --dataset futures --start 2020-01-01
python -m personal.cli.main sync --dataset margin --via-tushare --start 2020-01-01
python -m personal.cli.main sync --dataset breadth --start 2020-01-01   # chunked by 450 trading days
python -m personal.cli.main sync --dataset release --start 2020-01-01   # EM wide range
python -m personal.cli.main sync --dataset pcr --start 2020-01-01       # looped <=120-day windows
python -c "... sync_turnover(prefer_tushare=True, start=2020-01-01)"
python -c "... sync_index_valuation(start=2020-01-01)"
```

### Verification
- `pytest personal/tests`: **207 passed**; `compileall` passes.
- Local real fetches: margin 2020Q1 290 rows (600519 rzye 109.2亿, realistic);
  turnover 2020-01 16 trading days (~7000-8000亿 totals); release 2020-2021
  285 days via chunked Tushare, matching EM (6 家 on 2020-01-02 both);
  valuation extended to 2020-01-02 (000300: 1,668 daily rows).
- NAS results reported after the staged runs (see session record).

### Notes / Migration
- **Not backfilled to 2020** (physically impossible):
  - `limit_up_stats` — Eastmoney pools keep only ~30 trading days.
  - `sector_amount` / `etf_share` — same-day snapshot APIs, no history.
  - `futures_rank` — CFFEX official member CSVs cost ~4 requests per day
    (~5,300 requests for 2020→2025); kept at the 2025-05-19 extent.
- `market_breadth` rows before 2026-11-19 keep easy-daily's 指数背离 blanks;
  Tushare rows overwrite by date as the backfill progresses.
- Board-level margin rows exist only from 2025-05-19 (exchange detail); older
  dates carry the 3 market scopes only, which validate now accepts.

### Next
- Optionally backfill `futures_rank` if the CFFEX archive proves tolerant to
  a long crawl.
