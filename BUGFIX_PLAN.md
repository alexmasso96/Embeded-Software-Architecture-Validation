# Bug-fix & Hardening Plan (post-v2.1.0)

Validated against the code on 2026-06-09. Implementation order agreed with the user:

```
3  →  2 + 2A + 2B  →  [discuss] 4  →  1  →  6  →  7  →  5  →  2E  →  2C  →  2D
```

> **WAL caveat (user concern):** do **not** assume a `-wal` file exists. On network/UNC
> drives the journal mode falls back to `DELETE` (no WAL). Any fix that needs
> "concurrent reader + writer" via a second connection is therefore unsafe — prefer
> serializing DB access to a single thread instead.

---

## Status

- [x] **#3 — Dialogs: fix delete + consistency** (done: `result_button` fix in 3 sites — model delete, release locate-Yes, release create-No; shared `DIALOG_STYLESHEET`; sidebar refresh regardless of close; 394 tests pass)
- [x] **#2 + 2A + 2B — Code Map crash + gating + call-tree pre-check** (done: worker uses its OWN
      connection via `ProjectDatabase.open(create_schema=False, apply_journal=False)`; commits the map
      itself → durable without a project Save; light gate via `_codemap_building` pausing auto-save;
      2B logs ELF-vs-source call tree. Verified end-to-end + 394 tests pass)
- [x] **#4 — AI change log** (done: `Message(...)` → plain dicts (fixes the "Type Dict cannot be
      instantiated" crash); `currentText()` → `currentData()` for the model id. Confirmed single-shot
      response already rendered via `setMarkdown` — no bubbles needed here. 394 tests pass)
- [x] **#1 — `ElfImportTask` orchestrator + responsive phase logging** (done: `ElfImportTask` in
      `Logic_New_Project` sequences + narrates each step; `_parse_logic`/`_open_db_task` delegate to it.
      Rust extraction branch now logs Parsing/Decoding/Writing phases (was silent → the white window);
      backend logged as "Using the native Rust parser". `Decoding…` precedes the json.loads GIL pause so
      it's explained. Residual: fully removing that pause needs the Rust ext to stream — noted future.
      394 tests pass.)
- [x] **#6 — AI chat markdown + message bubbles/separation** (done: self-contained `md_to_html` helper +
      table-based per-role bubbles in `Logic_AI_Chat._append` — You/→tool/AI/System/Error each styled;
      AI rendered as markdown. Verified render; 394 tests pass.)
- [x] **#7 — Model-switch slowness** (done: `set_active_model` now persists only the active-model id
      (one `set_ui_state` write) instead of rewriting the whole registry every switch; and
      `on_model_selection_changed` skips the full flush of the old model when nothing is dirty
      (`_dirty_rows`/`_full_flush_needed`). Table rebuild remains the inherent cost — widget-reuse is
      possible later if needed. 394 tests pass.)
- [x] **#5 — Mind-map completeness marker** (done: dropdown items marked `✓`/`○` per model via new
      `ProjectDatabase.get_model_ids_with_mindmap`; Generate↔Regenerate flips on mind-map *existence*;
      persistent per-model status line ("no mind map" / "ready" / "regenerate recommended"). 394 tests pass.)
### Remaining (next session) — suggested order: 1b → 8/8.1 → 2E → 2C → 2D
- [x] **#1b — single continuous loading window** through ELF import → Code Map generation (done: the initial DWARF/Capstone code-map build moved off the main thread into `ElfImportTask._build_initial_code_map`, so it runs under the SAME import loading window — eliminating the post-import main-thread `build_code_map` beachball. `populate_from_parser` now prefers `parser._initial_code_map` and only falls back to an inline build for non-import paths. 403 tests pass.)
- [x] **#8 — Rhapsody-import architecture cleanup** (done: `_import_rhapsody` now calls `_drop_unmapped_rhapsody_columns` — drops the Mapped Func / Mapped Parameter column families unless the import mapped onto them, and purges their orphaned cells — and `_delete_default_model_if_untouched` — soft-deletes the empty default `Architecture_1` only when real models were imported and it's the untouched placeholder, re-pointing the active model if needed. Idempotent. New `Tests/test_rhapsody_cleanup.py`.)
- [x] **#8.1 — model-state → port-state propagation** (done: `ArchitectureManager.propagate_status_to_ports` bumps each row's Port State from "In Work" to the new model state on an In Work → other transition only, leaving Released/Retired/Deleted ports untouched, and persists. Wired from `Dialog_Architecture_Manager.on_edit`, resolving the Port State column name(s) from the active schema. New `Tests/test_model_state_propagation.py`. NOTE: model statuses are In Work/Released/Retired — the plan's "Reviewed" wording maps to "leaving In Work".)
- [x] **#2E — release-keyed source code in the DB + unify the source/release pickers** (DONE, 3 phases, 426 tests pass — plan `~/.claude/plans/atomic-herding-waterfall.md`). **P1:** `release_source_files` gzip table + CRUD (excluded from integrity digest) + `Logic_Source_Store.py` providers + Release Selection "Map / Import Source Code" (worker-owned-connection import, per-file log) & "Unload Source". **P2:** `ai_release_maps(model_id,release_id)` table + migration + release-aware accessors (`release_id=None`→active); refactored `build_index`/`build_source_context`/`diff_source_folders`/`compute_diff_hash`/`load_source_code` to `SourceProvider` (diff stat-gate uses content_hash for DB source); workers pin `release_id`. **P3:** all 4 source folder pickers → release dropdowns (`selectable_releases()` + `populate_release_combo`); `ToolExecutor` provider mode; fixed latent Change Log legacy-table bug via `set_model_diff_hash`. Tests: `test_release_source_store/_ui`, `test_per_release_maps`, `test_source_provider_refactor`, `test_release_source_picker`.
- [x] **#2C — manual / source-based indexing fallback** (done: new `elf_has_call_tree(parser)` probe in
      `Logic_Code_Map` samples the largest functions and decides via disassembly — real edge ⇒ tree present,
      clean `[]` leaf ⇒ disasm works (tree recoverable), only all-status-strings/no-Capstone/stripped ⇒ no
      tree. `build_code_map` gains `prefer_source_calls` (auto-detects when None): when the ELF has no usable
      call tree it **skips the futile Capstone `extract_subcalls`** and uses the source-derived `ast_func.calls`
      as the primary edges. Shared `_strip_capstone_noise` helper (also drops "Function not found"). The Code
      Map worker now probes once, passes the flag (no re-probe), bases the 2B message on the real probe (not a
      bare `elf_functions` count), and warns when there's no tree AND no source. New `Tests/test_source_based_indexing.py`
      (13 tests). 439 pass.)
- [x] **#2D — IDE features (macro values, ctrl-click navigation)** (done: `build_code_map` now persists the
      `#define` map (`"defines"`); the Code Map source viewer (`code_viewer`) got mouse tracking + one viewport
      event filter (`AICodeMapController.eventFilter`) driving (1) rich hover tooltips for functions/globals/
      macros via the pure, unit-tested `describe_symbol`, (2) Ctrl/Cmd-click → `focus_function` (re-centers graph
      + loads source), (3) Ctrl/Cmd-hover link affordance (pointing-hand + underline via `setExtraSelections`).
      `ControlModifier` covers Cmd-on-macOS for free; filter is teardown-safe. New `Tests/test_code_map_ide.py`
      (15 logic-layer tests) + runtime-verified event seam. 457 pass (1 unrelated pre-existing flaky UI test).
      Known limitation: `WordUnderCursor` doesn't resolve C++ `Class::method` (fine for the C target).)
- [x] **#8.2 — port-state propagation is now user-confirmed** (done: new `PortPropagationDialog`
      (`UI/Dialog_Port_Propagation.py`) — Port Name / Port State column dropdowns (default to the first
      `PortSearchColumn`/`PortStateColumn`), a checkable de-duplicated list of the unique **In Work** ports,
      Select All/None, Confirm/Cancel. `Dialog_Architecture_Manager._propagate_state_to_ports` now opens it on
      an In Work→other transition (skips silently when no In Work ports), and on Confirm calls
      `propagate_status_to_ports(..., selected_ports=set(...), port_name_column=...)` — a new back-compatible
      filter so only the ticked ports are bumped; Cancel changes nothing. Shared `_cell_text` helper.
      `Tests/test_port_propagation_dialog.py` + new selected-ports cases in `test_model_state_propagation.py`.
      471 pass.)

---

## #3 — Dialogs (delete broken + consistency)  [doing first]
Root cause: `main.py:11` aliases `QMessageBox = StyledMessageBox`. `Dialog_Architecture_Manager.on_delete`
checks `msg.exec() == QMessageBox.StandardButton.Yes`, but `StyledMessageBox.exec()` (a `QDialog`)
returns `Accepted(1)`/`Rejected(0)`, never the button enum → Yes never matches → delete no-ops.
A stray "OK" button also appears (constructor adds default OK before `setStandardButtons`).
- Use `StyledMessageBox.question(self, title, text) == StandardButton.Yes` (returns `result_button`).
- Grep & fix any other `.exec() == ...StandardButton` misuse.
- Restyle `ArchitectureManagerDialog` / `Dialog_Architecture_Edit` / `Dialog_Restore_Model`
  (plain `QDialog`s) with the app dark theme for consistency.
- Refresh the main sidebar after the manager closes regardless of accept/reject.

## #2 + 2A + 2B — Code Map crash, gating, call-tree pre-check
Root cause: `_CodeMapWorker` uses the **shared** SQLite connection on a worker thread while the
main thread (imports / model move / timers) also writes → concurrent use of one connection → crash.
**WAL-independent fix — worker-owned connection + gated main thread (revised after user Q):**
`extract_subcalls` *does* read `self._db`, so the worker cannot reuse the main parser's connection.
Keep **all** DB work off the main thread (the grey-window concern):
- 2A — **gate the main thread** for the whole build: overlay up; disable table editing + imports +
  model switch; suspend the auto-save/heartbeat timers. This leaves the **main connection idle**.
- The **worker opens its own `ProjectDatabase(db_path)`** (+ a worker-side parser bound to it) and does
  everything off-thread: read DWARF rows, `build_index`, `build_code_map` (incl. Capstone), **write the
  code map + commit**, then close its connection.
- **Why this is WAL-independent:** two connections only contend if both are *active* at once. Because the
  main connection is idle (gated), the worker's connection takes the normal file lock and writes fine
  **even in `DELETE` mode** — we rely on the gate, not on a `-wal` file existing.
- Main thread after completion: quick `load_data()` reload of the saved map (single blob read).
- 2B: before indexing, detect whether the ELF actually carries a call tree (DWARF/subcalls present);
  log "No call tree in ELF — building call graph from source" and route to the source-derived graph.

## #4 — AI change log  *(pause here to discuss)*
- `Logic_AI_Providers.py:137` `Message = Dict[str,str]` is a type alias; `AIChangeLogWorker.run()`
  calls `Message(role=…, content=…)` → "Type Dict cannot be instantiated". Build plain dicts.
- Use `cmb_model.currentData()` (model id), not `currentText()`. Surface the provider's real error.

## #1 — ElfImportTask orchestrator + responsive logging
Embedded-style task that owns the New-Project sequence and logs **before/after each step**: WAL test
(+ fallback reason), backend selection (rust/python), and per-phase extraction progress. Rust path
currently emits nothing during parse → add "Parsing… / Decoding N symbols+functions… / Writing to DB…"
(the Rust call sets a status the task captures). Goal: the app never *looks* hung.

## #6 — AI chat markdown + bubbles
Render assistant turns via markdown; visually separate user message / agent-tool log / AI response.

## #7 — Model-switch slowness
On switch, persist only the active-model id (single `set_ui_state`), not the full `save_registry`;
block signals during table repopulate; reuse widgets where possible.

## #5 — Mind-map completeness marker
On load, check `get_model_mindmap` per model; mark dropdown items (✓ / none); flip
Generate↔Regenerate on existence + freshness, not just diff state.

## #1b — single continuous loading window (ELF import → Code Map)  [NEW]
After an ELF import, when Code Map generation starts it currently **closes** the import loading window
and **opens** the Code Map overlay → on M4 Pro there's a visible 3–4 s beachball in that gap.
**Plan:** keep ONE loading window/overlay alive across both phases — the import task hands the same
window to the code-map build (or the code-map build reuses it) and only closes it when *everything* is
done. No close/reopen, continuous log. Ties into #1 (`ElfImportTask`) + #2 (code-map worker).

## #2E — release-keyed source code in the DB + unify the source/release pickers  [DESIGN]
**Problem:** there are many separate source-folder pickers across the app (AI Test Gen "Source code path",
AI Chat Current/Previous source, Code Map "Link Local Source Folder", Change Log folder pickers) — confusing.
**Design (agreed with user):**
1. **One entry point — Release Selection window** gets a **"Map / Import Source Code"** button that links a
   source folder to the ELF/**release** (keyed by **release name/id**). This is the *only* place that keeps a
   real folder picker.
2. **Import on a background worker** with a loading window: "Importing source… / Indexing <file>" logging
   **each file** as it's indexed. Same gating pattern as #2A: loading dialog on the main thread, **main DB
   access locked** during indexing (use the worker-owned-connection approach from #2 so it's WAL-independent
   and never freezes).
3. **Store the full source files in the DB, keyed by release** (whole files, per user preference). Store
   **per-release mind maps** too (independent versions) so **intermediary releases** work (e.g. a 1.5 added
   after 2.0). Code maps already per-model — extend to be release-aware as needed.
4. **All other source pickers → release dropdowns** that list **software releases only**. Must **exclude pure
   baselines** — list releases (including ones that have been baselined) but not baseline snapshots
   (confirm `releases.is_baseline` semantics: pull where it represents a real release, filter baseline-only).
5. **AI uses the selected release's data** (source + mind map parsed from the DB, not the filesystem). The
   "current release" picker **pre-fills the latest release added**.
6. **Unload source** action: drop **only the source code** for a release, **keeping its mind map + code map**
   — so a regression check doesn't force regeneration.
**Feasibility / must-design-around (from earlier analysis):**
- Integrity HMAC (`compute_content_digest`) must **exclude** the source blobs, or every save/open hashes GBs.
- Store **compressed** (C source gzips ~5–10×); **lazy** per-file reads, never load all into RAM.
- Save-As copies the whole file (inherent); size mitigated by the **unload/drop** actions above.
- DB schema: a `release_source_files(release_id, rel_path, content_blob, …)` table + per-release mind-map
  rows; reuse `ai_model_mindmaps` pattern but key/scope by release where needed.

## #2C — manual / source-based indexing fallback
`build_index` already builds a static call graph + globals + #defines from source. When the ELF lacks
a call tree, use the source-derived graph as the primary edges.

## #2D — IDE features (macro hover + ctrl-click navigation)  [PLANNED]
Bring IDE-grade navigation/inspection to the Code Map **source viewer**
(`self.code_viewer`, a read-only `QPlainTextEdit` in `AICodeMapController`). All five
capabilities below hang off **one event filter** installed on the viewer's viewport,
backed by the in-memory `self.dataset` code map (no extra DB reads at hover time).

**1 — Persist macro definitions into the code map.**
`build_code_map()` (`Logic_Code_Map.py`) currently returns `functions` / `global_variables`
/ `structures`. Add `"defines": code_index.defines if code_index else {}` so the `#define`
name→value map (already produced by `build_index`'s `_extract_defines`) is serialized into
`code_map_json` in SQLite and is available on reload. **Back-compat:** older saved maps won't
have the key — every read site must use `self.dataset.get("defines", {})`.

**2 — Mouse tracking + event filter.**
In `_build_ui` (right after the `code_viewer` is created): `setMouseTracking(True)` on both the
widget and its `viewport()`, then `code_viewer.viewport().installEventFilter(self)` (the
controller is already a `QtCore.QObject`, so it can host `eventFilter`). The filter only acts when
`obj is self.code_viewer.viewport()` and handles three event types: `ToolTip`, `MouseMove`,
`MouseButtonPress`. Word resolution is shared:
`cur = code_viewer.cursorForPosition(pos); cur.select(QTextCursor.SelectionType.WordUnderCursor);
word = cur.selectedText()`.

**3 — Rich tooltips (`QEvent.Type.ToolTip`).**
Resolve the hovered word, then classify against `self.dataset` and show
`QToolTip.showText(event.globalPosition().toPoint(), html, self.code_viewer)`:
- **function** (`dataset["functions"][word]`): signature, return type, `file:line_start`.
- **global** (`dataset["global_variables"][word]`): name + type.
- **macro** (`dataset.get("defines", {})[word]`): `#define WORD value`.
- no match → `QToolTip.hideText()` and let the event pass.
The classify-and-format step is factored into a **pure** helper `describe_symbol(word) -> Optional[str]`
so it's unit-testable without Qt (per the logic-layer testing strategy).

**4 — Ctrl/Cmd-click navigation (`QEvent.Type.MouseButtonPress`).**
If `event.modifiers() & Qt.KeyboardModifier.ControlModifier` and the word is a known function,
call `self.focus_function(word)` (which already re-centers the graph **and** loads that function's
source) and return `True` to consume the click (so the caret doesn't just move). Non-functions /
no modifier → return `False` (normal behavior). **macOS note:** Qt maps **Cmd**→`ControlModifier`
by default, so checking `ControlModifier` gives Ctrl-on-Windows/Linux and Cmd-on-macOS for free.

**5 — Link affordance (`QEvent.Type.MouseMove`).**
While `ControlModifier` is held: if the word under the cursor is a known function, set the viewport
cursor to `Qt.CursorShape.PointingHandCursor` and underline that word via `setExtraSelections`
(a `QTextEdit.ExtraSelection` with an underlined `QTextCharFormat` over the word's range);
otherwise restore `Qt.CursorShape.IBeamCursor` and clear the extra selections. ExtraSelections are
independent of `CSyntaxHighlighter` (which paints via the document), so they won't fight. Clear the
underline/cursor on `Leave` too.

**Testability / scope notes:**
- Logic-layer tests (automated): `build_code_map` includes `defines`; `describe_symbol()` returns the
  right text for function/global/macro/unknown; `_is_known_function()` gating for nav/underline.
- The event-filter wiring itself is UI → verified manually (per `feedback_testing_strategy`).
- **Known limitation:** `WordUnderCursor` returns a single identifier, so **C++ qualified names**
  (`Class::method`) won't resolve from a hover (only the bare segment). Fine for the C embedded target;
  noted for a possible later enhancement (qualified-name reconstruction around `::`).

## #8 — Architecture handling on Rhapsody import  [NEW]
When new architecture models are created via **Rhapsody Import**:
- **Auto-delete the default `Architecture_1`** model (the empty placeholder) once real models are imported,
  so the user isn't left with a stray empty model.
- **Silently drop unmapped columns.** In the Excel/Rhapsody flow we map *operations → input port*, so the
  "mapped function" and "mapped parameter" columns are redundant after import — remove them automatically.
- Where: `Logic_Rhapsody_Import` / `Logic_Architecture_Import` (the import completion path) + the model
  manager (`soft_delete`/hard-remove of `Architecture_1`) + column layout (drop the unmapped columns).
- Care: only delete `Architecture_1` if it's the untouched default (no rows/edits), and only when the
  import actually produced models; keep it idempotent.

## #8.1 — Model-state → port-state propagation  [DONE]
When an architecture model's state changes **In Work → Reviewed**, also set the **port state** to match
the model state — **but only for ports whose port state is still "In Work"** (don't override Released/
Retired/etc.). Where: the model-status change handler (`Dialog_Architecture_Edit` / model manager
`save_registry` / wherever status is committed) → iterate the model's rows and bump the PortState column
value from "In Work" to the new state. Keep it scoped to that one transition + that one prior value.

**Implemented (2026-06-10):** `ArchitectureManager.propagate_status_to_ports(model, old, new, port_cols)`
bumps "In Work" port cells → the new model state on an **In Work → other** transition only; Released/
Retired/Deleted ports untouched; **other → In Work does nothing** (better tracking, per user). Wired from
`Dialog_Architecture_Manager.on_edit` (resolves Port State col name(s) from the active schema). Model
statuses are **In Work/Released/Retired** (no "Reviewed") — so the trigger is "leaving In Work".
Tests: `Tests/test_model_state_propagation.py`.

## #8.2 — Port-state propagation is now user-confirmed  [DONE]
Resolved the #8.1 "silent cascade" concern by putting the user in control instead of hard-coding rules.
**Implemented (2026-06-11):**
- New **`PortPropagationDialog`** (`UI/Dialog_Port_Propagation.py`), built from plain data
  (`columns`, `rows`, `new_status`) so it's decoupled + unit-testable:
  - **Column dropdowns** for Port Name / Port State, pre-filled to the first `PortSearchColumn` /
    `PortStateColumn` (fall back to index 0); changing either re-scans live.
  - **Checkable port list** — a grouped/de-duplicated scan of the rows for unique ports whose current
    Port State is **In Work** (all ticked by default). **Select All / None** buttons.
  - **Confirm Propagation / Cancel.**
- **Wiring** (`Dialog_Architecture_Manager._propagate_state_to_ports`): only the **In Work → other**
  transition opens the dialog; if no ports are In Work it returns silently; **Cancel = no changes**.
  On Confirm it calls `ArchitectureManager.propagate_status_to_ports(..., selected_ports=set(names),
  port_name_column=…, port_state_columns=(chosen,))`. Columns resolved from the live table schema
  (`active_config`), falling back to row-key inference when no controller is reachable.
- **Manager method** gained `selected_ports` / `port_name_column` (back-compatible: `selected_ports=None`
  keeps the original "all In Work ports" behaviour for #8.1's direct callers/tests). Shared `_cell_text`
  helper for cell→text. Single chokepoint preserved.
- Tests: `Tests/test_port_propagation_dialog.py` (dialog defaults/scan/checkboxes/re-scan + manager-dialog
  wiring confirm/cancel/non-transition/no-ports) and new selected-ports cases in
  `Tests/test_model_state_propagation.py`. **471 pass** (1 unrelated pre-existing flaky UI test).
- Open rules questions from #8.1 (In Work→Retired, re-open behaviour, per-port overrides) are now **moot**
  for the common case — the user decides per-transition. Revisit only if a non-interactive/bulk path needs it.

---

## Audit Findings (2026-06-11)

An audit of the implementation was conducted against the final test suite and codebase. The following findings were identified:

### 1. Test Pollution & Failure in `test_restore_dialog_no_selection_warns`
- **Component:** `Tests/test_architecture_manager_dialog.py`
- **Issue:** When running the entire test suite, the global monkey-patching of `QMessageBox` in `main.py` causes `PyQt6.QtWidgets.QMessageBox` to be replaced with `StyledMessageBox`. In this test, the mock target `patch("PyQt6.QtWidgets.QMessageBox.warning")` patches `StyledMessageBox.warning`, but the module `UI.Dialog_Restore_Model` has already imported the original `QMessageBox` class before `main.py` ran. This causes the mock to be called 0 times.
- **Recommendation:** Change the patch target to the module-local name: `patch("UI.Dialog_Restore_Model.QMessageBox.warning")`.

### 2. Broken Mock in `test_on_delete_soft_deletes_with_confirmation`
- **Component:** `Tests/test_architecture_manager_dialog.py`
- **Issue:** The test patches `QMessageBox.exec` to simulate clicking "Yes" on the delete confirmation dialog. However, during the refactoring for #3, `on_delete()` was updated to call `StyledMessageBox.warning(...)` directly instead of instantiating and calling `exec()` on a standard `QMessageBox` (to fix a bug where standard popups ignored styling). As a result, the mock for `QMessageBox.exec` is never invoked, the confirmation returns false/default, and the assertion fails (`assert False is True`).
- **Recommendation:** Update the test to patch the warning method on `StyledMessageBox` directly, matching the pattern used in `test_on_delete_cancelled_keeps_model`:
  ```python
  from UI.StyledMessageBox import StyledMessageBox
  with patch.object(StyledMessageBox, "warning", return_value=QMessageBox.StandardButton.Yes):
      dlg.on_delete()
  ```

### 3. Untracked Artifacts
- **Status:** Multiple new test and implementation files are untracked by Git, along with `BUGFIX_PLAN.md` itself.
- **Recommendation:** Stage and commit these files to maintain repository sanity and clean branches.
