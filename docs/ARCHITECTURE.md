# Architecture Validator Pro — Architecture Documentation

> A developer-facing map of the codebase. For an end-user walkthrough of the features, see the [User Guide](guide/README.md).

## Overview

Architecture Validator Pro is a cross-platform **desktop application** for validating embedded software architectures against the ELF binary they ship in. It parses ELF/DWARF debug info to extract symbols, functions, structures, and global variables, then fuzzy-matches architecture ports to the real software symbols in the firmware.

The app is built as a **React single-page app running inside a native [pywebview](https://pywebview.flowrl.com/) window**, talking to a **local FastAPI worker** over `http://127.0.0.1`. The worker owns all project state and reuses a Qt-free **pure-logic layer** (`Application_Logic/Logic_*`) plus a native **Rust ELF parser**. A project is persisted as a **single SQLite file** (`MyProject.arch`) with selective per-block content encryption.

The UI is organised as a seven-view workbench:

| View | Purpose |
| :--- | :--- |
| **Workspace** | The architecture-validation matrix: ports × columns, matched to ELF symbols |
| **Test Design** | Markdown-templated test-case design with live preview |
| **AI Generation** | Generate low-level tests from high-level designs, grounded in a code mind map |
| **AI Chat** | Agentic, source-grounded Q&A about the firmware |
| **Code Map** | Visual call-graph + read-only IDE joining ELF facts to C source |
| **Change Log** | Side-by-side release diff with an optional AI summary |
| **Test Injection** | Splice test code into production source without editing the originals |

> This is the **v3** architecture. Earlier versions (v2.x) were a PyQt6 desktop app driven by a `QTableWidget` and a god-object `main_window`. That UI layer and the Qt-coupled controllers have been removed; the business logic that survived was already extracted into the Qt-free `Application_Logic/` package, which the FastAPI worker now drives directly.

---

## Process & layer topology

```
┌─────────────────────────────────────────────────────────────────┐
│  Desktop shell process   (src/desktop/main.py)                    │
│  ─ native pywebview window                                        │
│  ─ exposes native file dialogs + the session token via js_api     │
│  ─ spawns and supervises the worker child process                 │
└───────────────┬───────────────────────────────────────────────────┘
                │  loads  http://127.0.0.1:<port>/   (static SPA)
                │  + token handed over via pywebview js_api
                ▼
┌─────────────────────────────────────────────────────────────────┐
│  React SPA   (src/frontend → built to frontend/dist)              │
│  ─ views/ (the 7 workbench views) + components/ + api/ client     │
│  ─ every data call hits /api/* with the bearer token              │
│  ─ subscribes to /api/events (SSE) for job progress + db-changed  │
└───────────────┬───────────────────────────────────────────────────┘
                │  HTTP /api/*   (bearer-token auth, 127.0.0.1 only)
                ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI worker   (src/backend)                                   │
│  ─ app.py        app factory + 14 routers + /api/events SSE        │
│  ─ state.py      AppState: open project, edit mode, file lock      │
│  ─ jobs.py       JobManager: every heavy op as a cancellable job   │
│  ─ events.py     thread-safe SSE event bus                         │
│  ─ handlers.py   adapt pure Logic_* jobs to the job contract       │
│  ─ security.py   per-session bearer token                          │
│  ─ static.py     serve the built SPA (desktop only)               │
└───────────────┬───────────────────────────────────────────────────┘
                │  direct Python calls (no Qt)
                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Pure logic layer   (src/Application_Logic/Logic_*)               │
│  ProjectDatabase · ReleaseManager · SymbolMatcher · TestCase      │
│  Design · History · AI providers/context/tools · Code index/map · │
│  Code injection · Rhapsody import · Source store · Crypto · Lock   │
└───────────────┬───────────────────────────────────────────────────┘
                │
       ┌────────┴─────────┐
       ▼                  ▼
┌──────────────┐   ┌──────────────────────────────────────┐
│ core/        │   │  native/parser_rust  (rust_elf_parser) │
│ elf_parser   │──▶│  PyO3 ext: parallel ELF/DWARF + mmap   │
│ (+pyelftools │   │  fallback → pyelftools                 │
│  fallback)   │   └──────────────────────────────────────┘
└──────┬───────┘
       ▼
  MyProject.arch  ◄── single SQLite file (per-block encrypted content)
```

In **development** there are two servers: Vite serves the SPA on `:5173` and proxies `/api` to the worker on `:8765`. In the **packaged desktop app** there is only the worker, which serves the static SPA build itself (`create_app(serve_frontend=True)`); pywebview points the window at it.

---

## Data flow (ELF → matched table)

```
ELF Binary File (per release)
    │
    ▼
ELFParser (core/elf_parser.py)
    │ native rust_elf_parser first; transparent pyelftools fallback
    │ extracts: symbols, functions (params), structures, global_vars
    │ flush_to_db() bulk-inserts into the project DB, then frees RAM
    ▼
ProjectDatabase (Logic_Database.py)         ◄── single .arch SQLite file
    │ ELF data keyed by elf_hash so releases can share an import
    ▼
SymbolMatcher (Logic_Symbol_Matcher.py)
    │ loads only symbol/function name strings from the DB (cheap)
    │ rapidfuzz fuzzy matching with a configurable threshold
    ▼
Architecture / Releases routers (backend/routers/*)
    │ build the ports × columns matrix for the active model + release
    ▼
React Workspace view (frontend/src/views/Workspace.tsx)
    │ PortsTable renders rows (ports) × columns (match, state, review, result…)
    ▼
Save → ProjectDatabase → .arch SQLite (on disk)
```

ELF data is parsed **once**, flushed to SQLite keyed by `elf_hash`, and then served from the DB; only the active release is materialised in memory and the matcher loads just name strings. This DB-backed lazy loading keeps large multi-release projects within a flat memory budget.

---

## Module responsibilities

### Desktop shell — `src/desktop/`

| Module | Role |
|--------|------|
| `main.py` | Spawns the worker, waits for it to report its port and become ready, opens a native pywebview window pointed at the worker, and exposes native file dialogs + the session token to the SPA via pywebview's `js_api`. The token reaches the SPA through `js_api` / the URL fragment — **never over HTTP**. |
| `worker.py` | Child entrypoint: binds an OS-assigned port, reports it to the parent over a pipe, and serves the FastAPI app with uvicorn until the parent goes away. Kept free of any GUI import so it is unit-testable headless. |

### Backend worker — `src/backend/`

| Module | Role |
|--------|------|
| `app.py` | `create_app()` wires the singletons (`EventBus`, `AppState`, `JobManager`) onto `app.state`, binds the event loop to the bus at startup, and mounts the 14 routers + `/api/health`. Module-level `app` for `uvicorn backend.app:app`. |
| `state.py` | `AppState` — headless project lifecycle. Owns the open `ProjectDatabase`, the Qt-free `ArchitectureManager`/`ReleaseManager`, the project path, edit mode, and file-lock state. **View-only is enforced server-side** with `PRAGMA query_only=ON`. Routers read/mutate the DB through here. |
| `events.py` | The SSE event bus. A single `/api/events` stream carries job progress, `db-changed`, and lock events. `publish` is thread-safe (`call_soon_threadsafe`) because publishers are usually worker threads. |
| `jobs.py` | `JobManager` — one contract for every heavy operation: `POST /api/jobs/{kind}` → `202 {job_id}`, polled via `GET /api/jobs/{job_id}`, cancelled via `…/cancel`, progress streamed over SSE. A handler is `fn(params, progress, cancel_event) -> result`. |
| `handlers.py` | Adapts each pure `Logic_*` job function to the `(params, progress, cancel_event)` contract and registers it by kind. Heavy jobs (`build_code_map_job`, `run_release_diff`, ELF parse) open their own SQLite connection on the worker thread so a build can run while the main connection is busy. |
| `security.py` | Per-session bearer-token auth (`require_token` dependency). The worker binds `127.0.0.1` only, but every request must still carry the session token (set via `ARCH_API_TOKEN` env or auto-generated). Accepts `Authorization: Bearer <token>` or a `?token=` query param (for the SSE EventSource). |
| `static.py` | Serves the built React SPA from `frontend/dist/` in the packaged app. Static files are intentionally unauthenticated (just the shell); all data flows through token-guarded `/api/*`. |

#### Routers — `src/backend/routers/`

| Router | Surface |
|--------|---------|
| `project.py` | `/api/project/{new,open,save,close,status}` — project lifecycle (master password optional; `None` → plaintext). |
| `architecture.py` | The architecture matrix plus `/api/models` CRUD + `/ports` (create, bulk, patch, delete), model `state` transitions, and activate. |
| `releases.py` | `/api/releases` CRUD, `activate`, `branch`, `unfreeze`, `restore`, `source` attach/detach, `result-column`, `compare`, `lineage`. |
| `baselines.py` | Baseline diffs. |
| `symbols.py` | `/api/symbols` + re-match. |
| `codemap.py` | `/api/codemap` (+ `function/{name}`, `graph`). |
| `changelog.py` | `/api/changelog` (+ `diff`) — release source diffs. |
| `ai.py` | `/api/ai/{providers,prompts,mindmap,chat,parse-hlt}` + Copilot device-flow login. |
| `imports.py` | `/api/import/{analyze,read,rhapsody}` — spreadsheet / Rhapsody import. |
| `injection.py` | `/api/injection/*` — test projects, hooks (injections), files, build, export. |
| `testdesign.py` | Test Case Design templates + preview + export. |
| `fs.py` | Native folder/file picker bridge. |
| `prefs.py` | App-data preference/recents store (mirrors UI prefs server-side). |
| `jobs.py` | Generic job submit/poll/cancel + `/api/events` SSE. |

### Pure logic layer — `src/Application_Logic/`

Qt-free modules that hold the actual business logic. The worker (and the test suite) drive these directly.

**Persistence & lifecycle**
- `Logic_Database.py` — `ProjectDatabase`: SQLite-backed storage for one `.arch`. Owns the full schema and typed CRUD for project meta, column layout, models + rows, releases + rows, ELF data tables, baselines, test-case design, history, AI mind maps/diffs, source files, and test-injection data. There is no JSON-on-disk project format.
- `Logic_New_Project.py` — new-project import sequencing (run as worker jobs).
- `Logic_File_Locking.py` — `FileLockManager`: the View-Only / Exclusive-Edit model via a `<project>.arch.lock` sidecar carrying owner + heartbeat; stale locks are reclaimable.
- `Logic_Column_Layout.py` — project-global column-layout rules (Qt-free), enforced by the API and reused by the React column customizer. Cell keys are migrated across every model's rows on rename/delete.

**Models, releases, matching, results**
- `Logic_Architecture_Models.py` — multiple architecture models per project (create, duplicate, soft-delete, restore, reorder).
- `Logic_Release_Manager.py` — `ReleaseManager`: software releases + baselines; ELF shared by `elf_hash`; lazy loading of the active release only.
- `Logic_Symbol_Matcher.py` — `rapidfuzz` fuzzy matching over DB-loaded name strings (`find_best_match`, `find_top_matches`, threshold).
- `Logic_Release_Results.py` — per-release validation result derivation (Pass / Block / No Result / Not Run).
- `Logic_Release_Source_Picker.py` — shared release-dropdown helper for the source pickers (every "pick a folder" became a release dropdown).

**Source, code map, change log**
- `Logic_Source_Store.py` — source-provider abstraction (`FilesystemSourceProvider` for a local folder; a DB-backed provider for release-keyed source) so parsing/diff/AI context are decoupled from where source bytes live.
- `Logic_Code_Index.py` — stdlib-only C indexer: `build_index(path) -> CodeIndex` (functions / globals / call_graph / file_functions).
- `Logic_Code_Map.py` — `build_code_map(parser, code_index)` joins DWARF facts to the C call graph **by function name** (with C++ demangling) into a `CodeMap`.
- `Logic_Change_Log_Tab.py` — release-to-release source diff logic.
- `Logic_Rhapsody_Import.py` — Rhapsody path-based export detection and parsing.

**Test design, injection, history**
- `Logic_TestCase_Design.py` — the Markdown template language (`[Column]` tokens + `#if` conditionals), live preview, operation grouping, and bulk/individual `.md` export.
- `Logic_Code_Injection.py` — the injection matching engine: hooks anchor to the *text* of surrounding lines (not line numbers) so they re-find their spot when upstream source shifts.
- `Logic_History.py` — `HistoryManager`: release-scoped change history, obfuscated at rest and protected by an append-only HMAC hash-chain (`verify_history_chain()`).

**AI subsystem**
- `Logic_AI_Providers.py` — adapters for Copilot / Anthropic / OpenAI / Gemini behind one interface (`generate`, `generate_with_tools`), a per-provider tool-calling capability matrix, model context windows, and circuit breakers (turns / calls / bytes).
- `Logic_AI_Credentials.py` — per-user Fernet-encrypted credential store (`credentials.aikeys` in the OS config dir). API keys + the Copilot OAuth token; **the project file never stores keys**.
- `Logic_AI_Context.py` — pure builders: `build_mind_map`/`mind_map_to_text`, source hashing/diffing, staleness checks, requirements parsing, prompt/rules meta.
- `Logic_AI_Tools.py` — `ToolExecutor` with sandboxed read-only tools (`read_file`, `search_code`, `get_call_graph`, …) confined by a realpath path-jail to the source root.
- `Logic_AI_Generation.py` / `Logic_AI_Chat.py` — the generation and agentic-chat orchestration.

**Security & crypto**
- `Logic_Block_Crypto.py` — per-block (per-category) content encryption: the `.arch` is a plaintext SQLite file; only sensitive content columns are encrypted, each under its own per-category Fernet key. Replaces the old whole-file encryption.
- `Logic_Crypto.py` / `Logic_Security.py` — master-password hashing (`bcrypt`) and key derivation; gates Test Mode.

### Core & native parser

- `src/core/elf_parser.py` — `ELFParser`. Tries the native `rust_elf_parser` first (`_try_native_extract()` maps its JSON onto the in-memory contract) and falls back transparently to **`pyelftools`** on any error. Extracts the symbol table + DWARF (params, structures, globals) and provides Capstone disassembly for sub-call analysis. `flush_to_db()` / `load_from_db()` back the SQLite design; `export_elf_cache()` / `import_elf_cache_to_db()` give a portable JSON cache for fast re-import. The active backend is surfaced in `get_statistics()`.
- `src/native/parser_rust/` — `rust_elf_parser`, a PyO3 Rust extension (built with **maturin**) that parses ELF symbols + DWARF with parallel traversal and `mmap`. Exposes `parse_elf(path)` (JSON) and `compute_md5(path)`. Bundled into the packaged app; CI builds it on all three platforms.

### Frontend — `src/frontend/src/`

A Vite + React + TypeScript SPA; Monaco for code editing.

| Area | Contents |
|------|----------|
| `views/` | The 7 workbench views: `Workspace`, `TestDesign`, `AIGeneration`, `AIChat`, `CodeMap`, `ChangeLog`, `TestCodeInjection`. |
| `components/` | Shared UI — `Titlebar`, `Sidebar`, `PortsTable`, `Inspector`, `Preferences`, import/column/release dialogs, and `tutorial/` (the in-app interactive guides + `TutorialShell`). |
| `api/` | The typed `/api/*` client; attaches the bearer token and exposes the SSE subscription. |
| `native.ts` | Reads the session token from the URL fragment (`#token=…`) or `VITE_API_TOKEN`, and bridges native file pickers. |
| `theme/` | `macos.css` — the app's styling, including the tutorial/demo widgets. |
| `settings.ts`, `prefs.ts`, `recents.ts`, `update.ts`, `columns.ts`, `markdown.ts`, `monaco.ts` | Client state, preferences mirroring, recents, update checks, column model, markdown + Monaco helpers. |

---

## Background jobs & live updates

Every operation that can take more than a moment — ELF parsing, code-map build, release diff, AI generation — runs as a **job**, not a blocking request:

1. The SPA `POST`s to `/api/jobs/{kind}` (or a feature route that submits one) and gets back a `job_id`.
2. The job runs on a worker thread with its own SQLite connection; it reports progress through a `progress(message, percent)` callback.
3. Progress, `db-changed`, and lock events fan out over the single **`/api/events` SSE** stream; the SPA updates in place.
4. `POST /api/jobs/{job_id}/cancel` sets a cancel event the handler checks cooperatively.

This keeps the UI responsive and gives every long task uniform progress, cancellation, and error reporting.

---

## Security model

- **Local bearer token.** The worker binds `127.0.0.1` only; every `/api/*` call must carry the per-session token, which reaches the SPA through pywebview's `js_api` / the URL fragment, never over the network.
- **Server-side view-only.** Read-only mode is enforced with `PRAGMA query_only=ON`, so a view-only session physically cannot write — not just a disabled button.
- **Exclusive-edit file lock.** A `<project>.arch.lock` sidecar (owner + heartbeat) means a teammate opening a project that's being edited sees who holds it instead of clobbering it.
- **Per-block content encryption.** The `.arch` is a plaintext SQLite container; sensitive content columns are encrypted per-category under their own Fernet keys (`per-block-v1`). Legacy whole-file `ARCHENC1` projects auto-migrate on open.
- **AI credentials are per-user, never in the project.** Keys + the Copilot OAuth token live in a Fernet-encrypted store in the OS config dir.
- **Tamper-evident history.** The change log is obfuscated at rest and protected by an append-only HMAC hash-chain.
- **Master password.** `bcrypt`-hashed; gates Test Mode and unfreezing baselines.

---

## Project file structure (`.arch` SQLite database)

A project is **one SQLite file**. The database and its sidecars sit together:

```
MyProject.arch                # the SQLite database (the whole project)
MyProject.arch.lock           # exclusive-edit lock (owner + heartbeat), when held
MyProject.arch.elf_caches/    # exported ELF JSON caches for fast re-import
```

### Database schema (selected tables)

| Table | Holds |
|-------|-------|
| `project_meta` | Key/value settings, schema version, master-password hash, integrity HMAC |
| `column_layout` | The project-global column layout |
| `architecture_models` | Models (with soft-delete) |
| `architecture_rows` | Port rows, cells keyed by column name, per model |
| `releases` / `release_rows` / `release_results` | Releases, their port snapshots, and per-release results |
| `release_column_metadata` | Per-release result columns |
| `elf_index` / `elf_symbols` / `elf_functions` / `elf_structures` / `elf_global_vars` | ELF data keyed by `elf_hash` |
| `release_source_files` | Release-keyed C source (DB-backed source provider) |
| `ai_model_mindmaps` / `ai_code_diffs` / `ai_release_maps` | AI mind maps, computed source diffs, per-release code maps |
| `test_projects` / `test_project_files` / `test_code_injections` | Test Injection projects, helper files, and hooks |
| `test_case_design` | Test Case Design templates |
| `history` | Release-scoped, HMAC-chained change log |

---

## Build & packaging

**Run from source (development):**

```bash
pip install -r requirements.txt
( cd src/frontend && npm ci && npm run build )   # build the SPA once
PYTHONPATH=src python -m desktop.main             # native shell over the worker
```

For frontend iteration, run Vite (`npm run dev` in `src/frontend`) and point it at a worker (`uvicorn backend.app:app --port 8765` with `PYTHONPATH=src`); Vite proxies `/api` to it.

**Distributable:** a PyInstaller onedir bundle from `ArchitectureValidatorDesktop.spec`, which builds the SPA and the Rust parser wheel first:

- **macOS / Linux:** `scripts/build_desktop.sh`
- **Windows:** `scripts/build_desktop.ps1`

---

## Testing

Per the project's testing strategy, the **logic layer and API are covered by automated tests**; the React UI is verified manually (and via the in-app interactive guides). Heavy jobs are tested headlessly against the FastAPI `TestClient`, which exposes `app.state.token` so tests can authenticate. The desktop shell's `worker.py` is deliberately GUI-free so it can be unit-tested without pywebview.
