> ## ✅ RETIRED — migration complete (v3.0.0)
> This plan has been **fully executed**. The app now ships as a React SPA in a pywebview shell over
> a FastAPI worker, exactly as scoped below. This document is kept for historical reference only —
> for the current system design see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**. Safe to delete.

---

# Migration Plan: PyQt6 → pywebview + React + FastAPI (Path B)

> **Supersedes** `tauri_react_migration_plan.md`. Tauri was dropped after analysis: every
> benefit it provided here (a UI that cannot freeze) comes from the *process boundary*,
> not from Rust or the Tauri shell — and a pure-Python shell avoids a second binary for
> corporate EDR/whitelisting, a Rust toolchain in CI, sidecar lifecycle management, and
> the port-injection/CORS dance. If Tauri is ever wanted later (auto-updater, smaller
> installer), the React frontend and FastAPI backend built here move over unchanged.

This plan is written to be executed incrementally by AI coding assistants. Each phase
leaves the application **working and shippable**. Do not start a phase before the
previous one's exit criteria are met.

> **Status (2026-06-18): Phases 0, 1, 2 COMPLETE — ready to start Phase 3.**
> Logic layer is Qt-free (only comments/strings mention PyQt6); the FastAPI worker
> exposes all features over 13 routers (HTTP + SSE); all six React views are built and
> verified in-browser; `npm run build` is clean and the suite is green (634 passed).
> The per-phase progress trackers (`PHASE0/1/2_PROGRESS.md`) and the completed feature
> sub-plans were retired after this checkpoint; their history lives in git + memory.

---

## 0. Why we are doing this (read before coding)

Two real problems, confirmed by measurement:

1. **UI freezes ("not responding") on EDR-protected machines.** QThread workers share
   Python's GIL with the Qt event loop. CPU-bound Python in a worker starves the main
   thread; EDR makes every operation 5–10x longer so the starvation becomes visible.
   *Already partially fixed:* the Rust ELF parser now releases the GIL
   (`py.allow_threads` in `native/parser_rust/src/lib.rs`). The remaining pure-Python
   heavy paths (code-map build, source-into-DB copy, indexing) can only be fixed
   structurally — by moving them into a **separate OS process**.
2. **The Qt cross-thread model is hard to maintain** — for humans and for AI
   assistants. Queued signal/slot connections, QObject thread affinity, and
   "never touch widgets off the main thread" are niche, error-prone idioms.
   HTTP request/response + SSE progress streams are the most widely understood
   async pattern in existence.

Target architecture:

```
┌───────────────────────────────┐         ┌──────────────────────────────────┐
│  UI PROCESS                   │         │  WORKER PROCESS                  │
│  pywebview window             │  HTTP   │  FastAPI (uvicorn)               │
│  └─ OS webview renderer       │ ──────► │  ├─ de-Qt'd Application_Logic    │
│     (WebView2 / WKWebView —   │   SSE   │  ├─ SQLite (.arch)               │
│      renders out-of-process)  │ ◄────── │  ├─ rust_elf_parser (GIL-free)   │
│  React frontend (static)      │         │  └─ job manager (thread pool)    │
└───────────────────────────────┘         └──────────────────────────────────┘
```

- The UI process does **no heavy work, ever**. It cannot freeze.
- The worker process owns the database, parsers, fuzzy matching, AI calls, indexing.
- The worker is spawned with `multiprocessing.Process` (both ends are Python — no
  sidecar binary, no PyInstaller second artifact, one bundle like today).
- During development you don't even need pywebview: run uvicorn + Vite dev server
  and work in a normal browser with hot reload and devtools.

---

## 1. Target directory structure

Grown inside the existing repo — the PyQt app keeps living in `src/` until Phase 4
retires it. Nothing is deleted until the new UI reaches feature parity.

```
├── src/                          # CURRENT PyQt app — untouched until Phase 4
│   ├── Application_Logic/        # Phase 0 de-Qts these files IN PLACE
│   ├── UI/                       # retired at the end
│   └── main.py
├── backend/                      # Phase 1
│   ├── app.py                    # FastAPI app factory
│   ├── jobs.py                   # background job manager (start/progress/cancel)
│   ├── events.py                 # SSE event bus
│   └── routers/
│       ├── project.py            # new/open/save/status/lock
│       ├── architecture.py       # models, ports table CRUD, columns, import
│       ├── releases.py           # releases, baselines, sources
│       ├── codemap.py            # call graph, source lookup, defines
│       ├── changelog.py          # diffs, AI summary
│       ├── testdesign.py         # templates, preview, export
│       └── ai.py                 # providers, credentials, generation, chat
├── frontend/                     # Phase 2
│   ├── src/
│   │   ├── api/                  # typed client + SSE hooks (single fetch wrapper)
│   │   ├── components/           # Table, StatusPill, Sidebar, Toolbar, …
│   │   ├── views/                # Workspace, TestDesign, AIGen, AIChat, CodeMap, ChangeLog
│   │   └── theme/                # CSS variables — chosen via design_survey/
│   ├── package.json
│   └── vite.config.js
├── desktop/                      # Phase 3
│   └── main.py                   # pywebview shell: spawn worker, open window
├── design_survey/                # static HTML mockups for team review
└── Tests/                        # existing suite — stays green through Phase 0/1
```

---

## 2. Phase 0 — De-Qt the logic layer (the load-bearing phase)

**Goal:** every file in `src/Application_Logic/` becomes importable without PyQt6.
This is ~60% of the total migration effort and is valuable even if the migration
stopped here (simpler code, faster tests, AI-friendlier).

**21 of 33 logic files currently import Qt.** Work file-by-file; the PyQt app must
still run after every single file's conversion.

### 2.1 The conversion pattern

Replace Qt signals with a tiny dependency-free event emitter:

```python
# src/Application_Logic/events.py  (new, no Qt)
class Emitter:
    def __init__(self):
        self._subs: dict[str, list] = {}
    def on(self, event: str, fn) -> None:
        self._subs.setdefault(event, []).append(fn)
    def emit(self, event: str, *args, **kw) -> None:
        for fn in self._subs.get(event, []):
            fn(*args, **kw)
```

- `pyqtSignal(...)` → `Emitter` instance; `self.progress.emit(n)` →
  `self.events.emit("progress", n)`.
- `QThread` worker subclasses (`_GenWorker`, `_CodeMapWorker`, `_ChatWorker`,
  `_MindMapWorker`, `AIChangeLogWorker`, `TaskWorker`, `_ModelDiscoverThread`) →
  plain functions that take a `progress_cb` / `cancel_event` and run under
  `concurrent.futures`. **The thread management moves out of the logic layer
  entirely** — Qt code (until Phase 4) and FastAPI (after Phase 1) each provide
  their own executor.
- Dialog/`QMessageBox` calls inside logic → return values / raised exceptions /
  an injected `confirm(message) -> bool` callback. Logic never creates widgets.
- During the transition, the PyQt side bridges events back onto the GUI thread
  with one adapter (this is the only place queued delivery still exists):

```python
# src/UI/qt_bridge.py — temporary, deleted in Phase 4
class QtBridge(QtCore.QObject):
    relay = QtCore.pyqtSignal(str, tuple)
    def __init__(self, emitter):
        super().__init__()
        self.relay.connect(lambda ev, args: self._fire(ev, args))
        emitter.on_any = ...  # forward every emit into self.relay.emit (thread-safe)
```

### 2.2 Conversion order (dependency-driven, easiest first)

| Tier | Files | Notes |
|------|-------|-------|
| 1 — pure-ish | `Logic_Security`, `Logic_AI_Credentials`, `Logic_Column_Types`, `Logic_History`, `Logic_Symbol_Matcher` | Mostly incidental Qt imports; quick wins |
| 2 — data layer | `Logic_Database`, `Logic_Source_Store`, `Logic_Architecture_Models`, `Logic_Architecture_Baseline`, `Logic_Architecture_IO`, `Logic_Release_Manager`, `Logic_Release_Source_Picker` | DB + releases; the FastAPI core |
| 3 — heavy ops | `Logic_Code_Index`, `Logic_Code_Map`, `Logic_Change_Log_Tab` (diff engine), `Logic_Architecture_Import`, `Logic_Rhapsody_Import` | These are the freeze sources — convert their QThreads to `progress_cb` functions |
| 4 — AI stack | `Logic_AI_Providers`, `Logic_AI_Generation`, `Logic_AI_Chat`, `Logic_AI_Context`, `Logic_AI_Tools`, `Logic_AI_ProviderPanel` | Streaming → generator functions yielding chunks |
| 5 — app glue | `Logic_New_Project`, `Logic_Project_Saving`, `Logic_File_Locking`, `Logic_User_Interaction`, `Logic_TestCase_Design`, `Logic_Code_Map_Tab`, `Logic_Architecture_Table`, `Logic_Column_Customizer`, `Logic_Loading_Window` | Some of these are mostly UI glue and partially dissolve into routers/frontend |

### 2.3 Exit criteria

- `grep -rl "PyQt6" src/Application_Logic/` returns **zero** files.
- Full test suite passes (`pytest Tests/`) — tests shed their Qt fixtures as files
  convert, which also makes them faster.
- The PyQt app still works, now via `qt_bridge`.

---

## 3. Phase 1 — FastAPI worker process

**Goal:** the de-Qt'd logic exposed as a local HTTP API with SSE progress, runnable
standalone (`uvicorn backend.app:app --port 8765`) and testable with `httpx`/curl.

### 3.1 The job manager (one pattern for every heavy operation)

Every slow operation follows the same contract — this is the AI-legibility win,
so do not invent per-feature variations:

```
POST /api/jobs/{kind}            body: params        → 202 {"job_id": "..."}
GET  /api/jobs/{job_id}                              → {"status","progress","message","result?"}
GET  /api/events                 (single SSE stream) → job progress + db-changed + lock events
POST /api/jobs/{job_id}/cancel                       → sets the cancel_event
```

`jobs.py` owns a `ThreadPoolExecutor`, a job registry keyed by uuid, and pushes
every progress callback onto the SSE bus. Job kinds: `parse_elf`, `build_code_map`,
`index_source`, `import_architecture`, `fuzzy_rematch`, `create_baseline`,
`generate_tests`, `build_mind_map`, `release_diff`, `save_project`.

Inside the worker process, threads are fine for I/O-bound work; the GIL no longer
matters to the UI because the UI lives in another process. CPU-heavy parsing is
already GIL-free in Rust.

### 3.2 Core endpoints (beyond jobs)

- `POST /api/project/new|open|save|close`, `GET /api/project/status`
  (lock state, dirty flag, release, edit mode — view-only enforced server-side
  with `PRAGMA query_only=ON`)
- `GET/PUT /api/models`, `GET/PUT /api/models/{id}/ports` (paged),
  `PATCH /api/ports/{id}` (single-cell edit → returns affected cells so the UI
  can apply server-confirmed state), `GET/PUT /api/columns`
- `GET /api/symbols?kind=function&q=...` (fuzzy candidates with scores — feeds
  the match-picker dropdown)
- `GET /api/releases`, `POST /api/releases`, `POST /api/baselines`,
  `GET /api/codemap/graph?fn=...&back=1&fwd=1`, `GET /api/source/function/{name}`
- `POST /api/ai/chat` (SSE-streamed tokens), `GET/PUT /api/ai/providers`
- Port-state propagation (the `PortPropagationDialog` flow) becomes a two-step
  API: `POST /api/ports/{id}/state?dry_run=1` returns the affected-ports list,
  the UI shows the confirmation, then commits with `dry_run=0`.

### 3.3 Lifecycle & file locking

- `desktop/main.py` spawns the worker with `multiprocessing.Process`; the worker
  binds port 0 (OS-assigned), reports the actual port back over a `Pipe`, and
  the parent passes the URL to the frontend via pywebview's `js_api`.
- Worker watches the parent: if the parent PID dies, the worker releases the
  edit lock and exits (no zombie servers holding `.arch` locks).
- The existing `Logic_File_Locking` heartbeat runs inside the worker on a timer;
  lock-lost events go out over SSE so the UI can drop to view-only with a banner
  (same UX as today).
- Bind to `127.0.0.1` only; generate a per-session bearer token, pass it to the
  frontend at startup, require it on every request (other local users on a
  shared machine must not be able to drive the API).

### 3.4 Exit criteria

- Every feature of the app is reachable through the API with **no Qt imports
  anywhere in `backend/`** (`grep -rl PyQt6 backend/` → empty).
- API-level tests (httpx against the FastAPI TestClient) cover the job manager,
  project open/save, port editing, and locking.
- The legacy PyQt app still works (it keeps calling the logic layer directly —
  it does NOT need to be ported to the API; it retires in Phase 4).

---

## 4. Phase 2 — React frontend

**Goal:** the six views rebuilt as a React SPA against the Phase 1 API.
Develop in a plain browser: `uvicorn` + `vite dev` — hot reload, real devtools.

1. **Foundations first:** theme CSS variables (winner of `design_survey/`), the
   typed API client (one `fetch` wrapper + one `useSSE` hook + one `useJob(kind)`
   hook that wraps start/progress/cancel — every view reuses these three).
2. **View order** (risk-first, value-first):
   1. **Workspace** (the must-have): virtualized table (TanStack Table +
      TanStack Virtual — thousands of rows), status-pill dropdowns, fuzzy-match
      cell picker with candidate scores, column customizer, model sidebar,
      release selector, action toolbar. **Design rule: no right-click-only
      actions.** Every row action is also in a visible kebab (⋯) menu; every
      table action is in the toolbar; right-click becomes a shortcut, never the
      only path.
   2. **Code Map**: graph rendering with ELK.js layout + SVG (or React Flow);
      function search panel, depth controls, detail card, source pane with
      Ctrl-click navigation and hover tooltips (port of #2D features).
   3. **Change Log**: side-by-side diff (Monaco diff editor in read-only mode —
      free syntax highlighting), file tree, AI summary panel.
   4. **Test Case Design**: template editor (CodeMirror) + live preview pane.
   5. **AI Generation + AI Chat**: provider config, streaming chat (SSE),
      mind-map status, requirements import.
3. **Startup flow**: launcher screen (New / Open View-Only / Open Exclusive-Edit)
   as the SPA's initial route — same three-button simplicity as today.

Exit criteria: feature-parity checklist (§7) fully ticked in the browser.

---

## 5. Phase 3 — pywebview desktop shell  ← NEXT

**Goal:** the SPA in a native window, one packaged artifact.

> **Status (2026-06-18): Phase 3 core built; only on-machine packaging validation remains.**
> Done: `backend/static.py` serves the SPA via `create_app(serve_frontend=True)` (frozen-aware
> path; `/api/*` still wins; 7 tests). `desktop/worker.py` spawns the worker with
> `multiprocessing` (spawn), hands the OS-assigned port back over a Pipe that doubles as a
> **lifeline** — closing the parent end triggers a graceful uvicorn shutdown so the `.arch`
> lock is released (no zombie-lock); 5 headless tests. `desktop/main.py` is the pywebview
> shell; `JsApi` exposes `get_token` (token never crosses HTTP), `set_title`, and native file
> dialogs. Frontend `native.ts` + `main.tsx` bootstrap the token through the bridge when the
> SPA is loaded with `?desktop=1`. Window title (project · release · edit/view) and the
> ⌘/Ctrl-S / ⌘/Ctrl-F shortcuts are wired in `App.tsx`. `scripts/freeze_probe.py` passes
> (worst UI-loop latency ~2.5 ms under 4 CPU-bound worker jobs, threshold 50 ms).
> **Decision (Alex):** keep the custom `/api/fs` Miller-columns picker — it already returns
> real worker-side paths inside pywebview; the `js_api` dialog methods stay wired but unused.
> **Remaining:** `ArchitectureValidatorDesktop.spec` (separate onedir spec, written but
> unbuilt) needs a real build + smoke test on macOS and an EDR Windows box, including the
> WebView2-runtime fallback. Native dialogs and a backend `dirty` flag for the title are
> deferred (not blockers).

- `desktop/main.py`: spawn worker → wait for port → `webview.create_window()`
  pointing at the worker's statically-served frontend build (FastAPI serves
  `frontend/dist/` — no second server) → `webview.start()`.
- Native file dialogs via pywebview's `window.create_file_dialog` exposed through
  `js_api` (browser file inputs can't return real paths; the app needs real
  paths for `.arch`/ELF/source folders on network shares).
- Keyboard shortcuts (Ctrl/Cmd-S save, Ctrl/Cmd-F table search) handled in React.
- Window title shows project + edit-mode + dirty flag, as today.

**Packaging:** extend the existing PyInstaller **onedir** spec (`COLLECT` — keep
onedir; onefile would re-trigger the EDR small-file penalty on every launch).
Bundle `frontend/dist/` as data files. On Windows, WebView2 runtime is present on
Win10/11 by default; add the bootstrapper to the installer as a fallback. Still
**one executable for IT to whitelist**; code-sign it if the org can issue a cert.

---

## 6. Phase 4 — Cutover

- Side-by-side period: both UIs ship from one repo (PyQt entry `src/main.py`,
  new entry `desktop/main.py`); the team uses the new one, falls back if blocked.
- When the parity checklist (§7) is signed off: delete `src/UI/`, `src/main.py`,
  `qt_bridge.py`, drop PyQt6 from `requirements.txt`, update CI and the
  flatpak manifest, move `src/Application_Logic` → `backend/logic`.

---

## 7. Feature-parity checklist (cutover gate — nothing ships missing)

Workspace: port table (virtualized, inline edit) · column customizer
(add/remove/reorder/rename/hide, TC. ID pinned, reviewed-column locking) ·
fuzzy match + candidate picker + manual override tracking · review status /
port state pills · port-state propagation confirmation (#8.2) · retired/deleted
visibility toggle · multi-model sidebar (create/rename/duplicate/soft-delete/
restore) · Excel/CSV import · Rhapsody import · symbol filter.
Releases: release manager · release source picker (per-release dropdowns, #2E) ·
baselines (create/load/compare) · per-(model,release) maps · release results columns.
Code Map: call graph w/ depth controls · source-derived fallback (#2C) ·
function details · matched globals · `#define` tooltips, Ctrl-click nav (#2D) ·
source folder linking + re-index.
Change Log: release-vs-release side-by-side diff · file tree · AI summary.
Test Design: template language + conditionals · grouping modes · live preview ·
export.
AI: provider config (Copilot/Claude/OpenAI/Gemini) + encrypted credentials ·
test generation · agentic chat + tools · mind maps · requirements import.
Collaboration: exclusive-edit lock + heartbeat · view-only mode (server-enforced) ·
lock-lost banner · auto-save · change history log · DB activity tracking.
App: launcher (New/Open-VO/Open-EE) · loading progress for all long jobs ·
status bar (lock, save time, release, row count) · keyboard shortcuts.

---

## 8. Testing strategy (per the project's standing policy)

- Logic-layer tests: survive Phase 0 (they get *simpler* — no Qt fixtures).
- API tests: new in Phase 1, FastAPI TestClient, cover routers + job manager.
- Frontend: manual testing per current policy; regression tests only when an
  interface bug recurs.
- A `scripts/freeze_probe.py` harness: drives a worker-process job while
  asserting the UI process's event loop latency stays < 50 ms — the structural
  no-freeze guarantee, run on an EDR machine before cutover.

## 9. Risks

| Risk | Mitigation |
|------|------------|
| Phase 0 scope creep (21 Qt-coupled files) | File-by-file, app always working, tests green per file; tiers ordered easiest-first |
| Table performance with thousands of rows in the webview | Virtualize from day one; paged API; server-side filter/sort |
| pywebview platform quirks (dialogs, menus) | Native dialogs via js_api early in Phase 3; everything else lives in HTML where behavior is uniform |
| WebView2 missing on locked-down Windows images | Installer bootstrapper; verify on a real EDR machine in Phase 3 week 1 |
| Team rejects web UI feel | design_survey decided *before* Phase 2; Workspace built first and demoed |
| Long side-by-side period drifts | Parity checklist is the single cutover gate; no new features land in the PyQt UI after Phase 2 starts |
