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
