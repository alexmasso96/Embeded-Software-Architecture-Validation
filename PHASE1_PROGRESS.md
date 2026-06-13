# Phase 1 Progress — FastAPI Worker Process

Tracking document for Phase 1 of [pywebview_react_migration_plan.md](pywebview_react_migration_plan.md) (§3).
Phase 0 is complete (see [PHASE0_PROGRESS.md](PHASE0_PROGRESS.md)); the logic layer is Qt-free.

**Goal:** expose the de-Qt'd logic as a local HTTP API with SSE progress, runnable standalone
(`uvicorn backend.app:app`) and testable with httpx/TestClient. No Qt imports anywhere under `backend/`.

**Test command:** `/Users/alex/Git_Projects/Embeded-Software-Architecture-Validation/.venv/bin/python -m pytest Tests/ -q`
(uses the v1 venv — now with fastapi/uvicorn/httpx/sse-starlette installed; added to `requirements.txt`).
**Suite:** 496 passed (479 Phase-0 + 17 new backend tests).

## Architecture (built)

```
backend/
├── app.py            # create_app() factory + `python -m backend.app` entrypoint (127.0.0.1:0, prints URL+token)
├── state.py          # AppState — headless project lifecycle (replaces the Qt main_window god-object)
├── jobs.py           # JobManager — ThreadPoolExecutor, Job registry, cancel events, SSE emit
├── events.py         # EventBus — thread-safe SSE fan-out (call_soon_threadsafe)
├── handlers.py       # job handlers: _demo, release_diff, build_code_map
├── security.py       # per-session bearer token (Authorization: Bearer, or ?token= for EventSource)
├── deps.py           # FastAPI deps pulling singletons off app.state
└── routers/
    ├── project.py    # new / open / save / close / status
    └── jobs.py       # POST /jobs/{kind}, GET /jobs/{id}, POST /jobs/{id}/cancel, GET /jobs, GET /events (SSE)
```

**Key design decisions**
- **AppState replaces `main_window`.** It owns the open `ProjectDatabase` + the Qt-free
  `ArchitectureManager`/`ReleaseManager`, wired straight to the DB (NOT through the Qt
  `ProjectSaver.load_project`, which drives the table widget). The data model the API serves
  is the DB shape directly (`get_all_models`/`get_model_rows`/`load_column_layout`/`active_config`).
- **Save = durability barrier, not table-flush.** In the worker the `.arch` *is* the live DB;
  routers mutate it directly, so `/project/save` commits + re-stamps the integrity HMAC + WAL-checkpoints.
- **View-only enforced server-side** via `db.set_read_only(True)` (`PRAGMA query_only=ON`) on top of the lock.
- **Job contract is uniform** (plan §3.1): handler = `(params, progress, cancel_event) -> result`.
  Pure `Logic_*` jobs already have this shape (progress_cb + own-connection crash-safety), so handlers stay thin.
- **`new_project` creates the `.arch` BEFORE acquiring the lock** — `FileLockManager.acquire_lock`
  keys its lock file off an existing path.

## Endpoints — status

| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /api/health` | ✅ | no auth |
| `POST /api/project/new\|open\|save\|close`, `GET /api/project/status` | ✅ | lock + view-only + integrity in `status` |
| `POST /api/jobs/{kind}`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, `GET /api/jobs` | ✅ | |
| `GET /api/events` (SSE) | ✅ | job + db-changed + lock events; `?token=` auth for EventSource |
| `GET/PUT /api/models`, `/api/models/{id}/ports` (paged), `PATCH /api/ports/{id}` | ❌ TODO | architecture router |
| `GET/PUT /api/columns` | ❌ TODO | |
| `GET /api/symbols?kind=&q=` (fuzzy candidates) | ❌ TODO | feeds the match-picker |
| `GET /api/releases`, `POST /api/releases`, `POST /api/baselines` | ❌ TODO | releases router |
| `GET /api/codemap/graph`, `GET /api/source/function/{name}` | ❌ TODO | codemap router |
| `POST /api/ai/chat` (SSE tokens), `GET/PUT /api/ai/providers` | ❌ TODO | ai router |
| Port-state propagation (`POST /api/ports/{id}/state?dry_run=`) | ❌ TODO | two-step #8.2 flow |

## Job kinds — status

Registered: `_demo` (test-only), `release_diff`, `build_code_map`.
TODO (wire as routers land): `parse_elf`, `index_source`, `import_architecture`, `fuzzy_rematch`,
`create_baseline`, `generate_tests`, `build_mind_map`, `save_project`.
Note: `run_mindmap_job` takes a live `db` object (not a path) — needs an own-connection wrapper
or careful main-thread handoff before wiring as a job (it currently writes via the shared connection).

## Tests

- `Tests/test_backend_api.py` (15) — auth, project lifecycle, job start/poll/cancel, no-PyQt6 import guard.
- `Tests/test_backend_sse.py` (2) — real uvicorn server + async httpx: SSE delivers job events, bad-token 401.
  (The sync TestClient can't drive streaming SSE, hence the real-server test.)

## Exit criteria (plan §3.4) — progress

- [ ] Every feature reachable through the API. **Foundation + project/jobs/events done; feature routers TODO.**
- [x] No Qt imports under `backend/` (asserted by `test_backend_imports_without_pyqt6`).
- [x] API tests cover the job manager + project open/save (httpx/TestClient). Port editing + locking tests TODO with those routers.
- [x] Legacy PyQt app still works (untouched — it calls the logic layer directly; retires Phase 4).

## Next steps (suggested order)

1. **architecture router** — models list/CRUD, paged ports (`get_model_rows` + `active_config`),
   single-cell `PATCH /api/ports/{id}` returning affected cells, columns. This is the Workspace backbone.
2. **releases router** — list/create, `create_baseline` job, active-release switch.
3. **symbols** — fuzzy candidates from `SymbolMatcher` (feeds the match picker).
4. **codemap + source** router; **changelog** (diff already wired as a job); **ai** (chat SSE, providers).
5. Lock heartbeat timer inside the worker (plan §3.3) + parent-PID watch (belongs with Phase 3 desktop shell).

## Session log

- **2026-06-13** — Phase 1 started. Installed fastapi/uvicorn[standard]/httpx/sse-starlette into the v1 venv
  (added to requirements.txt). Built the foundation: EventBus, JobManager, AppState, security, app factory,
  project + jobs/events routers, three job handlers. 17 backend tests (incl. real-server SSE). Full suite 496 passed.
  Next: the architecture (Workspace) router.
