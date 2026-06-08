# Architecture Validator Pro — Architecture Documentation

> A developer-facing map of the codebase. For an end-user walkthrough of the features, see the [User Guide](guide/README.md).

## Overview

Architecture Validator Pro is a **PyQt6** desktop application for validating embedded software architectures against ELF binary files. It parses ELF/DWARF debug info to extract symbols, functions, structures, and global variables, then uses fuzzy matching to map architecture ports to the real software symbols in the firmware.

As of **v2.0** it is a six-tab workbench: *Architecture Test*, *Test Case Design*, *AI Test Generation* (Tab 3), *Advanced AI Chat* (Tab 4), *Code Map* (Tab 5), and *Change Log* (Tab 6). ELF parsing is backed by a **native Rust extension** (`rust_elf_parser`) with a `pyelftools` fallback; the AI tabs add source mind-maps, agentic source-grounded chat, and AI test-case generation across Copilot/Anthropic/OpenAI/Gemini; the Code Map joins ELF facts to C source as a visual call graph; and the Change Log diffs releases.

A project is persisted as a **single SQLite file** (`MyProject.arch`, inside a per-project folder). All architecture data, software releases, ELF symbol data, baselines, test-case templates, AI mind-maps/diffs, and change history live in that one database.

## Data Flow

```
ELF Binary File
    │
    ▼
ELFParser (core/elf_parser.py)
    │ Extracts: symbols, functions, structures, global_vars
    │ flush_to_db() bulk-inserts into the project DB, then frees RAM
    ▼
ProjectDatabase (Logic_Database.py)         ◄── single .arch SQLite file
    │ Stores ELF data keyed by elf_hash so releases can share an import
    ▼
SymbolMatcher (Logic_Symbol_Matcher.py)
    │ Loads only symbol/function name strings from the DB (cheap)
    │ Provides: fuzzy matching via rapidfuzz
    ▼
ArchitectureTabController (Logic_Architecture_Table.py + mixins)
    │ Orchestrates: table setup, column logic, sidebar, model/release switching
    │ Uses: active_columns[] — one strategy object per visible table column
    ▼
QTableWidget (UI/MainWindow.py → Architecture_Table)
    │ Renders: rows (ports) × columns (search, match, init, cyclic, review, …)
    ▼
ProjectSaver (Logic_Project_Saving.py)
    │ Persists table/release/baseline data back into the .arch DB
    ▼
.arch SQLite Database (on disk)
```

## Module Responsibilities

### Core

#### `native/parser_rust/` — Native Rust ELF parser (`rust_elf_parser`)
A PyO3 Rust extension (built with **maturin**) that parses ELF symbols + DWARF with parallel traversal and `mmap`. Exposes `parse_elf(path)` (JSON) and `compute_md5(path)`. Bundled into the app as a hidden import; CI builds it on all three platforms.

#### `core/elf_parser.py` — ELF Binary Parser (~1310 lines)
Parses ELF files. The native `rust_elf_parser` is tried first (`parser_backend == "rust_elf_parser"`); `_try_native_extract()` maps its JSON onto the in-memory contract and falls back transparently to **`pyelftools`** on any error. Extracts the symbol table and DWARF debug info (function parameters, structures, global variables), and provides disassembly via **Capstone** for sub-call analysis. The active backend is surfaced in `get_statistics()` (`parser_backend`). Two persistence modes back the SQLite design:
- `flush_to_db(db)` — bulk-inserts parsed data into the project DB on first save, then clears the in-RAM lists and runs `gc.collect()` to keep memory flat.
- `load_from_db(db, elf_hash)` — DB-backed mode that serves lookups straight from the database without rehydrating the full object lists.
- `export_elf_cache()` / `import_elf_cache_to_db()` — portable JSON cache for fast re-import of a previously parsed binary.

Key classes/dataclasses: `Symbol`, `Function`, `ELFParser`.

### Persistence

#### `Application_Logic/Logic_Database.py` — Project Database (~810 lines)
The heart of persistence. `ProjectDatabase` wraps a SQLite connection and owns the full schema (see [Project File Structure](#project-file-structure-arch-sqlite-database)). Provides typed CRUD for project meta, column layout, models and their rows, releases and their rows, ELF data tables, baselines, test-case design, UI state, and history. All other modules go through this class — there is no JSON-on-disk project format.

#### `Application_Logic/Logic_Project_Saving.py` — Save / Load Orchestration (~400 lines)
`ProjectSaver` coordinates a full save (flush table → DB, settings, master-password hash, test-case design, ELF flush + cache export) and load (open DB, restore layout/models/releases, load active model into the table, restore test-case design). Also computes the project integrity hash and manages the `.dirty` temp-state marker.

#### `Application_Logic/Logic_File_Locking.py` — Cross-Process Lock (~265 lines)
`FileLockManager` implements the View-Only / Exclusive-Edit model. The lock is a sidecar file (`<project>.arch.lock`) carrying the owner and a heartbeat timestamp; stale locks (older than the threshold) are reclaimable. Used to show *who* holds a project and to gate editing.

### Architecture Table (the controller and its mixins)

#### `Application_Logic/Logic_Architecture_Table.py` — Main Controller (~1600 lines)
`ArchitectureTabController` is the central orchestrator for the validation workflow. It is composed from three mixins:

```python
class ArchitectureTabController(ArchitectureIOMixin, ArchitectureBaselineMixin, ArchitectureImportMixin):
```

It manages the `QTableWidget`, the per-column strategy objects (`active_columns`), the model sidebar/list, the `available_logics` registry, and coordinates model/release switching, column rebuilds (`_rebuild_column_objects`), and row-widget creation (`_initialize_row_widgets`). `populate_from_parser()` ingests a freshly parsed ELF; `load_active_model_to_table()` renders the active model.

#### `Application_Logic/Logic_Architecture_IO.py` — I/O Mixin (~265 lines)
Serialisation/deserialisation for the controller: `get_project_data()` snapshots the table + config + settings; `_load_row_data()` rebuilds rows (including combo-box widgets) on load; `flush_current_data_to_model()` writes the active table into the DB.

#### `Application_Logic/Logic_Architecture_Baseline.py` — Baseline Mixin (~255 lines)
Creating, loading, and exiting immutable baseline snapshots. Baselines are stored as DB rows (no file copying), so a snapshot is a cheap, query-able record.

#### `Application_Logic/Logic_Architecture_Import.py` — Import Mixin (~490 lines)
Excel/CSV import. Auto-detects Rhapsody path-based exports and routes them to the dedicated flow; otherwise handles the legacy sheet-per-model spreadsheet layout. Includes word-similarity heuristics for column detection.

### Column system

#### `Application_Logic/Logic_Column_Types.py` — Column Strategy Pattern (~1025 lines)
Implements the **Strategy Pattern** for table columns. Base class `TableColumn` plus 10 concrete subclasses, each defining its own `on_change()` behaviour, widget creation, and colouring. (See [Column Type System](#column-type-system).)

#### `Application_Logic/Logic_Column_Customizer.py` — Column Configuration Dialog (~455 lines)
Drag-and-drop dialog to add, remove, reorder, rename, and show/hide columns. Enforces constraints (TC. ID first, locked columns for reviewed data) and tri-state visibility for Init/Cyclic columns.

#### `Application_Logic/Logic_User_Interaction.py` — Cell State Tracking (~130 lines)
Per-cell metadata via Qt's `UserRole` system: manual-override flags, conflict state, and function associations. Static utility class.

### Models, releases, matching

#### `Application_Logic/Logic_Architecture_Models.py` — Architecture Model CRUD (~370 lines)
Manages multiple architecture models per project (create, duplicate, soft-delete, restore, reorder) against the DB. Includes `ArchitectureListModel` (the Qt model behind the sidebar `QListView`).

#### `Application_Logic/Logic_Release_Manager.py` — SW Release Management (~435 lines)
`ReleaseManager` owns software releases and baselines. ELF data is shared by `elf_hash`, and only the active release is held in memory (lazy loading). Supports baseline snapshots and release comparison.

#### `Application_Logic/Logic_Symbol_Matcher.py` — Fuzzy Matching (~105 lines)
Wraps **rapidfuzz** for fuzzy symbol matching. Loads only name strings from the DB (cheap, ~tens of MB rather than full objects) and exposes `find_best_match()`, `find_top_matches()`, and `get_matches_for_list()` with a configurable threshold.

### Test case design, history, security

#### `Application_Logic/Logic_TestCase_Design.py` — Test Case Designer (~1790 lines)
`TestCaseDesignController` drives the Test Case Design tab: the Markdown template editor with `[Column]` token + `#if` conditional autocomplete, the live preview, operation grouping (Grouped/Independent), and the bulk/individual `.md` generation. Includes the template tokenizer/evaluator and the in-app help dialog.

#### `Application_Logic/Logic_History.py` — Change Log
`HistoryManager` reads/writes the release-scoped, ASPICE-style change history from the DB (each entry carries user + timestamp + `release_id`). Descriptions are obfuscated at rest and protected by an append-only HMAC hash-chain (`db.verify_history_chain()`).

### AI, Code Map & Change Log subsystems (v2.0)

#### `Application_Logic/Logic_AI_Credentials.py` — Encrypted credential store
Per-user, Fernet-encrypted `credentials.aikeys` (OS-appropriate config dir). Holds API keys and the Copilot OAuth token; the project file never stores keys.

#### `Application_Logic/Logic_AI_Providers.py` — Provider adapters + agentic loop
Adapters for Copilot / Anthropic / OpenAI / Gemini behind one interface (`generate`, `generate_with_tools`), a `_post_and_json` helper, a per-provider tool-calling **capability matrix** (native JSON tools for direct keys; `[READ: …]` text-fallback for Copilot), `MODEL_CONTEXT_WINDOWS`, and circuit breakers (turns / calls / cumulative bytes).

#### `Application_Logic/Logic_AI_Context.py` — Context, mind map, diffs
Pure (no-Qt) builders: `build_mind_map`/`mind_map_to_text` (version-dispatched v1/v2 renderers), `hash_source_tree`/`diff_source_folders`/`compute_diff_hash`, `mindmap_is_stale`, `parse_requirements_file`, and the separate prompt/rules meta keys.

#### `Application_Logic/Logic_Code_Index.py` — C source indexer
Ported `deep_code_indexer` (stdlib-only): `build_index(path) -> CodeIndex` with `functions`/`globals`/`call_graph`/`file_functions` and `find_functions_by_keywords`/`extract_keywords`.

#### `Application_Logic/Logic_AI_Tools.py` — Sandboxed read-only tool set
`ToolExecutor` exposing `read_file`/`list_files`/`search_code`/`get_mind_map`/`get_requirements`/`get_diff`/`get_function`/`get_call_graph`, all confined by a realpath + `os.sep` **path-jail** to the source root.

#### `Application_Logic/Logic_Code_Map.py` — ELF↔C joiner
`build_code_map(parser, code_index)` joins DWARF facts to the C call graph **by function name** (with C++ demangling) into a `CodeMap` consumed by the mind map and the Code Map tab.

#### Tab controllers
- `Logic_AI_Generation.py` — Tab 3 (AI Test Generation) controller; threaded generate, write-back, model-change context reset.
- `Logic_AI_Chat.py` — Tab 4 (Advanced AI Chat) controller; mind-map/diff generation, requirements import, agentic chat.
- `Logic_Code_Map_Tab.py` (+ `UI/widgets_code_map.py`) — Tab 5 (Code Map) viewer.
- `Logic_Change_Log_Tab.py` (+ `UI/widgets_change_log.py`) — Tab 6 (Change Log) diff viewer.
- `Logic_AI_ProviderPanel.py` — `ProviderPanelMixin` shared by the AI tabs (provider/model picker, status pill), parameterised by per-tab meta keys.

#### AI dialogs (`UI/`)
`Dialog_AI_Configure.py` (provider sign-in / API keys) and `Dialog_AI_Help.py` (provider help & troubleshooting).

#### `Application_Logic/Logic_Security.py` — Master Password (~130 lines)
`SecurityManager` (bcrypt hashing/verification) plus the master-password setup/prompt dialogs. Gates **Test Mode**.

#### `Application_Logic/interfaces.py` — Type Contracts (~80 lines)
`Protocol` classes (structural typing) documenting the controller surface for static type checkers and AI agents, without forcing inheritance.

#### `Application_Logic/Logging_Handler.py` — Qt Logging Bridge (~30 lines)
`QtLoggingHandler` + `Signaller` route Python logging into Qt signals so long-running tasks can stream log output to the UI thread safely.

### UI layer

| Module | Role |
|--------|------|
| `main.py` (~850 lines) | `ApplicationWindow` — wires menus, controllers (`arch_controller`, `test_case_controller`), edit modes, auto-save, Test Mode, theme, and entry point |
| `UI/MainWindow.py` | Generated main-window UI (`Ui_MainWindow`) — do not hand-edit |
| `UI/Dialog_Release_Selection.py` | Release management + `AllBaselinesDialog` |
| `UI/Dialog_Architecture_Manager.py` | Model create/rename/duplicate/soft-delete/restore |
| `UI/Dialog_Rhapsody_Import.py` / `Logic_Rhapsody_Import.py` | Rhapsody export preview, model selection, and parsing |
| `UI/Dialog_Architecture_Import.py` | Sheet-per-model Excel import dialog |
| `UI/Dialog_History.py` | Read-only ASPICE change-log viewer |
| `UI/Dialog_Startup_Launcher.py` | New / Open (View Only) / Open (Exclusive Edit) launcher |
| `UI/Dialog_Restore_Model.py` | Restore soft-deleted models |
| `UI/Dialog_Architecture_Edit.py` | Model rename/edit |
| `Logic_Loading_Window.py` / `UI/win_simple_loading.py` | Background-task modal with streamed log output |
| `UI/win_new_project_dialogue.py`, `win_help_new_project.py` | Generated new-project UIs |

## Column Type System

### Base Class: `TableColumn`
```python
class TableColumn:
    def __init__(self, name, column_type): ...
    def on_change(self, table, row, col, text, controller, lazy=False): ...
```

### Available Column Types

| Registry key | Class | Description | Auto-Added? |
|--------------|-------|-------------|-------------|
| `Port Search` | `PortSearchColumn` | Fuzzy-searches function names for port matches | No |
| `Function Search` | `FunctionSearchColumn` | Searches for functions by name | No |
| `Variable Search` | `VariableSearchColumn` | Searches for global variables by name | No |
| `Static Text` | `TableColumn` (base) | Read-only / free text, used for Match columns | Auto (with a search parent) |
| `InitColumn` | `InitColumn` | Init-time visibility of the matched function | Auto (with Port/Function search) |
| `CyclicColumn` | `CyclicColumn` | Cyclic-time exec count of the matched function | Auto (with Port/Function search) |
| `Review Status` | `ReviewColumn` | ComboBox: Not Reviewed / In Review / Reviewed | No |
| `PortStateColumn` | `PortStateColumn` | ComboBox: Released / In Work / Retired / Deleted | Auto (with Review) |
| `Last Result` | `LastResultColumn` | Latest validation result across releases | No |
| `ReleaseResultColumn` | `ReleaseResultColumn` | Per-release validation result column | Auto (via Release dialog) |
| `Link` | `LinkColumn` | Cross-reference between rows | No |

### Adding a New Column Type (Step-by-Step)

1. **Define the class** in `Logic_Column_Types.py`:
   - Inherit from `TableColumn`
   - Implement `on_change(self, table, row, col, text, controller, lazy=False)`
   - If it needs a widget (e.g. a `QComboBox`), create it in the controller's `_initialize_row_widgets()`

2. **Register it** in `Logic_Architecture_Table.py`:
   - Add to the `available_logics` dict in `__init__()`
   - Add the import at the top of the file
   - Map it in `_rebuild_column_objects()`

3. **Handle serialization** in `Logic_Architecture_IO.py`:
   - Ensure the column's data is included in `get_project_data()` and restored in `_load_row_data()`

## Key Design Patterns

### Strategy Pattern (Column Types)
Each column type encapsulates its own behaviour. The controller iterates `active_columns[]` and delegates to each column's `on_change()`. New behaviours can be added without touching the controller.

### Mixin Composition (Controller)
`ArchitectureTabController` is assembled from `ArchitectureIOMixin`, `ArchitectureBaselineMixin`, and `ArchitectureImportMixin`, keeping I/O, baseline, and import concerns in separate files while presenting one controller object.

### Observer Pattern (Signal → Controller → Column)
`QTableWidget.cellChanged` → `ArchitectureTabController.handle_table_cell_change()` → the affected column's `on_change()`. UI signals drive business logic through the controller.

### Registry Pattern
`available_logics` maps display names to column classes; the Column Customizer reads this registry to offer column types.

### DB-Backed Lazy Loading
ELF data is parsed once, flushed to SQLite keyed by `elf_hash`, and then served from the DB. Only the active release is materialised in memory, and the matcher loads just name strings — this is what keeps large multi-release projects within a flat memory budget.

### UserRole Data Storage
`QTableWidgetItem.setData(UserRole + N, value)` stores metadata directly on cells:
- `UserRole + 1`: user manual-override flag (bool)
- `UserRole + 2`: last function name (str)
- `UserRole + 3`: conflict/purple state (bool)

## Project File Structure (`.arch` SQLite database)

The project is **one SQLite file**. As of v2.0 it is created inside a **per-project
folder** (named after the project) so the database and its sidecars stay together:

```
MyProject/                      # per-project folder (v2.0)
  MyProject.arch                # the SQLite database (the whole project)
  MyProject.arch.lock           # exclusive-edit lock (owner + heartbeat), when held
  MyProject.arch.dirty          # unsaved-changes / temp-state marker
  MyProject.arch.elf_caches/    # exported ELF JSON caches for fast re-import
  Test Case Design/             # generated high-level test-case design .md files
```

The integrity HMAC is stored *inside* the database (`project_meta.integrity_hmac`),
not as a sidecar.

### Database schema (tables)

| Table | Holds |
|-------|-------|
| `project_meta` | Key/value settings, schema version, master-password hash |
| `column_layout` | Ordered column config (name, type, visibility, width) |
| `ui_state` | Active model/release and other UI state |
| `test_case_design` | Project title template, design template, grouping mode |
| `architecture_models` | Models (name, status, soft-delete flag, order) |
| `architecture_rows` | Per-model row data (JSON per row) |
| `model_metadata` | Per-model key/value metadata |
| `releases` | Software releases + baselines (elf_hash, parent, active flag) |
| `release_rows` | Per-release row data |
| `release_column_metadata` / `release_results` | Per-release column metadata and validation results |
| `elf_index` | One row per imported ELF (`elf_hash` → path, timestamp, `parser_backend`) |
| `elf_symbols`, `elf_functions`, `elf_structures`, `elf_global_vars` | Parsed ELF data, keyed by `elf_hash` (shared across releases) |
| `history` | Release-scoped change log (`timestamp, user, model, description, release_id, entry_hmac`); descriptions obfuscated + HMAC hash-chained |
| `ai_model_mindmaps` | Per-model compact mind map (+ `code_map_json`), source/diff hash, builder version |
| `ai_code_diffs` | Per-file unified diffs between a current and previous source folder |

`DB_SCHEMA_VERSION = 3`. New tables/columns are additive (`CREATE TABLE IF NOT EXISTS` / guarded `ALTER TABLE`), so existing projects upgrade transparently. The two AI cache tables and machine-specific path/requirements meta keys are excluded from the integrity digest; the journal mode is chosen per project location (WAL locally, DELETE on network/UNC drives).

## File Naming Conventions

| Pattern | Purpose | Examples |
|---------|---------|----------|
| `Logic_*.py` | Business-logic controllers/managers | `Logic_Architecture_Table.py`, `Logic_Database.py` |
| `Dialog_*.py` | Modal dialog windows (in `UI/`) | `Dialog_Release_Selection.py`, `Dialog_History.py` |
| `win_*.py` | Generated window UIs (from Qt Designer) | `win_new_project_dialogue.py`, `win_simple_loading.py` |
| `Logging_*.py` | Logging infrastructure | `Logging_Handler.py` |
