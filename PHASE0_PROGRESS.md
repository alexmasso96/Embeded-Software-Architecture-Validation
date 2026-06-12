# Phase 0 Progress — De-Qt the Logic Layer — ✅ COMPLETE (2026-06-12)

Tracking document for Phase 0 of [pywebview_react_migration_plan.md](pywebview_react_migration_plan.md).
Update this file whenever a file conversion lands, so any session can pick up where the last left off.

**Goal:** every file in `src/Application_Logic/` importable without PyQt6, full test suite green after every single file, PyQt app still working.

> **Phase 0 is DONE.** All 30 `Application_Logic` modules import with PyQt6 hard-blocked;
> 479 tests pass; the PyQt app still runs (verified via the ApplicationWindow-based tests).
> Next: **Phase 1 — FastAPI worker** (plan §3).

> **Direction decision (Alex, 2026-06-12):** PyQt compatibility is no longer a maintenance
> goal. v3 is a full drop-in replacement developed on a local git instance; v1 remains the
> production app until v3 is finished and merged as one PR. The end state is a React UI —
> ALL remaining PyQt interface code (the whole `src/UI` package + `src/main.py`) gets ripped
> out at cutover. Consequence for the former "table access layer" open question: the Qt
> table code was moved to `src/UI` wholesale as legacy-to-delete; the lasting data model is
> what the DB already holds (`data_cache` rows + `active_config` column tuples with
> logic_key strings), which Phase 1 routers serve directly.

**Check current state:** `grep -rl "PyQt6" src/Application_Logic/` — Phase 0 is done when this returns nothing.

**Test command:** `/Users/alex/Git_Projects/Embeded-Software-Architecture-Validation/.venv/bin/python -m pytest Tests/ -q`
(v3 checkout has no own venv — uses the sibling checkout's venv.)
**Baseline before Phase 0:** 472 passed (2026-06-12).

## Infrastructure

| Item | Status | Notes |
|------|--------|-------|
| `src/Application_Logic/events.py` (`Emitter`) | ✅ DONE | `on`/`off`/`emit` + `on_any` catch-all hook for the future `qt_bridge` |
| `Tests/test_events.py` | ✅ DONE | unit tests for the emitter |
| `src/Application_Logic/qt_compat.py` | ✅ DONE | `gui_active(widget)` — answers "is the Qt GUI up?" via `sys.modules`, never imports Qt; deleted in Phase 4 |
| `Application_Logic/__init__.py` lazy re-exports | ✅ DONE | PEP 562 `__getattr__`: importing the package (or any de-Qt'd submodule) no longer pulls PyQt6; `main.py`'s `App_Logic.X` names still resolve |
| `src/UI/qt_bridge.py` (thread-safe relay onto GUI thread) | ❌ TODO | not needed yet — QThread conversions so far route results through Qt-side `TaskWorker` signals; the `_LogRelay` in `UI/loading_window.py` is the per-case template |
| `src/UI/list_models.py` (Qt list models moved out of logic) | ✅ DONE | `ArchitectureListModel`, `ReleaseListModel` |
| `src/UI/controller_feedback.py` (`ControllerFeedbackMixin`) | ✅ DONE | Qt implementation of the logic-side callbacks: `notify_info/warning/error`, `ask_yes_no_cancel`, `ask_text`, `ask_choice`, `ask_open_file`, `busy(text)` (non-modal LoadingDialog + log fn), `set_table_no_edit` — mixed into `ArchitectureTabController` |

## File status — 21 Qt importers at start

Status meanings: ✅ DONE (no PyQt6 import, tests green) · 🔶 IN PROGRESS · ❌ TODO.
"Strategy" says what the conversion looks like; files marked *split* keep their logic class and move Qt classes to `src/UI/`.

### Quick wins (incidental Qt)

| File | Status | Strategy |
|------|--------|----------|
| `interfaces.py` | ✅ DONE | TYPE_CHECKING-only Qt names → `Any` aliases |
| `Logging_Handler.py` | ✅ DONE | `Signaller(QObject)` → plain class wrapping an `Emitter`; `QtLoggingHandler` renamed `EmitterLoggingHandler` (no alias — sole importer updated); `Logic_Loading_Window` subscribes via a queued-signal `_LogRelay(QObject)` for thread-safe GUI delivery |
| `Logic_Security.py` | ✅ DONE | split: `SecurityManager` stays; both password dialogs → `src/UI/Dialog_Master_Password.py`; importers (`main.py`, `Dialog_Release_Selection.py`) + test patch paths updated |
| `Logic_Project_Saving.py` | ✅ DONE | only a `QtWidgets.QWidget` isinstance guard — replaced with `qt_compat.gui_active(main_window)` |
| `Logic_Architecture_Models.py` | ✅ DONE | split: `ArchitectureListModel` → `src/UI/list_models.py`; `ArchitectureManager`/`ArchitectureModel` stay |
| `Logic_Release_Manager.py` | ✅ DONE | split: `ReleaseListModel` → `src/UI/list_models.py`; `ReleaseManager` stays |

### Tier 2-3 — mixins of ArchitectureTabController & heavy ops

These are mixed into the (still-Qt) table controller. De-Qt = replace direct `QMessageBox`/`QInputDialog`/`LoadingDialog` calls with controller-provided callbacks (`self.notify`, `self.confirm`, `self.ask_text`, `self.run_with_progress`) implemented on the Qt side, and stop touching widgets directly where possible.

| File | Status | Strategy |
|------|--------|----------|
| `Logic_Architecture_Baseline.py` | ✅ DONE | QMessageBox/QInputDialog/LoadingDialog → `notify_*`/`ask_*`/`busy` callbacks; `setEditTriggers` → `set_table_no_edit()`; widget attrs (`table.setVisible`, `btn_exit_baseline`) stay duck-typed |
| `Logic_Architecture_IO.py` | ✅ DONE | (see tier 5 — moved to `src/UI/architecture_io.py`) |
| `Logic_Architecture_Import.py` | ✅ DONE* | QFileDialog/QMessageBox → callbacks; LoadingDialog+processEvents → `busy`; import dialogs imported lazily (state machine still drives them — moves behind the API in Phase 1). *Transitively still pulls Qt via `Logic_Column_Types` until that converts |
| `Logic_Change_Log_Tab.py` | ✅ DONE | split: diff engine + `run_release_diff` + `build_changelog_prompt` + `generate_ai_changelog` stay (pure); `AIChangeLogWorker(QThread)` deleted (UI uses generic `TaskWorker`); controller → `src/UI/tab_change_log.py` |
| `Logic_Loading_Window.py` | ✅ DONE | moved wholesale → `src/UI/loading_window.py` (it IS a dialog); all 12 import sites + test patch targets updated |
| `Logic_New_Project.py` | ✅ DONE | split: `ElfImportTask` (import sequencing) stays, Qt-free; `NewProjectController(QMainWindow)` → `src/UI/new_project_window.py` |

### Tier 4 — AI stack (QThread workers → functions)

| File | Status | Strategy |
|------|--------|----------|
| `Logic_AI_Generation.py` | ✅ DONE | split: `run_generation_job` (progress/case-done/stop callbacks) stays pure; controller + thin `_GenWorker(QThread)` wrapper → `src/UI/tab_ai_generation.py` |
| `Logic_AI_Chat.py` | ✅ DONE | split: `run_mindmap_job`, `run_chat_job`, `md_to_html` stay pure; controller + thin `_MindMapWorker`/`_ChatWorker` wrappers → `src/UI/tab_ai_chat.py` |
| `Logic_AI_ProviderPanel.py` | ✅ DONE | pure widget glue — moved wholesale → `src/UI/provider_panel.py` (model discovery already lives in `Logic_AI_Providers`); `_ModelDiscoverThread` went with it (UI concern) |
| `Logic_Code_Map_Tab.py` | ✅ DONE | split: `build_code_map_job` (own DB connection, progress_cb), `compute_graph_levels` (BFS + truncation), `build_callers_map`, `describe_symbol`, `extract_function_block_by_line` stay pure; controller + thin `_CodeMapWorker` wrapper → `src/UI/tab_code_map.py` |

### Tier 5 — mostly UI glue (largest splits, do last)

| File | Status | Strategy |
|------|--------|----------|
| `Logic_Architecture_Table.py` | ✅ DONE | moved wholesale → `src/UI/architecture_table.py` (legacy-to-delete per direction decision); the Qt-free mixins (IO from UI, Baseline/Import from logic) stay mixed in |
| `Logic_Architecture_IO.py` | ✅ DONE | moved wholesale → `src/UI/architecture_io.py` (reads/writes the live QTableWidget — pure legacy; persistence already exists as `data_cache`/`save_model_rows`) |
| `Logic_Column_Types.py` | ✅ DONE | moved wholesale → `src/UI/column_types.py`; the lasting column identity is the `active_config` logic_key strings, not these Qt classes |
| `Logic_Column_Customizer.py` | ✅ DONE* | moved wholesale → `src/UI/column_customizer.py`. *TODO noted in its header: extract rename/delete validation rules into logic in Phase 1 so the API can enforce them server-side |
| `Logic_TestCase_Design.py` | ✅ DONE | split: pure condition tokenizer / suggestion engine (`tokenize_partial_condition`, `tokenize_condition`, `get_condition_suggestions_and_prefix`) stays; widgets + `HelpDialog` + controller → `src/UI/test_case_design.py` |
| `Logic_User_Interaction.py` | ✅ DONE | moved wholesale → `src/UI/user_interaction.py` (QTableWidgetItem metadata helpers — the React UI tracks per-cell metadata in row data instead of Qt item roles) |

### Already Qt-free at start (no work needed)

`Logic_AI_Context`, `Logic_AI_Credentials`, `Logic_AI_Providers`, `Logic_AI_Tools`,
`Logic_Code_Index`, `Logic_Code_Map`, `Logic_Database`, `Logic_File_Locking`,
`Logic_History`, `Logic_Release_Source_Picker`, `Logic_Rhapsody_Import`,
`Logic_Source_Store`, `Logic_Symbol_Matcher`

## Open questions / decisions

- **Table access layer — RESOLVED by the direction decision (2026-06-12):** no logic-owned row store is built for the Qt table. The Qt table code moved to `src/UI` as legacy-to-delete; the data model Phase 1 serves is the existing DB shape: `data_cache` rows (`{col_name: {text, widget_text, widget_style, user_changed, is_purple, last_func}}`), `save_model_rows`/`model_metadata` persistence, and `active_config` `(name, logic_key, visible, width)` column tuples. Per-cell metadata (manual override, conflict purple) moves from Qt item roles into those row dicts when the React table is built.
- **`exec()`-style dialogs in logic flows:** pattern adopted = logic raises/returns and the caller (Qt today, HTTP later) decides; for mixins, controller-provided `notify/confirm/ask_text` callbacks.
- **Exit-criterion grep nuance:** `qt_compat.py` contains the literal string `"PyQt6.QtWidgets"` (a `sys.modules` key, never an import). Use `grep -rl "from PyQt6\|import PyQt6" src/Application_Logic/` as the import-level check; `qt_compat.py` is the one sanctioned exception to the plan's plain-string grep and dies in Phase 4.
- `Tests/debug_loading.py` is a manual debug script, not collected by pytest — updated imports anyway.

## Session log

- **2026-06-12 (a)** — Baseline 472 passed. Created `events.py` + tests, `qt_compat.py`, this tracker; made `Application_Logic/__init__.py` re-exports lazy (PEP 562). Converted 6 of 21 Qt importers: `interfaces.py`, `Logging_Handler.py` (+ loading-window subscriber update), `Logic_Project_Saving.py`, `Logic_Security.py` (dialogs → `src/UI/Dialog_Master_Password.py`), `Logic_Architecture_Models.py` + `Logic_Release_Manager.py` (list models → `src/UI/list_models.py`). Suite: 479 passed (472 + 7 new emitter tests).
- **2026-06-12 (b)** — Created `src/UI/controller_feedback.py` (`ControllerFeedbackMixin`: notify/ask/busy callbacks) and mixed it into `ArchitectureTabController`. Converted/moved 7 more: `Logic_Architecture_Baseline.py` (callbacks), `Logic_Architecture_Import.py` (callbacks + lazy dialogs), `Logic_Change_Log_Tab.py` (pure diff/AI logic stays, controller → `src/UI/tab_change_log.py`, `AIChangeLogWorker(QThread)` deleted in favour of generic `TaskWorker`), `Logic_AI_ProviderPanel.py` → `src/UI/provider_panel.py`, `Logic_Loading_Window.py` → `src/UI/loading_window.py`, `Logic_New_Project.py` (split: `ElfImportTask` stays / window → `src/UI/new_project_window.py`), `Logic_Column_Customizer.py` → `src/UI/column_customizer.py`. Updated test patch targets (`test_excel_import`, `test_elf_reload_and_import_match`, `test_baseline_mixin`, `test_new_project`, `test_audit_fixes`, `test_project_isolation`, `test_change_log_viewer`, `test_column_customizer`). **8 Qt importers remain:** `Logic_AI_Chat`, `Logic_AI_Generation`, `Logic_Architecture_IO`, `Logic_Architecture_Table`, `Logic_Code_Map_Tab`, `Logic_Column_Types`, `Logic_TestCase_Design`, `Logic_User_Interaction`. Suite: 479 passed. Qt-blocked import verified for all converted files (note: `Logic_Architecture_Import` still pulls Qt transitively via `Logic_Column_Types`).
  **Next step:** `Logic_Code_Map_Tab.py` + `Logic_AI_Generation.py` + `Logic_AI_Chat.py` via the `tab_change_log.py` split pattern (pure functions stay, controller → `src/UI/`, QThreads → `TaskWorker`). The last four (`Architecture_Table`, `Architecture_IO`, `Column_Types`, `User_Interaction`) hang together on the table-access-layer decision in Open questions.
- **2026-06-12 (c)** — Converted the three tab controllers via the split pattern: `Logic_Code_Map_Tab.py` (pure: `build_code_map_job`/`compute_graph_levels`/`build_callers_map`/`describe_symbol`/`extract_function_block_by_line`; controller → `src/UI/tab_code_map.py`), `Logic_AI_Generation.py` (pure: `run_generation_job`; controller → `src/UI/tab_ai_generation.py`), `Logic_AI_Chat.py` (pure: `run_mindmap_job`/`run_chat_job`/`md_to_html`; controller → `src/UI/tab_ai_chat.py`). QThread subclasses became thin wrappers in the UI files that relay the pure jobs' callbacks as queued signals. Test imports updated: `test_code_map_tab`, `test_code_map_ide`, `test_ai_generation_smoke`, `test_change_log_viewer`. Suite: 479 passed; Qt-blocked import verified for all three.
  **5 Qt importers remain — ALL on the table-access-layer decision:** `Logic_Architecture_IO`, `Logic_Architecture_Table`, `Logic_Column_Types`, `Logic_TestCase_Design`, `Logic_User_Interaction`. (`Logic_TestCase_Design` is partly separable: its template engine is pure and could split first; the rest reads the live table.) Decide the row-store design (Open questions) before starting these.
- **2026-06-12 (d) — PHASE 0 COMPLETE.** Alex resolved the open question: PyQt compatibility is no longer maintained (v3 = drop-in replacement; PyQt UI gets ripped out at cutover; target = React UI). Final 5 files handled accordingly: `Logic_Architecture_Table` → `UI/architecture_table.py`, `Logic_Architecture_IO` → `UI/architecture_io.py`, `Logic_Column_Types` → `UI/column_types.py`, `Logic_User_Interaction` → `UI/user_interaction.py` (wholesale moves, legacy-to-delete); `Logic_TestCase_Design` split (pure tokenizer/suggestion engine stays, widgets + controller → `UI/test_case_design.py`). `Application_Logic/__init__.py` back to plain imports (no Qt left to defer). `Logic_Architecture_Import`'s column-class imports made lazy (module imports Qt-free; the classes only load when the Qt controller runs the import flow). Importers updated in `main.py`, `interfaces.py`, `UI/Dialog_Release_Selection.py`, `UI/tab_ai_chat.py`, and 14 test files.
  **Verified:** all 30 `Application_Logic` modules import with PyQt6 hard-blocked; `grep -rl "from PyQt6\|import PyQt6" src/Application_Logic/` → empty; suite 479 passed. **→ Phase 1 (FastAPI worker) is next.**
