---

## Implementation Audit — 2026-05-27

Audit of fixes implemented by Gemini 2.5 Pro and GPT-5.5 after the initial analysis above.

---

### Gemini fixes — status

#### ✅ Correctly implemented

| Fix | File | Notes |
|---|---|---|
| P0-2: `model.file_path` crash removed | `Logic_Architecture_Import.py` | Clean removal; import now calls `ProjectSaver.save_project()` on completion |
| `TestCaseDesignController.__test__ = False` | `Logic_TestCase_Design.py:611` | Silences pytest collection warning |
| P3-3: `ARCH_NO_STARTUP_DIALOG` env flag | `main.py:show_startup_launcher()` | Correctly gates the dialog |
| P1-6: Lock file write atomicity (partial) | `Logic_File_Locking.py` | Write-to-temp + `os.replace()` eliminates partial-write corruption |

#### ⚠️ Implemented but has bugs

**P0-1 — Discard semantics (`Logic_Architecture_Table.py`)**

`_mark_row_dirty()` and `discard_dirty_rows()` are correct in isolation. The critical bug is in `_flush_dirty_rows_to_db()` which calls `self._row_snapshots.clear()` (line 627) after every 750 ms autosave. After the first autosave fires, the snapshot dict is empty. Any subsequent `discard_dirty_rows()` call is a no-op — it silently does nothing, and the user believes they discarded changes that were not reverted.

Fix required: Remove `self._row_snapshots.clear()` from `_flush_dirty_rows_to_db()`. Snapshots must only be cleared on explicit user save (`save_project`) or model switch.

Secondary issue: `on_model_selection_changed()` clears `_dirty_rows` but not `_row_snapshots`. Add `self._row_snapshots.clear()` there too.

**P1-6 — Atomic lock still has TOCTOU (`Logic_File_Locking.py`)**

The write-then-rename approach eliminates partial writes but not the race condition. Two processes can both pass `check_lock()` simultaneously (both see "unlocked"), both write temp files, and the second `os.replace()` silently overwrites the first. Both processes believe they hold the lock. The original spec required `os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` which is atomic. That was not implemented.

Fix required:
```python
try:
    fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, 'w') as f:
        json.dump(lock_data, f, indent=4)
    return True, "Lock acquired successfully."
except FileExistsError:
    # File exists — re-check if it's stale; if so, unlink and retry once
    ...
```

#### ❌ Implemented incorrectly — plumbing disconnected

**P0-3 — Model metadata round-trip (`Logic_Database.py`, `Logic_Architecture_IO.py`, `Logic_Architecture_Models.py`)**

The `model_metadata` DB table was created and `get_model_metadata()` / `save_model_metadata()` methods exist. However the IO path is completely disconnected from them:

1. `flush_current_data_to_model()` in `Logic_Architecture_IO.py` still writes `column_metadata` to `ui_state` as `col_meta_{model_id}` (line 130). The `model_metadata` table is never written to through the normal save flow.

2. `release_results` and `linked_release_column` are stored in `data_cache` in memory but never persisted via `flush_current_data_to_model()`.

3. `_load_model_data()` in `Logic_Architecture_Models.py` sets `model.metadata = self._db.get_model_metadata(model.id)` — a **separate attribute** from `data_cache`. All consuming code (`load_active_model_to_table()`, `_restore_row_logic()`) reads from `data_cache`, not `model.metadata`. The loaded metadata is unreachable.

Net result: the `model_metadata` table is always empty after a normal project cycle. The bug is not fixed.

Fix required:
- `flush_current_data_to_model()` must call `db.save_model_metadata(model.id, {key: value})` for `column_metadata`, `release_results`, and `linked_release_column`, instead of (or in addition to) the `ui_state` path.
- `_load_model_data()` must merge the result of `db.get_model_metadata(model.id)` directly into `model.data_cache` (not `model.metadata`), so consuming code can find it.

#### Not verified

The following fixes were not checked due to context constraints; verify manually before shipping:
- FIX 2a/2b: `test_elf_parser.py` skip marker; Excel temp fixture in `test_excel_import.py`
- FIX 6: `LoadingDialog` stdout try/finally (`Logic_Loading_Window.py`)
- FIX 8: `SymbolMatcher.find_top_function_matches()` / `find_top_variable_matches()` new methods and wiring in `Logic_Column_Types.py`
- FIX 12/13: "project folder" wording fix; integrity hash read-failure behavior

---

### GPT-5.5 ELF RAM fix — status

**Files touched:** `elf_parser.py`, `Logic_Database.py`, `Dialog_Release_Selection.py`, `Logic_Architecture_Table.py`

#### What improved

- Post-import idle memory reduced from ~1 GB to ~500 MB. Root cause: `extract_all_streaming_to_db()` now clears `self.symbols`, `self.functions`, `self.structures`, `self.global_vars_dwarf` after DB flush via `self.close()`. Before the fix those lists were retained in RAM after import.
- `bulk_insert_symbols()` and `bulk_insert_functions()` now accept iterables and process in configurable batches of 2000 with `batch.clear()` rather than forcing `list()` upfront. This removes the transient in-memory copy of the entire symbol/function list during bulk insert.
- `Dialog_Release_Selection._parse_task()` now routes through `extract_all_streaming_to_db()` when a DB is open, instead of falling back to the in-memory `extract_all()` path.
- `export_elf_cache()` already streams from DB cursor rather than calling `fetchall()`.

#### What was NOT fixed — the 8–9 GB import spike

The peak memory during import is dominated by pyelftools' DWARF parsing, which was untouched:

1. **`extract_function_parameters()`** iterates all CUs and all DIEs. pyelftools caches parsed DWARF structures for the lifetime of the `elf_file` object. For a large embedded binary with hundreds of CUs and millions of DIEs, this is 3–5 GB with no way to free it incrementally.

2. **`extract_structures()`** builds a `typedefs` list accumulating all typedef DIEs before processing (line 460). `del typedefs` + `gc.collect()` only runs at end of method — after all typedefs are already in RAM.

3. **`import_elf_cache_to_db()`** still calls `json.load(f)` loading the entire JSON file into one Python dict before inserting. For a large project this can be 500 MB–1 GB just for the parse step.

4. **pyelftools internal caching**: `elf_file.get_dwarf_info()` caches the dwarfinfo object. Once called it retains all parsed structures for the object's lifetime. This is the single largest contributor to the 8–9 GB spike and cannot be addressed without either replacing pyelftools or running DWARF extraction in a subprocess.

#### Options to actually fix the 8–9 GB spike

| Approach | Complexity | Memory reduction |
|---|---|---|
| Process DWARF in a subprocess; write results to a temp SQLite; merge into main DB | High | Full — subprocess memory freed by OS on exit |
| Stream typedefs processing in `extract_structures()` without accumulation (requires 2-pass or lazy resolution) | Medium | Moderate — saves typedef list size |
| Stream JSON import in `import_elf_cache_to_db()` using incremental JSON parser (`ijson`) | Low | Moderate — removes JSON load spike |
| Replace pyelftools with LLVM/DWARF-native C extension | Very high | Full — C extension uses far less memory |

The subprocess approach is the most pragmatic for the existing architecture: spawn a worker process to parse the ELF and stream results via a queue or temp DB file, then the main process imports from the temp file. Memory from the parsing subprocess is fully reclaimed by the OS when it exits, regardless of what pyelftools does internally.

---

### ELF import memory — root-cause breakdown and next steps (2026-05-27)

#### What GPT's changes actually fixed (keep these)

GPT's changes are correct and should be retained. They solved the **post-import idle memory** problem:

- `extract_all_streaming_to_db()` now calls `self.close()` at the end, which clears `self.symbols`, `self.functions`, `self.structures`, and `self.global_vars_dwarf`. Before this fix those lists stayed in RAM after the import completed, holding ~500 MB of Python objects indefinitely. Now they are freed as soon as the DB has the data.
- `bulk_insert_symbols()` and `bulk_insert_functions()` now accept iterables and process in batches of 2000 with `batch.clear()` instead of calling `list()` on the full input. This eliminates a transient full-list copy during bulk insert.
- `Dialog_Release_Selection._parse_task()` now routes to `extract_all_streaming_to_db()` when a DB is open instead of falling back to the in-memory `extract_all()` path.

**Result: idle memory after import ~500 MB (was ~1 GB). Import spike unchanged at 8–9 GB.**

#### Why the spike cannot be fixed by batching symbols/functions

The symbol and function tables are NOT the dominant memory consumer during import. They are small relative to DWARF. The spike comes from three independent sources inside the DWARF extraction phase, none of which GPT touched:

**Source A — Three separate passes through all DWARF CUs:**

`extract_function_parameters()`, `extract_structures()`, and `extract_dwarf_variables()` each call `dwarfinfo.iter_CUs()` independently. pyelftools' `DWARFInfo` object maintains a `_CU_cache` dict. Every CU parsed during any pass is cached there for the object's lifetime. With three passes, the cache is populated three times over, and the peak memory of the DWARF phase is roughly 3× what one pass would require.

**Source B — `typedefs` list holds live DIE object references:**

In `extract_structures()`, the line `typedefs.append(DIE)` stores actual pyelftools DIE objects across all CUs. A DIE object holds a reference to its CU object, which holds a reference to its raw byte buffer. For a large embedded binary this chain keeps thousands of CUs alive in RAM simultaneously — even after their portion of the DWARF section has been iterated — because the `typedefs` list holds the last reference. `del typedefs` at the end of `extract_structures()` releases them, but they were all live at the same time for the duration of the typedef processing loop.

**Source C — pyelftools' internal `_CU_cache`:**

Even without the typedef reference chain, pyelftools caches each parsed CU in `DWARFInfo._CU_cache`. Once `iter_CUs()` completes, all CU objects are in this dict. This is pyelftools internal state and cannot be cleared from outside the library without reaching into private fields. For a large Aurix TriCore binary with hundreds of CUs, this cache alone can be 2–3 GB.

#### What can actually reduce the spike (without replacing pyelftools)

**Fix A — Single-pass DWARF extraction (high value, medium effort):**

Merge `extract_function_parameters()`, `extract_structures()`, and `extract_dwarf_variables()` into one function that iterates `iter_CUs()` exactly once and dispatches each DIE to the appropriate handler based on its tag. Write results to DB per CU rather than accumulating all in memory.

Expected reduction: DWARF-phase peak from 3× per-CU cost → 1× per-CU cost. For a binary where the current spike is 8 GB, this could bring it to ~3–4 GB. Effort: ~150 lines, contained to `elf_parser.py`.

```python
# Sketch of single-pass approach in extract_all_streaming_to_db():
func_map = {f.name: f for f in functions}  # built earlier from symbols
cu_functions = []
cu_structures = {}
cu_typedefs = []   # store plain dicts, NOT DIE objects
cu_variables = {}

for CU in dwarfinfo.iter_CUs():
    for DIE in CU.iter_DIEs():
        tag = DIE.tag
        if tag == 'DW_TAG_subprogram':
            # enrich matching function with parameters
            ...
        elif tag in ('DW_TAG_structure_type', 'DW_TAG_class_type', 'DW_TAG_union_type'):
            # extract struct fields
            ...
        elif tag == 'DW_TAG_typedef':
            # store ONLY scalars: name, type_offset, cu_offset — no DIE reference
            cu_typedefs.append({'name': ..., 'type_offset': ..., 'cu_offset': ...})
        elif tag == 'DW_TAG_variable':
            # extract global var
            ...
    # After each CU: write partial results to DB and clear per-CU buffers
    # (CU object can now be GC'd if pyelftools releases it)
```

**Fix B — Break the typedef DIE reference chain (low effort, targeted):**

In `extract_structures()`, replace `typedefs.append(DIE)` with storing only the scalar values needed for typedef resolution:

```python
# Instead of:
typedefs.append(DIE)

# Store only what is needed for the second pass:
td_name = DIE.attributes['DW_AT_name'].value.decode('utf-8', errors='replace')
type_attr = DIE.attributes.get('DW_AT_type')
if type_attr:
    cu_typedefs.append({
        'name': td_name,
        'type_offset': type_attr.value,
        'cu_offset': DIE.cu.cu_offset
    })
```

This breaks the DIE → CU → buffer reference chain. CU objects can be GC'd after iteration even if `_CU_cache` doesn't release them, because the `typedefs` list no longer holds strong references via DIE objects.

Expected reduction: 1–2 GB depending on how many typedef DIEs the binary has.

**Fix C — Subprocess isolation (complete fix, higher effort):**

Spawn `extract_all_streaming_to_db()` in a `multiprocessing.Process`. The subprocess writes to a temp SQLite file, then the main process imports from it and deletes the temp file. pyelftools' `_CU_cache` and all parsed DWARF objects live only in the subprocess; the OS reclaims all memory when the subprocess exits.

Expected reduction: Main process peak ~100–200 MB for the import operation, regardless of ELF size. Subprocess peak is unchanged (same pyelftools behavior) but is transient OS-level.

**Fix D — Streaming JSON import with `ijson` (independent, low effort):**

`import_elf_cache_to_db()` currently calls `json.load(f)` which loads the entire JSON cache file into a Python dict before inserting. For a large project this can add 500 MB–1 GB. Replace with `ijson` (incremental JSON parser) to stream symbols, functions, structures, and global_vars as iterables directly into `bulk_insert_*` without materializing the full dict.

#### Recommended implementation order

1. **Fix B** (typedef reference chain) — 10–20 lines, isolated to `extract_structures()`, immediate gain
2. **Fix A** (single-pass DWARF) — ~150 lines, contained to `elf_parser.py`, largest practical gain without subprocess
3. **Fix D** (`ijson` streaming import) — independent improvement for projects using JSON cache path
4. **Fix C** (subprocess) — implement if Fixes A+B still leave the spike above acceptable threshold for the largest expected ELF files

