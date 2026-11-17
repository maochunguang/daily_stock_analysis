# AGENTS.md — Personal Extension Layer

This file is the operating manual for AI coding agents working on this
repository. Read it before changing code.

> **Fork layout:** This is the self-contained fork. The repo root is the DSA
> upstream code; there is no `upstream/` subdirectory. The personal layer lives
> at `personal/`, and the UI integration patch is already applied. Where this
> document mentions `upstream/...`, read the repo root. Use
> `python -m personal.cli.main ...` if the `dsa-personal` console script is not
> installed.

## Read first

1. `docs/PERSONAL_EXTENSION_ARCHITECTURE.md` — architecture and boundaries.
2. `docs/AI_CONTEXT.md` — compact machine-readable context.
3. `docs/CHANGELOG_PERSONAL.md` — what changed, where, and how it was verified.
4. `docs/USER_GUIDE_PERSONAL.md` — end-user manual for every feature.
5. `docs/ROADMAP_PERSONAL.md` — priorities, status and acceptance criteria.
6. `UPSTREAM_VERSION` — pinned upstream commit.

## Hard invariants

1. **DSA-side changes are guarded by patches.** In this fork the DSA code is
   the repo root; DSA-side edits live in `patches/0001-personal-web-integration.patch`
   (personal page, sidebar entry, `/personal-api` mount, auth coverage),
   `patches/0002-deepseek-news-search.patch` (DeepSeek news-search provider +
   settings schema), and `patches/0003-news-intel-private-hosts.patch`
   (NEWS_INTEL_ALLOW_PRIVATE_HOSTS gate for self-hosted sources; depends on
   0002). `docker/` packaging and the personal block in
   `.env.example` are fork-maintained directly. Keep future DSA-side edits
   confined to these patches (or extend them); personal code lives in `personal/`.
2. **Personal code must not import upstream internals.** Allowed: `personal.contracts.*`.
   Forbidden: `from src.analyzer import ...`, `from src.core.pipeline import ...`.
3. **Never write to the upstream database.** The upstream DB is opened read-only
   (`mode=ro`, `PRAGMA query_only=ON`).
4. **Personal data lives in `data/personal.db`.** It is separate from upstream.
5. **Never commit secrets.** `config/personal.env` is gitignored. Do not print
   tokens, passwords, or account ids in logs or docs.
6. **Trading is off by default.** `QMT_TRADING_ENABLED=false` and
   `QMT_REQUIRE_CONFIRM=true`. Never enable live trading without explicit user
   instruction and a simulated-trading run first.
7. **Every change must update `docs/CHANGELOG_PERSONAL.md`** with a new
   `CHG-XXXX` entry using the fixed template.
8. **If architecture, contracts, schemas, commands, or limitations change,
   update `docs/AI_CONTEXT.md` too.**
9. **Every user-facing feature must update `docs/USER_GUIDE_PERSONAL.md`.**
   Pages, tabs, fields, CLI commands/options, env vars, API routes, data
   sources, backtest rules, metrics, plugin contracts and QMT endpoints all
   count. Add the guide update to the changelog `Files` table in the same
   commit. A feature without a manual entry is incomplete.
10. **Keep the personal layer low-coupling.** Prefer adapters, contracts, and
   sidecar modules over patching upstream. If a patch is unavoidable, put it in
   `patches/` and document the anchor and upstream version.

## Repository map

| Path | Purpose |
|---|---|
| `personal/contracts/` | Read-only upstream DB/API access and typed models |
| `personal/datahub/` | Ingestion, normalization, quality, adjustment, SQLite store |
| `personal/backtest/` | Portfolio accounting, costs, execution, metrics, replay |
| `personal/plugins/` | Stable plugin API, manifest, loader, registry, built-ins |
| `personal/execution/` | QMT bridge HTTP client |
| `personal/api/` | Local FastAPI console and static UI |
| `personal/cli/` | `dsa-personal` CLI |
| `personal/journal/` | Trade journal (Phase 2 placeholder) |
| `personal/reporting/` | Personal reports (Phase 2 placeholder) |
| `qmt-bridge/` | Windows-only FastAPI + xtquant bridge |
| `plugins/` | External plugin examples |
| `config/` | Example config; real `personal.env` is gitignored |
| `patches/` | Explicit upstream patches; currently the personal Web UI integration |
| `scripts/` | Upstream sync, contract check, patch apply |
| `docs/` | Architecture, AI context, changelog, user guide, Docker/NAS guide, phase notes |
| `(repo root)` | DSA upstream code (this fork) |

## Commands

```bash
# setup
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e ".[dev]"

# tests
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q personal scripts qmt-bridge

# CLI (this fork has no console script; run from the repo root)
python -m personal.cli.main info
python -m personal.cli.main init-db
python -m personal.cli.main demo --days 400
python -m personal.cli.main sync --source synthetic --code 600519 \
  --start 2026-01-01 --end 2026-03-01
python -m personal.cli.main sync --source auto --cross-check --code 600519 \
  --start 2026-01-01 --end 2026-03-01
python -m personal.cli.main sync --dataset calendar --source baostock \
  --start 2026-01-01 --end 2026-03-01
python -m personal.cli.main sync --dataset status --code 600519 \
  --start 2026-01-01 --end 2026-03-01
python -m personal.cli.main replay --start 2025-01-01 --end 2026-11-16
python -m personal.cli.main plugins

# Integrated upstream Web UI (one service, personal page at /personal)
# Requires an env with requirements.txt installed.
PYTHON_BIN=/path/to/upstream-env/bin/python scripts/start_webui.sh
# or: python main.py --webui

# Standalone personal console (still available)
.venv/bin/dsa-personal web --host 127.0.0.1 --port 8765

# Docker / NAS (integrated image; page at /personal)
docker compose -f docker/docker-compose.yml build server
docker compose -f docker/docker-compose.yml up -d server

# Rebuild upstream frontend after touching apps/dsa-web/src
cd apps/dsa-web && npm run build

# The UI patch is already applied in this fork. Verify it matches:
git apply --check --reverse patches/0001-personal-web-integration.patch

# upstream contract check
.venv/bin/python scripts/check_contracts.py --allow-missing
```

## Where to add a feature

| Feature | Files |
|---|---|
| New data source | `personal/datahub/sources/<name>_source.py`, register in `personal/datahub/sync.py::build_sources`, add tests in `personal/tests/test_sync.py` |
| New indicator plugin | `plugins/<name>/plugin.yaml` + `plugin.py`, implement `personal.plugins.api.IndicatorPlugin`, add tests in `personal/tests/test_plugins.py` |
| New upstream contract | `personal/contracts/upstream_db.py`, `personal/contracts/models.py`, `personal/contracts/version.py`, tests in `test_contracts.py` |
| New backtest rule/metric | `personal/backtest/*`, tests in `test_backtest.py` / `test_metrics.py` |
| New Web API | `personal/api/app.py`, tests in `personal/tests/test_api.py` |
| New integrated UI tab | `upstream/apps/dsa-web/src/pages/PersonalPage.tsx`; regenerate `patches/0001-personal-web-integration.patch` |
| New standalone console tab | `personal/api/static/index.html`, `style.css`, `app.js` |
| New CLI command | `personal/cli/main.py` |
| QMT endpoint | `qmt-bridge/app.py` + `personal/execution/qmt_client.py` |
| Any user-facing feature/manual | `docs/USER_GUIDE_PERSONAL.md` (add a §0 nav row + a section) |

## Upstream UI integration contract

The user wants the personal features inside the upstream Web UI, not only the
standalone console. This is the one intentional coupling point.

| Piece | Location |
|---|---|
| Sidebar entry | `upstream/apps/dsa-web/src/components/layout/SidebarNav.tsx` (`个人扩展` → `/personal`) |
| Route | `upstream/apps/dsa-web/src/App.tsx` |
| Header title/description | `upstream/apps/dsa-web/src/components/layout/ShellHeader.tsx` + i18n keys in `uiText.ts` |
| Page | `upstream/apps/dsa-web/src/pages/PersonalPage.tsx` |
| API client/types | `upstream/apps/dsa-web/src/api/personal.ts`, `types/personal.ts` |
| Backend mount | `upstream/api/app.py` → `/personal-api` before the SPA catch-all |
| Auth coverage | `upstream/api/middlewares/auth.py` protects `/personal-api/*` when auth is enabled |
| Patch | `patches/0001-personal-web-integration.patch` |

Rules:
- Keep upstream edits confined to these files.
- After editing, rebuild: `cd apps/dsa-web && npm run build`.
- Regenerate the patch:
  `git add -N <new files> && git diff -- <paths> > patches/0001-personal-web-integration.patch`
- On upstream sync, re-apply the patch and re-run the frontend build.
- The standalone console (`dsa-personal web`) remains available and should keep
  working; shared API contracts live in `personal/api/app.py`.

## Data source permissions (Tushare free tier, 2026-11-12)

| Interface | Status |
|---|---|
| `daily`, `daily_basic`, `index_daily`, `opt_basic`, `opt_daily` | ✅ |
| `adj_factor` | ⚠️ 1 request/hour |
| `fund_basic`, `fund_nav`, `fund_daily`, `fund_portfolio`, `index_weight` | ❌ no permission |

BaoStock is the current free daily-bar fallback. AkShare is planned for funds.

## Testing rules

- Unit tests must not hit the network. Use fake sources or monkeypatch
  `urllib.request.urlopen`.
- Every new behavior needs a test; keep `pytest` green.
- Run `compileall` after editing Python.
- Update the changelog with commands and verification results.

## Documentation rules for agents

- Changelog entry template:
  `## [YYYY-MM-DD] CHG-XXXX — Title` with `Metadata`, `Summary`, `Files`,
  `Commands`, `Verification`, `Notes`, `Next`.
- **User-facing changes require a `docs/USER_GUIDE_PERSONAL.md` update in the
  same commit.** Add the guide to the changelog `Files` table and describe the
  new UI/CLI/config behavior there. Manual-only docs do not need a second guide.
- Keep `docs/AI_CONTEXT.md` factual and path-exact. Prefer tables and short
  bullets over prose.
- Do not include secrets or full account ids.
- If a change affects architecture, update
  `docs/PERSONAL_EXTENSION_ARCHITECTURE.md` as well.
