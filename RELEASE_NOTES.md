# v3.0.2 — Hotfix: Windows blank/white window

A follow-up Windows fix. On some machines the app opened to a **blank white
window** (and only worked when "Run as administrator" was used). macOS and Linux
are unaffected.

## 🐛 Fixed
- **No more blank white window on Windows.** The embedded WebView2 control stores
  its browser profile in a "user data folder"; left unset it lands next to the
  `.exe`, which fails to initialise when the app runs from a read-only or
  permission-restricted location (Program Files, a VM shared folder, a locked-down
  extract) — leaving the window white unless launched as administrator. The app
  now puts that folder in a guaranteed per-user-writable location
  (`%LOCALAPPDATA%\ArchitectureValidator\WebView2`), so it works as a normal user.

---

# v3.0.1 — Hotfix: Windows launch crash

A maintenance release that fixes the Windows desktop build failing to start. No
functional changes to the app itself — **macOS and Linux behave exactly as in
3.0.0**; if 3.0.0 already runs for you, 3.0.1 only adds the Windows fix and better
diagnostics.

## 🐛 Fixed
- **Windows app no longer crashes on launch.** The native window backend
  (pywebview → winforms → pythonnet/.NET) failed to initialise on several
  machines — symptoms ranged from a silent exit, to a blank white window, to
  `Failed to resolve Python.Runtime.Loader.Initialize`. The build now ships
  pythonnet and its `clr_loader` .NET bootstrap shims with a pinned, matched
  version so the runtime loads correctly.
- **Crashes are no longer silent.** If the app fails to start, a full traceback is
  now written to `%LOCALAPPDATA%\ArchitectureValidator\crash.log`.
- **Missing-prerequisite check.** On Windows the app now verifies the WebView2
  Runtime and .NET Framework are present at launch, and — if either is missing —
  shows a dialog linking straight to Microsoft's download page instead of
  failing cryptically.

## 📦 Linux packaging
- Linux now ships proper distribution packages — **`.deb`, `.rpm`, and
  `.flatpak`** — instead of a portable `.tar.gz` archive.

## ℹ️ Windows prerequisites
The native window needs two Microsoft runtimes on the target machine:
- **Microsoft Edge WebView2 Evergreen Runtime** (match the CPU architecture — a
  missing/wrong-arch runtime shows a blank white window; install the ARM64
  runtime on Windows-on-ARM devices).
- **.NET Framework 4.7.2 or newer.**

---

# v3.0.0 — Desktop Rewrite: React + pywebview, Test Injection & Single-File Projects

The biggest release yet: the entire desktop app has been **rewritten**. The PyQt6
UI is gone, replaced by a **React single-page app running in a native pywebview
window** over a **local FastAPI worker**. The Qt-free Python logic core and the
native Rust ELF parser carry straight over, so every validation, release, AI, and
code-map capability is intact — now behind a faster, more responsive interface
that physically cannot freeze (the heavy work runs in a separate process and
streams progress over Server-Sent Events).

## 🏗 New architecture (no behaviour you relied on was dropped)
- **React SPA + pywebview shell + FastAPI worker.** The UI talks to the worker
  over `127.0.0.1` with a per-session bearer token; the worker owns all project
  state and drives the existing `Application_Logic` layer directly.
- **Every heavy operation is a cancellable background job** with uniform progress,
  cancellation, and error reporting streamed over a single `/api/events` SSE.
- **View-only is enforced server-side** (`PRAGMA query_only=ON`) — read-only
  sessions physically cannot write, not just a greyed-out button.

## 💉 New: Source-level Test Injection
A new view to **splice test code into production C source without editing the
originals**. Hooks anchor to the *text* of the surrounding lines (not brittle line
numbers), so they re-find their spot when upstream source shifts. Import helper
`.c/.h` files alongside, then export build-ready code — *Modified files only* or a
full *Reconstructed* tree — leaving your originals untouched.

## 🎓 New: Interactive in-app tutorials
Every view now has a **click-through interactive walkthrough** on a simulated
screen (nothing in your real projects is touched). Open **Preferences → Tutorials**
for Workspace, Code Map, Change Log, Test Design, AI Generation, AI Chat, and Test
Injection.

## 💾 Single-file projects + per-block encryption
- A project is now **one portable `.arch` SQLite file** — no per-project folder
  required.
- Encryption moved from whole-file to **per-block (per-category) content
  encryption**: the `.arch` is a plaintext SQLite container and only sensitive
  content columns are encrypted, each under its own key. Open and save are fast
  (no decrypt-to-temp / re-encrypt-the-whole-file). **Legacy whole-file
  (`ARCHENC1`) projects auto-migrate on first open.**

## ⚙️ Packaging
- Packaged as a **PyInstaller onedir desktop bundle** (Windows/macOS/Linux) from
  `ArchitectureValidatorDesktop.spec`, which builds the React SPA and the Rust
  parser wheel first. CI gained the Node.js setup + frontend build steps.

> **Upgrade note:** opening a project from v2.x re-stamps it into the v3 storage
> format on first open. Keep a backup of important projects before upgrading.

---

# v2.1.1 — Release-Keyed Source, Code Map IDE Features & a Major Bug-Fix Pass

Source code now lives **inside the project database, keyed by release** — no more
scattered folder pickers. The Code Map gained IDE-grade navigation and works even
when the ELF carries no call tree, imports run under one continuous progress
window, and a long list of crashes and rough edges from 2.1.0 are fixed.

---

## ✨ Source code in the project, keyed by release
The four separate source-folder pickers (AI Test Generation, AI Chat current/
previous, Code Map, Change Log) are gone, replaced by one consistent flow:
- **Map / Import Source Code** in the Release Selection window is now the single
  place a folder is picked. The import runs on a background worker with per-file
  progress, and stores the files **gzip-compressed in the `.arch` database**,
  keyed by release (excluded from the integrity digest, so saves stay fast).
- **Everywhere else shows a release dropdown** instead of a folder picker — AI
  chat, test generation, the Code Map, and the Change Log all read the selected
  release's source straight from the database.
- **Mind maps and code maps are now stored per (model, release)**, so adding an
  intermediary release (e.g. a 1.5 after 2.0 exists) keeps every release's
  index intact and independent.
- **Unload Source** removes a release's source blobs while keeping its mind map
  and code map — regression checks don't force a re-import or regeneration.

## 🗺 Code Map: IDE navigation + works without a call tree
- **Hover tooltips** in the source viewer for functions (signature, return type,
  location), globals (type), and `#define` macros (their values — now persisted
  into the code map).
- **Ctrl-click (Cmd-click on macOS) on a function name jumps to it** — the graph
  re-centers and its source loads; holding the modifier shows a link-style
  underline and pointing-hand cursor.
- **ELF without a call tree?** The map now probes whether the binary actually
  carries call information (stripped/ET_REL binaries often don't) and falls back
  to the **source-derived call graph** automatically instead of running a futile
  disassembly pass.
- **Crash fixed:** the Code Map build no longer shares the UI thread's database
  connection — the worker opens its own connection and commits the finished map
  durably, with the main thread safely gated during the build.

## 🚦 Port-state propagation is now user-confirmed
When a model leaves **In Work**, a new confirmation dialog lists the unique ports
still marked In Work (with selectable Port Name / Port State columns), all
pre-ticked with Select All/None — **you choose exactly which ports follow the
model's new state**; Cancel changes nothing. No more silent cascades.

## 📦 Imports: one continuous window, cleaner results
- **ELF import → Code Map generation now runs under a single loading window**
  with step-by-step narration (journal-mode test, parser backend, Parsing /
  Decoding / Writing phases) — the visible freeze between the two phases is gone.
- **Rhapsody import cleanup:** unmapped Mapped-Function/Parameter column families
  are dropped automatically, and the untouched default `Architecture_1`
  placeholder is removed once real models are imported.

## ⚡ Performance
- **The native Rust ELF parser now releases the Python GIL** during parsing and
  hashing — the UI keeps painting while large binaries parse. This was the
  single biggest cause of "(not responding)" on EDR-protected machines.
- **Model switching is much faster:** switching persists only the active-model
  id instead of rewriting the whole registry, and skips flushing clean tables.

## 🤖 AI quality-of-life
- **AI Change Log crash fixed** ("Type Dict cannot be instantiated") and the
  model dropdown now sends the real model id to the provider.
- **AI chat renders markdown** with distinct bubbles for You / tool calls / AI /
  system messages.
- **Mind-map status per model:** the model dropdown marks ✓/○ for mind-map
  existence, the Generate/Regenerate button flips accordingly, and a status line
  shows "no mind map / ready / regenerate recommended".

## 🛠 Dialog & correctness fixes
- **Model delete works again** — the styled confirmation dialog's result was
  never recognized, so Delete silently no-op'd; same fix applied to the release
  locate/create prompts. The stray extra "OK" button is gone, the manager
  dialogs got the consistent dark theme, and the sidebar refreshes after the
  manager closes regardless of how it was dismissed.

**Tests:** 471 logic-layer tests passing.

---

# v2.0.0 — AI, Code Mapping & Configuration Management

A major release. Architecture Validator Pro grows from an ELF↔architecture matcher
into a full embedded-software validation workbench: AI-assisted test-case
generation, an agentic source-aware chat, a visual code map, release/baseline
configuration management with change history, and a bundled native Rust ELF
parser — plus a large round of correctness, integrity, and UX fixes.

> **Upgrade note (one-time):** the tamper-evidence integrity digest changed in
> this release (it is now computed far faster). The **first** time you open a
> project created with an older version you will be asked once for the project
> master password to re-stamp it — this is expected and only happens once.

---

## ✨ New: AI Test Case Generation (Tab 3)
Generate detailed, HiL-debugger-style **low-level test designs** from your
high-level test cases and the actual C source.
- Providers: **GitHub Copilot** (OAuth device-flow sign-in), **Anthropic**,
  **OpenAI**, and **Gemini** (direct API keys). Keys are stored Fernet-encrypted
  in a per-user credential store, never in the project.
- Parses your `*_Test_Case_Design.md` HLT files, lets you pick which test cases to
  generate, edit the prompt/rules, streams progress, and writes results back into
  the high-level design.
- Dynamic per-account model discovery; non-streaming, per-test-case progress.

## ✨ New: Advanced AI Chat (Tab 4)
An **agentic, source-grounded chat** about your firmware.
- Builds a compact **mind map** index of your C source (signatures, call/data-flow
  relationships, requirement traces) — parsed instead of raw C to stay token-cheap.
- Read-only **agent tools** (`read_file`, `search_code`, `get_mind_map`,
  `get_requirements`, `get_diff`, `get_function`, `get_call_graph`) let the model
  pull exactly what it needs, sandboxed to the source root with a path-jail.
- **Import requirements** (CSV/XLSX), generate/regenerate the mind map per model,
  and compute **file-by-file source diffs** between a current and previous release.

## ✨ New: Code Map (Tab 5)
A visual **call-graph + source explorer**. Joins the ELF/DWARF facts (addresses,
sizes, parameters, structs, globals) to the C source by function name, with a
depth-bounded graph (caller/callee), a node cap for hub functions, a matched-globals
panel, and a syntax-highlighted source view. Includes a token-free **Index &
Rebuild Code Map** action.

## ✨ New: Change Log (Tab 6)
Review what changed between releases: a **git-style side-by-side diff** (file
browser + old/new with synchronized scrolling and add/delete highlighting) plus an
optional AI-generated change-log summary. **Compute Release Diffs** runs the
file-by-file comparison on demand.

## ✨ New: native Rust ELF parser
A bundled **PyO3 Rust extension** (`rust_elf_parser`, built via maturin) parses
ELF symbols/DWARF with parallel traversal and `mmap`, with a transparent
**pyelftools fallback** when the native module isn't present. Drop-in: the
in-memory `ELFParser` contract and all six consumers are unchanged.

## ✨ Releases, baselines & change history (configuration management)
- **Linear auto-baselining**: creating a new release freezes the previous one as a
  baseline and clones its rows/results/history.
- **Password-gated unfreeze**: frozen baselines are read-only and **write-protected
  at the database layer**; unlocking requires the project master password. Freeze/
  unfreeze events are recorded in history (visible on both the baseline and the
  main project).
- **Release-scoped, tamper-evident history**: every change is logged with user,
  timestamp and release; the change log is obfuscated at rest and protected by an
  append-only HMAC hash-chain.
- Per-project folder on creation (the `.arch`, caches, and generated files now live
  in one folder).

---

## 🛠 Fixes & hardening in this release
- **Crash fixed:** New Project → Load ELF no longer crashes (dialog lifecycle
  guard); a successful load now goes straight to the table.
- **Verified mapping integrity:** the **(Match)** columns now live-search the real
  symbol pool as you type — so you can map the actual function behind a port even
  when its name differs — and any entry that isn't a real symbol is flagged instead
  of being shown as a confirmed match.
- **Baseline immutability** enforced at the DB layer (not just the UI).
- **Faster, non-blocking saves:** the integrity digest no longer sorts megabytes of
  row JSON on every Ctrl+S.
- **Network-drive safety:** SQLite journal mode auto-switches to `DELETE` on
  network/UNC drives (where WAL can corrupt), WAL locally — with a silent
  filesystem check on macOS/Linux.
- **No lost edits on release switch:** pending edits are flushed before switching.
- **Correct change-log author** (no longer recorded as `root` on some macOS setups).
- Native macOS file dialogs restored; styled dialogs render correctly; empty
  columns no longer appear for schema-less projects.
- Release-selection dropdown/context fixes for JSON/ELF imports and baselining.

## ⚙️ Packaging
- Windows `.zip`, macOS `.app` `.zip`, Linux `.deb` / `.rpm` / Flatpak.
- Release/build CI now builds the Rust extension on all three platforms, and the
  release job is fixed to work from both tag pushes and manual dispatch.

**Tests:** 394 logic-layer tests passing.
