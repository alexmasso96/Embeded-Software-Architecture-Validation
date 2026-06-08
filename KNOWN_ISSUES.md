# Known Issues

Tracked issues that are **intentionally deferred** (not yet fixed in this repo), with enough
detail to be fixed later — several are earmarked for the enterprise-licensed Copilot on the work
machine (the only environment approved to parse real ECU source/binaries). See
[ASPICE_AUDIT_REPORT.md](ASPICE_AUDIT_REPORT.md) for the full audit.

---

## KI-01 — Native ELF parser corrupts DWARF on *relocatable* (`ET_REL`) objects
**Severity:** Low (no impact on supported targets) · **Owner:** enterprise Copilot (work machine)

`native/parser_rust/src/lib.rs` → `load_and_relocate_section` ignores the **in-place addend** of
ELF **REL** relocations (it applies `symbol_value + 0`). On a *relocatable object* this zeroes every
DWARF `DW_FORM_strp`/type offset → all struct/global names collapse to the DWARF producer string and
function parameters are dropped. `ELFParser._try_native_extract` (`src/core/elf_parser.py:~373`) only
falls back to pyelftools **on an exception**, never on corrupted-but-valid output, so the app
silently trusts the garbage.

**Why it is deferred / low impact:** it only triggers on relocatable objects (`ET_REL`). The
supported targets — **Aurix TriCore `.elf` and Renesas RH850 `.out`** — are *linked executables*
with no `.rel.debug_*` sections, so `load_and_relocate_section` is a pass-through and DWARF parses
correctly (confirmed: the linked `MB_CHLC_APP.elf` parses fine natively). It surfaced here only
because the audit fixture is a `.o` (no ELF linker on the audit host). **Parsing a real linked
TriCore/RH850 image is restricted to the work machine**, so the fix is to be done there by the
enterprise-licensed Copilot, not in this repo.

**Fix guidance:**
- In `load_and_relocate_section`, for REL relocations (implicit addend) read the existing 4/8 bytes
  at the offset and use `value = symbol_value + in_place_addend`; keep RELA (explicit addend) working.
  A correct, tested reference algorithm is `ForTesting/AspiceAudit/patch_debug_relocs.py`.
- Add an **output sanity check** in `_map_native_json` / `_try_native_extract`: if every struct name
  equals the DWARF producer string (or no function has params while symbols exist), discard the
  native result and fall back to pyelftools.
- **Validate against a real linked TriCore `.elf` and RH850 `.out`** (both backends) on the work
  machine — this is the real "supported?" gate.
- **NC-6 regression tests** ship with this fix: use `ForTesting/AspiceAudit/wlc_v1.elf`/`wlc_v2.elf`
  (or a captured JSON fixture) to assert correct structs/params/globals and backend agreement.

**Supporting additional (non-TriCore/RH850) ECUs later** — mostly validation, small code:
symbol/DWARF extraction via `object`+`gimli` is architecture-neutral; the hard-coded
little-endian (`lib.rs:~350 RunTimeEndian::Little`) is fine for TriCore/RH850 but a **big-endian**
target needs `elf_file.is_little_endian()` detection; the Capstone disassembly fallback supports
TriCore but **not** RH850/V850 (low impact — the call graph comes from the C indexer, not disasm).

## KI-02 — No parser-backend provenance / override (IMP-8)
**Severity:** Low · **Owner:** with KI-01 (enterprise Copilot)

There is no user-facing indication of which ELF parser backend produced the loaded data, and no
`ARCH_PARSER_BACKEND=python` (or `ARCH_PARSER_BINARY`) override to force the safe backend for
debugging. Add alongside the KI-01 fix: surface `parser_backend` in the UI/statistics and honour an
`ARCH_PARSER_BACKEND` env/setting in `ELFParser.extract_all`.

## KI-03 — `TC. ID` column is user-editable in edit mode (NC-2)
**Severity:** Medium (future) · **Owner:** deferred until DOORS Next Gen (DNG) import exists

`Logic_Architecture_Table` re-applies `ItemIsEditable` to display columns in edit mode
(`:501-506`), so the test-case identifier `TC. ID` is user-editable. **Test Case IDs are intended to
be populated from DOORS Next Gen exports**, and the DNG import is not built yet. Until then, leave as
is; when DNG import lands, make `TC. ID` tool-populated and read-only (drive editability from a
per-column capability rather than a blanket flag).

---

## UI-layer fixes — RESOLVED (verified live 2026-06-07)

### KI-04 — Architecture table loses columns for a model with no saved schema (Inc-04) — ✅ FIXED
`Logic_Architecture_Table._rebuild_column_objects` now falls back to `default_column_config()` when
the sanitized config is empty, so a schema-less model still renders the full column set. (A normally
created project already showed columns; the no-column state was tied to the BUG-02-corrupted project.)

### KI-05 — New-project ELF flow did not return to the table (Inc-03) — ✅ FIXED
`Logic_New_Project` now drops the blocking success popup and proceeds straight to the workspace via
`_safe_close()` (which also quits the modal `exec()` loop). Verified live: Load New ELF + release name
now lands directly on the architecture table ("Project created successfully").

### KI-06 — Match columns accepted arbitrary unvalidated free text (NC-1) — ✅ FIXED + feature
`_wire_live_match_search` (`Logic_Column_Types.py`) makes the `(Match)` combo **re-query the symbol
pool live as the user types** (so the real function behind a port can be found even when names differ,
e.g. `UART_LMM` → `UART_TX123_LMM`), each candidate carrying the real symbol (traceability kept). A
committed value that is not a real symbol is flagged dark red instead of shown as a valid match.
Verified live (typing `Current` → `WLC_ReadCurrent`; `NOTAREALSYMBOL` flagged red).

---

## Newly found

### KI-07 — `StyledMessageBox` rendered empty / unresponsive on macOS — ✅ FIXED
The unsaved-changes confirmation (and any `StyledMessageBox`) rendered as an empty thin sliver on
macOS. Root cause: the `setWindowFlags(... & ~Qt.Sheet)` hack left the dialog as a collapsed
window-modal sheet attached to the parent. Fix (`src/UI/StyledMessageBox.py`): make it
**application-modal** (`setWindowModality(ApplicationModal)` + `setWindowFlags(Qt.Dialog)`) and force
content sizing (`adjustSize()` + `setMinimumHeight(sizeHint)`). Verified live: the 3-button
Unsaved-Changes prompt now renders fully (text, `?` icon, Cancel/No/Yes).
