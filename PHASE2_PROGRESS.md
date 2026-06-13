# Phase 2 Progress — React Frontend — 🔶 IN PROGRESS (started 2026-06-13)

Tracking document for Phase 2 of [pywebview_react_migration_plan.md](pywebview_react_migration_plan.md) (§4).
Phases 0 & 1 complete ([PHASE0_PROGRESS.md](PHASE0_PROGRESS.md), [PHASE1_PROGRESS.md](PHASE1_PROGRESS.md));
the logic layer is Qt-free and the FastAPI worker exposes 44 routes over HTTP+SSE.

**Goal (§4):** the six views rebuilt as a React SPA against the Phase 1 API. Develop in a
plain browser (`uvicorn` + `vite dev`, hot reload, real devtools). Exit = the feature-parity
checklist (§7) ticked in the browser.

> **First slice DONE & verified in-browser: the Workspace (Main Table).** macOS-classic theme
> locked in (design_survey winner). Frontend scaffolded (Vite + React + **TypeScript**),
> `npm run build` clean. Live round-trip proven against the real worker on the
> `CodeMapTest.arch` dataset (35 models, active model 385 rows): virtualized table renders,
> status pills colour correctly, and a Port-State pill edit persists to the DB and re-renders
> green — no console errors.

## Dev workflow

```
# worker (uses the v1 venv; src on PYTHONPATH because backend imports Application_Logic.*)
PYTHONPATH=src ARCH_API_TOKEN=dev-token \
  /Users/alex/Git_Projects/Embeded-Software-Architecture-Validation/.venv/bin/python \
  -m uvicorn backend.app:app --port 8765

# frontend (Vite proxies /api → 127.0.0.1:8765; token from .env.development)
cd frontend && npm install && npm run dev      # http://localhost:5173
```

- **Auth in dev:** `frontend/.env.development` sets `VITE_API_TOKEN=dev-token`, which must
  match the worker's `ARCH_API_TOKEN`. In Phase 3 pywebview injects `window.__ARCH_TOKEN__`
  instead (the client prefers that global, falling back to the env var).
- **No project bundled:** point the launcher at an existing `.arch`. Rich dev dataset:
  `/Users/alex/Downloads/GIT/ForTesting/CodeMapTest/CodeMapTest.arch` (35 models; active
  `LedAdapter_SwPkg` = 385 rows; pills are mostly "In Work" + one "Not Reviewed").
  To test editing without mutating real data, copy it to /tmp and open exclusive.

## Architecture (built)

```
frontend/
├── package.json / vite.config.ts / tsconfig*.json / .env.development
├── index.html
└── src/
    ├── main.tsx                # React root + theme import
    ├── App.tsx                 # status gate (Launcher vs shell), titlebar, banners,
    │                           #   SSE lock-event handling, save, toast
    ├── theme/macos.css         # macOS-classic tokens (from design_survey/02) + --v-* shared tokens
    ├── columns.ts              # logic_key → render role; match-col detection; pill palettes; conf parse
    ├── api/
    │   ├── client.ts           # single fetch wrapper + bearer token + eventsUrl()  (plan §4.1 #1)
    │   ├── useSSE.ts           # one EventSource hook for the /api/events stream     (plan §4.1 #2)
    │   ├── hooks.ts            # useResource + useStatus/useModels/useColumns/useReleases/usePorts
    │   └── types.ts            # TS mirrors of the worker JSON shapes
    ├── recents.ts              # recent-projects list (localStorage; survives pywebview reloads)
    ├── components/
    │   ├── StartScreen.tsx     # launcher: New/Open cards + recent projects (plan §4.3)
    │   ├── FolderPicker.tsx    # modal dir/.arch browser backed by /api/fs (dev stand-in for native dialog)
    │   ├── Titlebar.tsx        # doc title + 6-tab segmented control + import/columns + Save
    │   ├── Sidebar.tsx         # models (row-count badges) + release picker + source status + actions
    │   ├── PortsTable.tsx      # TanStack Virtual table; pill cells w/ dropdown; confidence chips; kebab
    │   ├── Inspector.tsx       # selected-row actions strip (no right-click-only — plan §4.2)
    │   ├── StatusBar.tsx       # lock/view-only/lost + release·model + ports·reviewed counts
    │   └── Menu.tsx            # shared popup menu (pills + kebab), outside-click/Esc close
    └── views/
        └── Workspace.tsx       # ties it together: models/columns/ports/releases, search, selection,
                                #   cell edit (PATCH), add/delete/duplicate/retire, re-match job
```

**Key design decisions**
- **TypeScript** — the plan calls for a *typed* API client; types mirror the router JSON.
- **Column rendering from `logic_key`, no Qt classes.** `resolveColumns()` maps each column's
  `type` to a render role. The **match column has type `"Static Text"`** in real data — it's
  identified positionally as *the column immediately after a Port/Function/Variable Search
  column* (mirrors `Logic_Symbol_Matcher.search_specs_from_layout`). Pill palettes
  (Released/In Work/Retired/Deleted; Not Reviewed/In Review/Reviewed/Broken Link) ported
  verbatim from `src/UI/column_types.py`.
- **Virtualized from day one** (§9 risk): TanStack Virtual over a `<table>` with top/bottom
  spacer rows; `?limit=5000` page (server is already paged for bigger sets).
- **Three reusable API primitives** (§4.1): `client` fetch wrapper, `useSSE`, `useResource`.
  Reads refetch wholesale on SSE `db-changed`/`lock` rather than caching — simplicity first.
- **No right-click-only actions** (§4.2): every row action is in the visible kebab (⋯) menu
  AND the inspector strip; pills edit via left-click dropdown.

## Verified in-browser (this slice)

- Launcher opens a project (view + exclusive); status gate swaps to the workspace shell.
- Sidebar lists 35 models with live row-count badges; clicking switches the active model.
- Virtualized table renders the 385-row model smoothly; horizontal scroll exposes all columns.
- Status pills colour correctly: red "Not Reviewed", yellow "In Work" (+ green "Released" after edit).
- View-only mode: banner shown, pills non-editable (no ▾), write controls disabled.
- Exclusive mode: pill dropdown → `PATCH /models/{id}/ports/{row}` → **persisted to DB** →
  pill re-renders green. Save, Add Port, Re-match enabled.
- No console errors/warnings; `npm run build` (tsc + vite) clean.

## TODO — remaining Workspace parity (§7) before moving to other views

- Column customizer (add/remove/reorder/rename/hide; TC. ID pinned; reviewed-column locking)
  — backend needs the rename/delete validation rules extracted to logic (noted in Phase-0
  `column_customizer.py` header) so the API can enforce server-side.
- Fuzzy match candidate picker (the `GET /api/symbols` dropdown with scores) + manual-override
  (purple) tracking surfaced in the cell.
- Model management dialog (create/rename/duplicate/soft-delete/restore) — APIs exist.
- Port-state propagation confirmation UI (#8.2) — the two-step `/state/preview` → `/state`
  flow when a *model's* status changes (distinct from per-row pill edits, which are plain PATCH).
- Excel/Rhapsody import wizard (compose `/import/analyze` + `/ports/bulk` + `fuzzy_rematch`).
- Retired/deleted visibility toggle; symbol filter; release results columns; baselines (create/load/compare).
- Job progress UI: a `useJob(kind)` hook wrapping start/poll(SSE)/cancel (plan §4.1 #3) —
  re-match / generate / parse-elf currently fire-and-forget with a toast.

## Then (later Phase 2 slices, plan §4 view order)

Code Map (ELK.js/React Flow + source pane, #2C/#2D) → Change Log (Monaco diff + AI summary) →
Test Design (CodeMirror template + live preview) → AI Generation + AI Chat (provider config,
SSE streaming, mind-map status, requirements import). Then Phase 3 (pywebview shell).

## Session log

- **2026-06-13 (a)** — Scaffolded `frontend/` (Vite + React + TS; deps `@tanstack/react-table`,
  `@tanstack/react-virtual`, `@types/node`). Built the macOS-classic theme, the three API
  primitives, typed resource hooks, the Launcher, and the full Workspace (titlebar, sidebar,
  virtualized ports table with editable status pills, inspector, status bar, banners, toast).
  `npm run build` clean. Verified the live round-trip in the preview browser against the real
  worker (`CodeMapTest.arch`): render, model switch, pill edit → DB persist → green re-render,
  no console errors. `.claude/launch.json` adds a `frontend` config (npm run dev :5173).
- **2026-06-13 (b)** — UX polish per Alex: **resizable table columns** (header/body vertical
  separators + drag grips on each header right-edge; widths in local state, seeded from the
  layout — persisting via PUT /columns deferred to the column customizer) and a **resizable
  sidebar** (drag divider, clamped 170–480px). Both verified by simulated drag in the browser
  (column +90px, sidebar +70px) and screenshot; `npm run build` clean.
- **2026-06-13 (c)** — **Start screen + folder picker** (Alex: "replace launcher first" +
  "backend folder picker"). New backend router `backend/routers/fs.py` — read-only
  `GET /api/fs/list` (dirs + .arch only, dotfiles hidden) + `GET /api/fs/home`, token-guarded,
  the dev stand-in for Phase-3 native dialogs (6 tests, `Tests/test_backend_fs.py`). Frontend:
  `StartScreen` (New/Open cards + recent-projects list from localStorage) replaces the old
  typed-path `Launcher` (deleted); `FolderPicker` modal browses real folders, selects an .arch
  (exclusive/view), or picks a destination + filename for New. Verified in-browser: navigate
  4 levels → select → open (view-only) → lands in Workspace (35 models) → recent recorded →
  reload shows it. Full suite **585 passed** (579 + 6 fs); `npm run build` clean; no console
  errors. **NEXT: the dedicated New-Project create form** (ELF/source/release/first-model setup).
- **2026-06-13 (d)** — Onboarding polish per Alex: (1) **New Folder** in the picker —
  `POST /api/fs/mkdir` (rejects separators / existing; +3 tests) wired to a "＋ New Folder"
  affordance in New mode; (2) **Miller-columns** (Finder-style) picker — `FolderPicker` rewritten
  from a single list to a horizontal strip of folder listings (click a folder → next column opens
  to its right; deepest column auto-scrolls into view); (3) **view-only is now the default** open
  mode — picker checkbox flipped to "Open for editing (exclusive lock)", and a recent's main click
  opens view-only with a ✏️ secondary action for exclusive. All verified in-browser (drill 5 cols
  deep → open view-only; New Folder → create project inside → exclusive). Full suite **588 passed**
  (+3 mkdir); `npm run build` clean; no console errors.
- **2026-06-13 (e)** — Miller-columns polish per Alex: **thicker draggable dividers** between
  columns (`.picker-coldiv`, 7px with a center grip line, accent on hover), per-column **resize**
  (drag), and **double-click-to-fit** (sizes a column to its widest row via `.picker-name`
  scrollWidth). Verified in-browser (drag col0 +90px → 326; dbl-click col1 fit → 246).
  `npm run build` clean; no console errors.
- **2026-06-13 (f)** — **At-rest project encryption + master-password UX** (Alex upgraded the
  "password request" to full DB encryption). Approach (Alex-approved): **session temp file**
  (decrypt the .arch into a private 0700 temp dir, run the existing file-backed SQLite/WAL/jobs
  architecture unchanged, re-encrypt on save) — chosen over pure in-memory because the Phase-1
  job system relies on a *second connection to the same path*, which `:memory:` can't provide.
  Crypto = `cryptography` Fernet + PBKDF2-HMAC-SHA256 (no SQLCipher → EDR-safe). New module
  `src/Application_Logic/Logic_Crypto.py` (magic `ARCHENC1` | salt | token; `encrypt/decrypt_file`,
  format detection, `PasswordRequired`/`PasswordInvalid`). **Dual-mode** open: plaintext SQLite
  (magic `SQLite format 3\0`) opens directly (legacy/dev); encrypted needs the password.
  **Test bypass:** no password OR `master123` → saved plaintext (keeps the 588 fixtures working);
  `master123` blacklisted in the frontend setup form. `backend/state.py` rewired
  (new/open/save/close: provision temp db-file, encrypt-to-disk, purge+shred temp on close/atexit;
  `_check_integrity` skips for encrypted since Fernet authenticates; `status.encrypted` added).
  `project` router: `password` on new/open; `PasswordRequired→401`, `PasswordInvalid→403`.
  Frontend: `PasswordDialog` (setup: confirm+blacklist+min-len; unlock: retry on 403); `StartScreen`
  New → folder-pick → **mandatory** master-pw setup → encrypted create; Open (picker/recents) →
  401 prompts, 403 retries. Verified in-browser: encrypted create (on-disk magic = `ARCHENC1`),
  blacklist/mismatch guards, close→reopen (wrong pw error → correct pw opens), temp dirs purged.
  Backend tests `Tests/test_backend_crypto.py` (7). Full suite **595 passed**; `npm run build` clean;
  no console errors.
- **2026-06-13 (g)** — **Onboarding completed to the main table + Finder polish** (Alex).
  Backend: `import_symbols` job (auto-detects ELF vs JSON by magic/extension → dispatches the right
  ElfImportTask path → keys the release to the ELF hash; mirrors parse_elf but type-agnostic);
  `/api/fs/list` gained an `exts` allow-list param (Import picker passes `.elf,.json`). +3 backend
  tests (jobs 2, fs 1). Frontend: **2-option New flow** — after the encrypted .arch is created, a
  choice dialog (Empty Project / Import); Import → Miller picker (.elf/.json) → release-name → create
  release + activate + `import_symbols` job (polled) → lands in the Workspace. **Finder polish on the
  Miller picker:** blue macOS folder + file SVG icons (`Icons.tsx`; also the Open Project card),
  **grip dots** on each column divider (drag/dbl-click affordance), and a clickable **breadcrumb
  path** (Macintosh HD › Users › … with folder icons + chevrons) replacing the plain text.
  Verified in-browser end-to-end: New → New Folder → name → master-pw → Import → pick sample.elf →
  R1.0 → import job → **main table** (model Architecture_1, release R1.0 active, symbols queryable,
  encrypted, exclusive). Full suite **598 passed**; `npm run build` clean; no console errors.
  **NEXT: Workspace parity** — column customizer, fuzzy match-candidate picker (+purple override),
  model-management dialog, port-state propagation #8.2 UI, Excel/Rhapsody import wizard, useJob(kind)
  progress hook (import currently polls inline).
- **2026-06-13 (h)** — **Preferences panel + light/dark theming + accent switcher** (Alex).
  `src/theme.ts`: theme mode (light/dark/**auto**=prefers-color-scheme, default auto) + accent,
  persisted in localStorage, applied to `<html>` (`data-theme`) and `--accent`/`--v-accent`;
  `initTheme()` runs in `main.tsx` before paint. **Full dark theme** via a token refactor of
  `theme/macos.css`: added semantic surface tokens (`--surface/--bar/--titlebar-bg/--row-alt/--hover/
  --statusbar-bg/--overlay/--v-warn-bg`), swept the hardcoded light literals onto them (white-on-accent
  `color:#fff` and box-shadows left intact), and a `:root[data-theme="dark"]` override block.
  `Preferences.tsx`: split-column modal (categories: Appearance active / AI Settings / Paths;
  AI+Paths are placeholders) — Theme segmented control + accent pills with the Linux-distro joke
  tooltips (Perfect Fedora / Bloated Ubuntu / Fresh Mint / Corporate Red Hat / Gamer Mode Bazzite /
  Elitist Arch) + a rainbow **Distro Hop (Custom)** pill → hidden `<input type=color>` → live
  `--v-accent`. Gear ⚙ entry points in the Titlebar and the StartScreen header (modal lives in App,
  available with or without a project open). Verified in-browser: split layout, Light/Dark/Auto flip
  (whole UI re-themes), accent click + custom hex both update `--accent`/`--v-accent` live and persist,
  tooltips correct, no console errors. `npm run build` clean. Backend untouched (suite stays **598**).
- **2026-06-13 (i)** — Preferences refinements per Alex: (1) **dark-mode readability fix** — global
  `button { color: inherit }` + `input/select/textarea { color: var(--text) }` (native controls don't
  inherit colour, so sidebar/inspector buttons rendered black-on-dark); (2) **theme-mode icons**
  (Sun/Moon/Auto SVGs in `Icons.tsx`); (3) accent pills **smaller (20px) + right-aligned**, rows are
  label-left/control-right (`.prefs-row`); (4) **removed redundant tooltips/hints** (kept aria-labels);
  (5) **custom in-app `ColorPicker.tsx`** (HSV square + hue slider + hex, app-styled) replacing the
  native OS colour dialog — drives `--accent`/`--v-accent` live. Fixed a bug where the picker was a
  child of the overlay (its clicks closed the whole dialog) by rendering it inside `.prefs`. Verified
  in-browser: icons show, pills compact/right-aligned, custom picker live-updates the accent
  (#da2121) across the UI and persists, no console errors. `npm run build` clean.
- **2026-06-13 (j)** — Appearance polish to macOS System-Settings style (Alex refs): (1) **theme
  preview cards** replace the segmented control — Light / Dark / **System** each show a mini
  app-window thumbnail (titlebar dots + accent/green/red/neutral lines; System = diagonal
  light/dark clip) with a radio + label; active card gets the accent ring; the accent line in the
  thumb reflects the chosen accent. (2) **multicolor pill polished** (clean `conic-gradient` at 22px,
  no solid-colour override). (3) **selected accent name shown** under the pills (the distro names —
  Perfect Fedora / Bloated Ubuntu / … / "Distro Hop (Custom)"), right-aligned like macOS "Multicolor".
  Verified in-browser: cards render + switch theme live, accent name updates per selection, custom
  picker still drives the accent. `npm run build` clean; no console errors.
- **2026-06-13 (k)** — Polish: (1) multicolor accent pill — replaced the `border` (which left a
  sub-pixel HiDPI gap with `background-clip`) with an `inset` box-shadow edge so the conic gradient
  fills the whole circle. (2) **Folder icons follow the theme accent** — `FolderIcon` now uses
  `currentColor` (two-tone via opacity); `.picker-icon`/`.crumb svg`/`.start-card-icon svg` set
  `color: var(--accent)`, with `.picker-row.sel .picker-icon → #fff` so the selected row's folder
  stays white on the accent fill. Files (`FileIcon`) remain neutral. Verified: folders recolor live
  with the accent (blue → mint), breadcrumb included; no console errors; `npm run build` clean.
