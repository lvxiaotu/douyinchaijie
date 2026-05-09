# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

个人工具工作台 — a personal automation workbench that wraps third-party tools (Douyin scraping, AI video analysis, AI prompt reverse, Jianying/CapCut draft generation, HTML video render) behind stable adapters in `integrations/`. The principle is: the main app (FastAPI + Vite/React) stays stable; replacing or upgrading a third-party tool only changes its adapter.

User-facing copy, comments and most docs are written in **Simplified Chinese**. Match that convention when editing UI strings, README content, or `.env.example` comments. Code identifiers are English.

## Common commands

Run from `G:\ob-book\codex-project`. The Python venv is `.venv` (not `.venv-new`, which is leftover).

```powershell
# One-shot: build the frontend into dist/ and serve everything from the FastAPI backend.
.\scripts\start-web.ps1                 # http://127.0.0.1:8010
.\scripts\start-web.ps1 -Port 8020      # rebuild + serve on 8020
.\scripts\start-web.ps1 -InstallDeps    # force pip install -r requirements.txt (base + SDK deps)
.\scripts\start-web.ps1 -StartDouyin    # also boot the upstream Douyin_TikTok_Download_API
.\scripts\start-web.ps1 -NoBuild        # skip vite build, reuse existing dist/

# Dev mode (HMR, two terminals):
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
npm run dev                              # http://127.0.0.1:5173 (Vite dev server)

# Build / preview only:
npm run build
npm run preview
```

There is a small standard-library Python test suite under `tests/`. Run it with:

```powershell
python -m unittest discover -s tests
```

There is still no JS test runner or lint config. Don't fabricate `npm test` / `pytest` invocations — say so when asked.

## Service topology and ports

Three processes, all on `127.0.0.1`:

| Port | Service                                | Notes                                               |
|------|----------------------------------------|-----------------------------------------------------|
| 5173 | Vite dev server                        | Only used in dev mode; proxies `/api/*` to backend  |
| 8010 | FastAPI backend (`backend.app.main`)   | In production also serves the built `dist/`        |
| 8123 | `Douyin_TikTok_Download_API` (upstream) | Optional; needed only for Douyin features         |

Dev-mode wiring is aligned on port **8010**: `vite.config.js` proxies `/api` to `http://127.0.0.1:8010`, and `src/services/api.js` reads `VITE_API_BASE` with an empty-string fallback for same-origin/proxy use.

## Architecture

### Backend (`backend/app/`)

- `main.py` — FastAPI app. Includes routers from `backend/app/routes/` (`douyin`, `ai_provider_config`, `ai_video_analysis`, `ai_prompt_reverse`, `tasks`, `video_script`, `studio`). Calls `init_db()` at import time. When `dist/` exists, mounts `/assets` and falls back to `dist/index.html` for any non-`/api/` path → SPA hosting.
- `task_store.py` — SQLite at `data/runtime/tasks.sqlite3`. Tables: `tasks`, `task_events`, `analysis_archives`, `prompt_reverse_archives`. All async work is modeled as a row in `tasks` plus background updates via `update_task(...)` from a FastAPI `BackgroundTasks` callback. The frontend polls `/api/tasks?task_type=...`.
- `ai_provider_state.py` — single source of truth for which AI provider/model/credentials are active. Reads `AI_MODEL_PROVIDER`, `AI_MODEL`, plus per-provider `*_API_KEY` / `*_BASE_URL` / `*_ACCESS_MODE` env vars. Use `active_ai_provider()` / `openai_compatible_credentials()` rather than reading env directly.
- `registry.py` — workbench snapshot for `/api/workbench` (tools list, demo metrics/jobs/library). Edit here when adding a tool tile to the dashboard.

### Integrations (`integrations/<tool>/`)

Every third-party tool lives in its own folder with this shape:

```
integrations/<tool>/
├── adapter.py       # the only stable interface the backend imports
├── README.md        # tool-specific docs
└── vendor/          # optional, gitignored, upstream repo placed here
```

Rules (enforced informally):
- Backend code imports `integrations.<tool>.adapter`, never anything in `vendor/`.
- Adapters either call upstream over HTTP (`douyin_download_api`) or wrap a Python library (`jianying_draft` → `pyJianYingDraft`).
- Replacing an upstream tool means rewriting `adapter.py` only; route handlers and the frontend should stay untouched.
- `integrations/douyin_spider/` is **deprecated** (superseded by `douyin_download_api`); leave it alone unless removing it intentionally.

Currently active integrations:
- `douyin_download_api` — HTTP client to the upstream Douyin scraper on `:8123`.
- `ai_video_analysis` — long-video "evidence pack" pipeline: ffmpeg extracts audio → faster-whisper transcribes → segment + keyframe grids → AI breakdown per segment → global formula. Mode controlled by `AI_VIDEO_PIPELINE_MODE=auto|evidence|direct`.
- `ai_prompt_reverse` — reverse-engineers reusable prompts from a captured video.
- `jianying_draft` — wraps `pyJianYingDraft` for CapCut/Jianying draft creation. **Pinned to `pyJianYingDraft>=0.2.5,<0.3`** in `requirements-sdk.txt` — `AudioSegment(material, target_timerange, source_timerange=None)` and `draft.trange(start, duration)` (second arg is *duration*, not end time).
- `jianying_editor_skill` — project-owned bridge layer for the local SDK snapshot. Business bridge logic lives here, not under `sdks/jianying-editor-skill/`. Its normal `/status` endpoint is side-effect free; use `/diagnostics/deep` only for explicit smoke checks that may create a diagnostic draft.
- `html_video_render` — renders HTML scenes to MP4 via local ffmpeg (`ffmpeg-8.1.1-essentials_build/`).
- `video_pipeline` — newer in-tree pipeline that produces a single `script.json` per project under `data/runtime/video_pipeline/projects/<project_id>/`. Drives the three-step "灵感剧本 → 素材整理 → 草稿生成" flow described in `VIDEO_PIPELINE_IMPLEMENTATION_PLAN.md`. Tools two and three are partly TBD — check the plan doc before adding routes/files for them.

### Frontend (`src/`)

- `src/main.jsx` — single-file React app (~170 KB). The whole UI lives here; there's no component split yet, so prefer `Edit` for surgical changes over rewriting.
- `src/services/api.js` — every backend call. Add new endpoints here rather than `fetch`-ing inline elsewhere.
- `src/styles.css` — global styles.
- `src/studio/` — newer "studio" flow scaffolding (currently just `types.js`).
- `src/workbenchSeed.js` — fallback workbench data used before `/api/workbench` resolves.

### Data flow for AI tools

1. Frontend calls `POST /api/tools/<tool>/jobs` (or `/generate`, `/blueprint`) with the source video / payload.
2. Route handler creates a row via `create_task(...)` and registers a `BackgroundTasks` callback.
3. Callback runs the integration's adapter, calling `update_task(...)` to push progress.
4. Frontend polls `/api/tasks?task_type=<type>` and `/api/tasks/{id}/events`.
5. On success the route may write into `analysis_archives` / `prompt_reverse_archives` for the library views.

When adding a new long-running tool, follow this pattern — don't block the request thread.

## Configuration

- `.env` is loaded from project root and is **gitignored**. `.env.example` is the canonical list of supported variables.
- AI provider config is layered: generic `AI_*` (provider-agnostic active model), then per-provider blocks (`OPENAI_*`, `GEMINI_*`, `YUNWU_*`, `SIMPLE_RELAY_*`, `DEEPSEEK_*`, `VOLCANO_*`). Each provider supports `official` or `relay` access mode.
- Don't move secrets into source — even Cookies (`DY_COOKIES`) stay in `.env`.
- Upstream Douyin service has its own config at `integrations/douyin_download_api/vendor/Douyin_TikTok_Download_API/crawlers/douyin/web/config.yaml`; `scripts/sync_douyin_download_api_config.py` syncs Cookie from the main `.env` into it.

## Working conventions specific to this repo

- `data/runtime/` is gitignored runtime output (downloads, evidence packs, SQLite DB, generated drafts). Don't commit anything under it; don't assume files there exist on a fresh checkout.
- `integrations/*/vendor/*` is also gitignored — the upstream repo is cloned by the user and isn't part of this project's git history.
- `docs/` is currently empty (the old `ARCHITECTURE.md` / `JIANYING_VIDEO_TOOL_PLAN.md` / `VIDEO_COMPOSITION_SCHEMA.md` were removed). Treat the root-level `README.md`, `START_WEB.md`, `VIDEO_PIPELINE_IMPLEMENTATION_PLAN.md`, `sdks/README.md`, and per-integration `README.md` files as the actual design docs.
- Both README and `.env.example` end with a "配置变更记录" / "需求变更记录" log. When you change a port, env var, or a third-party endpoint, append a dated entry there.
