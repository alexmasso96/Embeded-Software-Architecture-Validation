# Architecture Validator Pro — Architecture Documentation

## Overview

Architecture Validator Pro is a PyQt6 desktop application for validating embedded software architectures against ELF binary files. It parses ELF/DWARF debug info to extract symbols, functions, and structures, then uses fuzzy matching to map architecture ports to actual software symbols.

## Data Flow

```
ELF Binary File
    │
    ▼
ELFParser (core/elf_parser.py)
    │ Extracts: symbols, functions, structures, global_vars
    ▼
SymbolMatcher (Logic_Symbol_Matcher.py)
    │ Builds: search_pool = function_names + variable_names
    │ Provides: fuzzy matching via fuzzywuzzy
    ▼
ArchitectureTabController (Logic_Architecture_Table.py)
    │ Orchestrates: table setup, column logic, sidebar, model switching
    │ Uses: active_columns[] — one per visible table column
    ▼
QTableWidget (UI/MainWindow.py → Architecture_Table)
    │ Renders: rows (ports) × columns (search, match, init, cyclic, review...)
    ▼
ProjectSaver (Logic_Project_Saving.py)
    │ Persists: layout.json + architecture model JSONs + release JSONs
    ▼
.arch Project Directory (on disk)
```

## Module Responsibilities

### `core/elf_parser.py` — ELF Binary Parser (770 lines)
Parses ELF files using `pyelftools`. Extracts symbol tables, DWARF debug info (function parameters, structures, global variables), and provides disassembly via Capstone for sub-call analysis. Supports JSON caching for fast reload. Key classes: `Symbol`, `Function`, `ELFParser`.

### `Application_Logic/Logic_Architecture_Table.py` — Main Controller (~1285 lines)
Central orchestrator for the architecture validation workflow. Manages the `QTableWidget`, column objects, sidebar/list model, and coordinates between all other modules. Key class: `ArchitectureTabController`.

### `Application_Logic/Logic_Column_Types.py` — Column Strategy Pattern (~815 lines)
Implements the **Strategy Pattern** for table columns. Each column type defines its own `on_change()` behavior, widget creation, and coloring logic. Base class `TableColumn` with 10 concrete implementations.

### `Application_Logic/Logic_User_Interaction.py` — Cell State Tracking (119 lines)
Manages per-cell metadata using Qt's `UserRole` data system. Tracks: manual overrides (bold text), conflict state (purple background), and function associations. Pure static utility class.

### `Application_Logic/Logic_Project_Saving.py` — Serialization (322 lines)
Handles project save/load with a directory-based format (`.arch` folders). Manages temp files for dirty state tracking, ELF data caching, and legacy migration from older file formats. Key class: `ProjectSaver`.

### `Application_Logic/Logic_Architecture_Models.py` — Architecture Model CRUD (392 lines)
Manages multiple architecture models within a project (create, duplicate, soft-delete, restore, reorder). Uses a registry JSON file for persistence. Includes `ArchitectureListModel` (Qt model for `QListView`).

### `Application_Logic/Logic_Release_Manager.py` — SW Release Management (479 lines)
Manages software releases and baselines. Each release stores ELF data independently. Supports lazy loading (only active release in memory), baseline snapshots, and release comparison. Key class: `ReleaseManager`.

### `Application_Logic/Logic_Symbol_Matcher.py` — Fuzzy Matching (58 lines)
Wraps `fuzzywuzzy` for fuzzy symbol matching. Provides `find_best_match()`, `find_top_matches()`, and `get_matches_for_list()` with configurable thresholds. Used by search columns to auto-populate match results.

### `Application_Logic/Logic_Column_Customizer.py` — Column Configuration Dialog (417 lines)
Drag-and-drop dialog for adding, removing, reordering, and renaming table columns. Enforces constraints (TC. ID first, dependents follow parents). Supports tri-state visibility for Init/Cyclic columns (Auto/Show/Hide).

### `Application_Logic/Logic_New_Project.py` — New Project Dialog (103 lines)
Handles ELF/JSON file selection with background parsing via `LoadingDialog`. Prompts for release name.

### `Application_Logic/Logic_Loading_Window.py` — Background Task Runner (122 lines)
Modal dialog with log output for long-running tasks. Uses `QThread` + signal-based log redirection. Key class: `LoadingDialog`.

### `UI/Dialog_Release_Selection.py` — Release Selection Dialog (352 lines)
Full release management dialog: select, load, rename, delete releases; create baselines; add new releases from ELF/JSON files.

## Column Type System

### Base Class: `TableColumn`
```python
class TableColumn:
    def __init__(self, name, column_type): ...
    def on_change(self, table, row, col, text, controller, lazy=False): ...
```

### Available Column Types

| Type | Class | Description | Auto-Added? |
|------|-------|-------------|-------------|
| Port Search | `PortSearchColumn` | Fuzzy-searches function names for port matches | No |
| Function Search | `FunctionSearchColumn` | Searches for functions by name | No |
| Variable Search | `VariableSearchColumn` | Searches for global variables by name | No |
| Static Text | — (base) | Read-only text, used for Match columns | Auto (with search parent) |
| Init Column | `InitColumn` | Shows init-time visibility of matched function | Auto (with Port/Function search) |
| Cyclic Column | `CyclicColumn` | Shows cyclic-time exec count of matched function | Auto (with Port/Function search) |
| Review Status | `ReviewColumn` | ComboBox: Not Reviewed / Reviewed / N/A | No |
| Port State | `PortStateColumn` | ComboBox: Active / Retired / Deleted / New | Auto (with Review) |
| Last Result | `LastResultColumn` | Shows latest validation result across releases | No |
| Release Result | `ReleaseResultColumn` | Per-release validation result column | Auto (via Release dialog) |

### Adding a New Column Type (Step-by-Step)

1. **Define the class** in `Logic_Column_Types.py`:
   - Inherit from `TableColumn`
   - Implement `on_change(self, table, row, col, text, controller, lazy=False)`
   - Optionally override widget creation in the controller's `_initialize_row_widgets()`

2. **Register it** in `Logic_Architecture_Table.py`:
   - Add to `available_logics` dict in `__init__()` 
   - Add import at top of file
   - Add to `_rebuild_column_objects()` mapping

3. **Handle serialization** in `get_project_data()` / `_load_row_data()`:
   - Ensure the column's data is included in the saved row dict
   - Ensure it's restored correctly on load

4. **Handle initialization** in `_initialize_row_widgets()`:
   - If the column uses a widget (QComboBox), create it here

## Key Design Patterns

### Strategy Pattern (Column Types)
Each column type encapsulates its own behavior. The controller iterates `active_columns[]` and delegates to each column's `on_change()` method. This allows adding new column behaviors without modifying the controller.

### Observer Pattern (Signal → Controller → Column)
`QTableWidget.cellChanged` → `ArchitectureTabController.handle_table_cell_change()` → iterates affected columns → calls `column.on_change()`. UI signals drive business logic through the controller.

### Registry Pattern
`available_logics` dict maps display names to column class constructors. The Column Customizer dialog reads this registry to show available types.

### UserRole Data Storage
`QTableWidgetItem.setData(UserRole + N, value)` stores metadata directly on cells:
- `UserRole + 1`: User manual override flag (bool)
- `UserRole + 2`: Last function name (str) 
- `UserRole + 3`: Purple/conflict state (bool)

## File Naming Conventions

| Pattern | Purpose | Examples |
|---------|---------|---------|
| `Logic_*.py` | Business logic controllers | `Logic_Architecture_Table.py`, `Logic_Column_Types.py` |
| `Dialog_*.py` | Modal dialog windows (in `UI/`) | `Dialog_Release_Selection.py`, `Dialog_Architecture_Edit.py` |
| `win_*.py` | Generated window UIs (from Qt Designer) | `win_new_project_dialogue.py`, `win_simple_loading.py` |
| `Logging_*.py` | Logging infrastructure | `Logging_Handler.py` |

## Project File Structure (`.arch` directory)

```
MyProject.arch/
├── layout.json                          # Column config + app settings
├── architecture_models_registry.json    # Model list + active index
├── releases_registry.json               # Release list + active release
├── Architecture_1.json                  # Model data (rows)
├── sw_releases/
│   ├── Release_1.json                   # Release data (rows + ELF cache)
│   └── Release_2.json
└── Baselines/
    └── Release_1_Baseline_20240101.json # Immutable snapshot
```
