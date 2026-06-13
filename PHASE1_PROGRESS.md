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
| `GET /api/models`, `POST /api/models`, `PATCH /api/models/{id}`, `POST /api/models/{id}/activate` | ✅ | architecture router; list has row_count (via new `db.get_row_count`) + is_active |
| `GET /api/models/{id}/ports` (paged), `PATCH .../ports/{row}`, `POST .../ports`, `DELETE .../ports/{row}` | ✅ | single-cell edit returns updated row; widget_text mirrored for dropdown cells |
| `GET/PUT /api/columns` | ✅ | `active_config` (name, type, visible, width) round-trip |
| `GET /api/symbols?q=&kind=function\|variable\|any` | ✅ | fuzzy candidates from active release's ELF (cached `SymbolMatcher` per elf_hash); empty (not error) when no ELF |
| `GET /api/releases`, `POST /api/releases`, `POST .../{id}/activate`, `PATCH/DELETE /api/releases/{id}` | ✅ | list marks `selectable` (real release) vs `is_baseline`; `baseline_previous` freeze on create |
| `POST /api/baselines` (create_baseline) | ❌ TODO | needs layout + active-model snapshot assembly (mirror `handle_create_baseline` headlessly) |
| `GET /api/codemap/graph`, `GET /api/source/function/{name}` | ❌ TODO | codemap router (build is wired as a job; graph/source endpoints pending) |
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
- `Tests/test_backend_architecture.py` (15) — models CRUD/activate, columns get/put, paged ports, single-cell + full-cell PATCH, add/delete row re-indexing, view-only write guard.
- `Tests/test_backend_releases.py` (9) — list (selectable vs baseline), create, baseline_previous freeze, activate, rename, delete, view-only guard.
- `Tests/test_backend_symbols.py` (7) — function/variable/any fuzzy candidates, explicit elf_hash, empty-when-no-ELF, works in view-only.

**Known minor robustness gap:** opening a *model-less* project in view-only mode 500s — `ArchitectureManager.load_registry()` tries to persist a default model against the read-only DB. Real projects always have ≥1 model (new_project creates the schema + default while writable), so this only bites hand-built fixtures. Fix later: skip the default-model write when the DB is read_only.

## Exit criteria (plan §3.4) — progress

- [ ] Every feature reachable through the API. **Foundation + project/jobs/events done; feature routers TODO.**
- [x] No Qt imports under `backend/` (asserted by `test_backend_imports_without_pyqt6`).
- [x] API tests cover the job manager + project open/save (httpx/TestClient). Port editing + locking tests TODO with those routers.
- [x] Legacy PyQt app still works (untouched — it calls the logic layer directly; retires Phase 4).

## Next steps (suggested order)

1. ~~architecture router~~ ✅ · ~~releases router~~ ✅ · ~~symbols~~ ✅
2. **codemap + source router** — `GET /api/codemap/graph?model_id=&release_id=` (reads `db.get_model_code_map`,
   reuses `compute_graph_levels` for depth-limited subgraphs), `GET /api/source/function/{name}`
   (reuses `extract_function_block_by_line` + `db.read_release_source_file`). Build is already the
   `build_code_map` job.
3. **changelog router** — diffs already compute via the `release_diff` job + `db.get_code_diffs`;
   add `GET /api/changelog/files` + `GET /api/changelog/diff/{file}` reading stored diffs (reuse
   `parse_and_align_diff`).
4. **ai router** — `GET/PUT /api/ai/providers` (Logic_AI_Providers + encrypted creds),
   `POST /api/ai/chat` SSE-streamed tokens (wrap `run_chat_job`; stream via the real-server SSE pattern),
   `build_mind_map`/`generate_tests` as job kinds (mind_map needs an own-connection wrapper first).
5. **baselines** — `POST /api/baselines` assembling layout (`load_column_layout` + meta +
   `get_test_case_design`) + active-model snapshot, mirroring `handle_create_baseline` headlessly.
6. **port-state propagation** (#8.2) two-step: `POST /api/ports/{id}/state?dry_run=1` → affected list, then commit.
7. Lock heartbeat timer inside the worker (plan §3.3) + parent-PID watch (with Phase 3 desktop shell).
8. Minor: skip default-model write on read-only open (see robustness gap above).

## Session log

- **2026-06-13 (a)** — Phase 1 started. Installed fastapi/uvicorn[standard]/httpx/sse-starlette into the v1 venv
  (added to requirements.txt). Built the foundation: EventBus, JobManager, AppState, security, app factory,
  project + jobs/events routers, three job handlers. 17 backend tests (incl. real-server SSE). Full suite 496 passed.
- **2026-06-13 (b)** — Added the **architecture**, **releases**, and **symbols** routers (+ `db.get_row_count`,
  AppState matcher cache + release/model index helpers). 27 API routes total. 31 new backend tests
  (architecture 15, releases 9, symbols 7). Full suite **527 passed**. All write endpoints honour the
  view-only guard (409) and publish `db-changed` SSE events. Next: **codemap + source router**, then changelog, then ai.
