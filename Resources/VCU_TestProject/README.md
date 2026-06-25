# VCU Test Project — large multi-release embedded C corpus

A synthetic but realistic automotive **Vehicle Control Unit (VCU)** firmware built
specifically to exercise and **stress-test Architecture Validator Pro** end-to-end
without any proprietary embedded code. It is deliberately bigger and more complex
than the bundled `AI_Demo_WindowLift` demo: **8 software components, 5 releases,**
**~923 functions and 738 architecture ports in the largest release.**

## Layout
```
VCU_TestProject/
  generate_project.py     # regenerates everything (this is the source of truth)
  build_all.sh            # compiles one ARM ELF (with DWARF) per release
  patch_debug_relocs.py   # build-time DWARF reloc fixup (ET_REL, see demo)
  CHANGELOG.md            # the inter-release deltas, narrated
  Test Case Design/       # one HLT doc per component
  releases/
    R1.0/
      src/                  # full multi-file C tree (6 components)
      vcu_R1.0.elf            # ARM ELF w/ DWARF (after build_all.sh)
      architecture_ports.csv / .xlsx
      requirements.csv / .xlsx
    R2.0/
      src/                  # full multi-file C tree (7 components)
      vcu_R2.0.elf            # ARM ELF w/ DWARF (after build_all.sh)
      architecture_ports.csv / .xlsx
      requirements.csv / .xlsx
    R3.0/
      src/                  # full multi-file C tree (8 components)
      vcu_R3.0.elf            # ARM ELF w/ DWARF (after build_all.sh)
      architecture_ports.csv / .xlsx
      requirements.csv / .xlsx
    R4.0/
      src/                  # full multi-file C tree (8 components)
      vcu_R4.0.elf            # ARM ELF w/ DWARF (after build_all.sh)
      architecture_ports.csv / .xlsx
      requirements.csv / .xlsx
    R5.0/
      src/                  # full multi-file C tree (8 components)
      vcu_R5.0.elf            # ARM ELF w/ DWARF (after build_all.sh)
      architecture_ports.csv / .xlsx
      requirements.csv / .xlsx
```

## How to drive every feature
1. **New Project** → save it → set a master password.
2. **Releases:** create one release per `releases/RX.Y` folder; **Load New ELF** →
   that release's `vcu_RX.Y.elf`.
3. **Architecture import:** import `architecture_ports.csv` (or `.xlsx`). Each
   component is a separate **model**; the `Operations` column holds real exported
   function names, so symbol matching resolves at score 100.
4. **Code Map / AI:** point the source at that release's `src/` folder.
5. **Change Log:** Compute Release Diffs between two releases' `src/` folders to
   see added/removed/modified functions, struct-field and signature changes
   (see `CHANGELOG.md` for what to expect).
6. **Requirements / Test Design:** import `requirements.csv`; use the
   `Test Case Design/` docs in the AI Test Generation tab.

## Rebuilding
```
# regenerate sources + exports (needs venv for openpyxl)
.venv/bin/python ForTesting/VCU_TestProject/generate_project.py
# bigger: VCU_SCALE=3 .venv/bin/python ForTesting/VCU_TestProject/generate_project.py
# compile the ELFs (needs clang w/ arm-none-eabi target)
PYTHON=.venv/bin/python ForTesting/VCU_TestProject/build_all.sh
```

## Notes on the ELF (same fixup as the demo)
No standalone ARM linker is available on the build host, so each release's
translation units are amalgamated into one compile unit and emitted as a single
**relocatable** ARM ELF (`ET_REL`) with DWARF. `patch_debug_relocs.py` pre-applies
the DWARF debug relocations so both the native Rust parser and the pyelftools
fallback read identical, correct symbols / params / structs / globals. This is a
fixture build step only — not part of the shipped app.
