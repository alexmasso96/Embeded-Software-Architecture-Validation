# 🏛️ Architecture Validator Pro

A cross-platform desktop tool for validating embedded software architecture against the compiled binary it ships in.

Point it at an `.elf` file and an architecture export, and it parses the binary's debug info, fuzzy-matches your architecture ports to the real symbols in the firmware, and gives you an editable table to review, track, and sign off on everything. From there you can detect changes between software releases, keep a reviewable history, and generate low-level test case designs straight from your architecture data.

Built with Python and PyQt6.

> 📷 _Screenshot coming soon._

---

## Why it exists

Embedded teams maintain an architecture (ports, interfaces, operations) that's supposed to reflect what's actually compiled into the ECU. Keeping those two in sync is normally a slow, manual, error-prone job — diffing symbol names by hand, re-checking everything on every software release, and writing low-level test cases by review.

Architecture Validator Pro automates the tedious parts so you can focus on the decisions: *is this match correct, and has anything changed since the last release?*

---

## 📖 Documentation

For a full, screenshot-by-screenshot walkthrough of every feature, see the **[User Guide](docs/guide/README.md)**:

- [Getting Started](docs/guide/01-getting-started.md)
- [The Validation Workspace](docs/guide/02-validation-workspace.md)
- [Importing Architecture](docs/guide/03-importing-architecture.md)
- [Releases & Baselines](docs/guide/04-releases-and-baselines.md)
- [Test Case Design](docs/guide/05-test-case-design.md)
- [Collaboration & Safety](docs/guide/06-collaboration-and-safety.md)
- [AI Test Generation](docs/guide/07-ai-test-generation.md)
- [Advanced AI Chat](docs/guide/08-advanced-ai-chat.md)
- [Code Map](docs/guide/09-code-map.md)
- [Change Log](docs/guide/10-change-log.md)

---

## Features

### 🔍 ELF / DWARF binary parsing (native Rust + Python fallback)
Reads compiled `.elf` files and pulls out the symbols, functions, structures, and global variables from the DWARF debug info. A bundled **native Rust parser** (`rust_elf_parser`, a PyO3 extension built with maturin) does this with parallel traversal and `mmap`; if the native module isn't present it falls back transparently to `pyelftools`. Includes disassembly-based sub-call analysis (via Capstone) and caches parsed data so large binaries only get the slow treatment once.

### 🤖 AI test-case generation, agentic chat & mind maps
Generate **low-level, HiL-debugger-style test designs** from your high-level test cases and the real C source, across **GitHub Copilot, Anthropic, OpenAI, and Gemini** (keys stored encrypted, per-user, never in the project). An **Advanced AI Chat** indexes your source into a compact **mind map** and answers questions agentically with read-only, sandboxed tools (`read_file`, `search_code`, `get_call_graph`, …) — grounded in the actual code. Import requirements (CSV/XLSX) and compute file-by-file source diffs between releases.

> 📷 _Screenshot coming soon._

### 🗺️ Code Map
A visual **call-graph + source explorer** that joins the ELF/DWARF facts (addresses, sizes, params, structs, globals) to the C source by function name — depth-bounded caller/callee graph, matched-globals panel, and a syntax-highlighted source view. Rebuildable offline (no AI tokens).

> 📷 _Screenshot coming soon._

### 📜 Change Log
A **git-style side-by-side diff** between releases (file browser, old/new with synchronized scrolling and add/delete highlighting), plus an optional AI-generated change-log summary.

> 📷 _Screenshot coming soon._

### 📥 Flexible architecture import
Bring your architecture in from **Excel or CSV**. Rhapsody path-based exports are detected automatically and routed through a dedicated import flow, and the classic sheet-per-model spreadsheet format is supported too.

### 🧩 Fuzzy symbol matching
Maps each architecture port to the closest real symbol in the binary using fuzzy string matching with a **configurable confidence threshold** — so you stay in control of how strict the matching is.

### 📊 Editable, customizable table
All your data lives in one editable table of ports × columns. A drag-and-drop column customizer lets you add, remove, reorder, and rename columns. Built-in column types cover port/function/variable search, matched symbols, init/cyclic execution info, review status, port state, and per-release validation results.

### 🔁 Release management, baselining & change detection
Manage multiple **software releases** in a single project, each carrying its own ELF data. Creating a release **auto-baselines** the previous one; frozen baselines are read-only and **write-protected at the database layer**, and unfreezing requires the project master password. Compare against a baseline to surface changes — differences are colour-coded so you can **approve or reject** them release over release, and every freeze/unfreeze is recorded in history.

### 🗂️ Multiple architecture models
Organise a project into several architecture models with full lifecycle support: create, duplicate, reorder, soft-delete, and restore.

### 📝 Test Case Design
Author low-level test case templates and generate them across your architecture:

- **Live preview** that updates as you type, row by row, so you always see the real output.
- An easy-to-learn **scripting language built on Markdown** — write standard Markdown, drop in `[Column]` tokens that resolve to your table data, and use inline `#if` conditionals to include or exclude content per row.
- Smart **autocomplete** for column tokens, operators, and values, plus an in-app help/reference dialog.
- **Bulk or individual exports** — generate for the current model or for every model at once.
- Operation grouping options (one test case per port, or one per operation).

![Test Case Design with live preview](/Media/images/screenshot_testcase_design.png "Test Case Design — template editor and live preview")

### 🕒 History & audit trail
A built-in history view tracks changes over the life of the project — each entry records the user, timestamp and release. The change log is **release-scoped**, obfuscated at rest, and protected by an **append-only HMAC hash-chain** so edits/deletions/reordering are detectable.

### 🔒 Collaboration-safe editing
Projects use file locking with an **Exclusive Edit / View-Only** model, so a teammate opening a project that's already being edited sees who holds the lock instead of clobbering each other's work. A password-protected **Test Mode** and configurable **auto-save** (immediate up to 15-minute intervals) round out day-to-day safety.

### 💾 Single-file projects
A project is one portable `.arch` file (a SQLite database under the hood), keeping ELF data, releases, baselines, and history together in one place.

---

## Tech stack

| Area | Library |
| :--- | :--- |
| Language | Python 🐍 |
| GUI | PyQt6 |
| ELF / DWARF parsing | native **Rust** (`rust_elf_parser`, PyO3 via `maturin`) + `pyelftools` fallback |
| Disassembly | `capstone` |
| C++ demangling | `cpp_demangle` |
| Fuzzy matching | `rapidfuzz` |
| Spreadsheet import | `pandas`, `openpyxl` |
| AI providers | Copilot / Anthropic / OpenAI / Gemini over `requests` |
| Project storage | SQLite |
| Security | `bcrypt` (master password), `cryptography` (encrypted AI credentials, history protection) |
| Packaging | `PyInstaller` (Windows/macOS/Linux), Flatpak |

---

## Getting started

```bash
# 1. Install dependencies (a virtual environment is recommended)
pip install -r requirements.txt

# 2. Run it
python src/main.py
```

### Building a distributable

- **Windows:** run `build_windows.bat`, or build directly from `ArchitectureValidatorPro.spec` with PyInstaller.
- **Linux:** a Flatpak build is available via `flatpak-manifest.yml`.

---

## License

Released under the MIT License. See [LICENSE](LICENSE) for details.
