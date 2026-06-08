#!/usr/bin/env python3
"""Pre-apply and neutralize DWARF debug-section relocations in an ARM ET_REL object.

Why this exists
---------------
clang on this host can only emit a *relocatable* ARM ELF (no ELF linker is
available). In a relocatable object, DWARF string/type references in
.debug_info are stored as `0 + relocation`, where ARM uses REL relocations
(the addend is held *in place* in the section bytes). A correct consumer
(pyelftools) applies `symbol_value + in_place_addend`.

The bundled native parser (rust_elf_parser) mishandles REL/implicit-addend
relocations on debug sections — it uses `symbol_value + 0`, zeroing every
offset, so all DWARF names collapse to the producer string and parameters are
lost. (Linked executables have no debug relocations, so the native parser is
fine there — the bug is specific to ET_REL objects.)

This script applies the debug relocations correctly in place and then
neutralizes them (sets each debug relocation's type to R_ARM_NONE), so BOTH
backends read identical, correct DWARF. It is a build-time fixup for the test
fixture only; it is NOT part of the shipped app.

Usage: patch_debug_relocs.py <in.elf> [out.elf]   (default: patch in place)
"""
import sys, struct
sys.path.insert(0, "src")  # for pyelftools if run from repo root; harmless otherwise
try:
    from elftools.elf.elffile import ELFFile
    from elftools.elf.relocation import RelocationSection
except ImportError:
    # fall back to the app's venv path layout
    from elftools.elf.elffile import ELFFile
    from elftools.elf.relocation import RelocationSection

R_ARM_NONE = 0
R_ARM_ABS32 = 2
R_ARM_REL32 = 3


def patch(in_path: str, out_path: str) -> None:
    with open(in_path, "rb") as fh:
        blob = bytearray(fh.read())
    elf = ELFFile(open(in_path, "rb"))

    for rel in elf.iter_sections():
        if not isinstance(rel, RelocationSection):
            continue
        target = elf.get_section(rel["sh_info"])
        if "debug" not in target.name:
            continue
        symtab = elf.get_section(rel["sh_link"])
        tgt_off = target["sh_offset"]
        tgt_size = target["sh_size"]
        rel_off = rel["sh_offset"]
        ent_size = rel["sh_entsize"] or 8
        for i, r in enumerate(rel.iter_relocations()):
            rtype = r["r_info_type"]
            off = r["r_offset"]
            if off + 4 > tgt_size:
                continue
            sym = symtab.get_symbol(r["r_info_sym"])
            symval = sym["st_value"]
            inplace = struct.unpack_from("<I", blob, tgt_off + off)[0]
            if rtype == R_ARM_ABS32:
                value = (symval + inplace) & 0xFFFFFFFF
            elif rtype == R_ARM_REL32:
                value = (symval + inplace - off) & 0xFFFFFFFF
            else:
                continue
            struct.pack_into("<I", blob, tgt_off + off, value)
            # neutralize: set this relocation's type byte to R_ARM_NONE
            ri_pos = rel_off + i * ent_size + 4  # low byte of r_info
            blob[ri_pos] = R_ARM_NONE
    with open(out_path, "wb") as fh:
        fh.write(blob)
    print(f"patched {in_path} -> {out_path}")


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    patch(src, dst)
