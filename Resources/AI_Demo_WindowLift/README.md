# AI Demo — Window Lift Controller (WLC)

A small but representative **Window Lift Controller (WLC)** ECU module — the bundled
**demo project** for trying every feature of Architecture Validator Pro (ELF matching,
releases/baselines, AI test generation, mind-map chat, code map, change-log diffs)
without needing proprietary C code. It's also the regression fixture behind
`Tests/test_aspice_dataset.py`.

## Quick start
1. **New Project** → save it (anywhere) → set a master password.
2. **Load New ELF** → `wlc_v1.elf` → name the release `R1.0`.
3. *Architecture* tab: **Import Architecture Export** → `architecture_ports.csv`
   (the `Operations` column maps to the real WLC functions, so matches resolve).
4. *AI Test Generation* / *Advanced AI Chat*: set the **source** to this folder's
   `src_v1/` to generate low-level tests, a mind map, and a code map.
5. *Change Log*: **Compute Release Diffs** with Current = `src_v2/`, Previous =
   `src_v1/` to see the added/modified/deleted changes.

## Contents

| Path | Purpose |
|------|---------|
| `src_v1/` | Version 1 C source (multi-file): `wlc_main`, `wlc_motor`, `wlc_sensor`, `wlc_types.h`. Functions, static (file-local) functions, globals, structs, a call graph with a hub (`WLC_UpdateStateMachine`), and `REQ-WLC-xxx` traces in comments. |
| `src_v2/` | Version 2: **added** file/func (`wlc_safety.c` / `WLC_AutoReverse`), **modified** func (`WLC_DetectPinch` now calibration-driven with hysteresis), **deleted** func (`WLC_LegacyInit`), **modified** struct (`WLC_State_t.reverse_count`). Drives diffs / baselines / change-log. |
| `wlc_v1.elf`, `wlc_v2.elf` | ARM ELF (with DWARF) built from each version. Symbols, sizes, params, structs, globals all populate. Function names match the architecture-import operations. |
| `architecture_ports.csv` / `.xlsx` | Rhapsody-style architecture import; the `Operations` column holds real WLC function names so symbol matching succeeds. |
| `requirements.csv` / `.xlsx` | Requirements (`REQ-WLC-001 …`) for the Advanced AI Chat "Import Requirements" flow and traceability. |
| `Test Case Design/WindowLift_Test_Case_Design.md` | High-level test cases (TC.001…TC.005) in the app's HLT format, for the AI Test Generation tab. |
| `build_elf.sh` | Rebuilds the ELFs from source. |
| `patch_debug_relocs.py` | Build-time fixup (see note). |

## Call graph (v1)

```
WLC_Cyclic -> WLC_UpdateStateMachine -> { WLC_ReadHallPosition -> WLC_Scale,
                                          WLC_DetectPinch -> WLC_ReadCurrent,
                                          WLC_MotorStop,
                                          WLC_MotorSetDuty -> WLC_ClampDuty }
WLC_Init   -> WLC_MotorInit
```

## Rebuilding the ELF

```
cd ForTesting/AspiceAudit
PYTHON=../../.venv/bin/python ./build_elf.sh
```

### Note on `patch_debug_relocs.py` (and a real parser bug it works around)

No standalone ARM linker (lld / arm-none-eabi-ld) is available on the build host, so the
sources are amalgamated and emitted as a **relocatable** ARM ELF (`ET_REL`). In a
relocatable object, DWARF name/type references in `.debug_info` are stored as
`0 + REL relocation` (ARM uses REL — the addend is held *in place*).

The bundled native parser (`rust_elf_parser`) mishandles REL/implicit-addend relocations
on debug sections: it applies `symbol_value + 0`, zeroing every offset, which collapses all
DWARF names to the producer string and drops parameters. (Linked executables have no debug
relocations, so the native parser is correct there — the defect is specific to `ET_REL`.)
`patch_debug_relocs.py` pre-applies the relocations correctly and neutralizes them so **both**
the native and pyelftools backends read identical, correct DWARF. This is a fixture build
step only — it is **not** part of the shipped app. See the ASPICE report for the underlying
parser bug (NC/bug item).
