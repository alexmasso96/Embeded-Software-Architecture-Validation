#!/usr/bin/env python3
"""Pre-apply DWARF debug-section relocations in an ARM ET_REL object, then
remove the relocation entries entirely.

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

This script applies the debug relocations correctly **in place** and then
**empties the relocation sections** (sets each `.rel.debug_*` section's
`sh_size` to 0 in the section-header table). With zero relocation entries left,
neither backend tries to re-apply anything: both read the already-correct,
pre-applied in-place values.

An earlier version instead set each relocation's type to R_ARM_NONE (0). That
works for the native parser but pyelftools *rejects* type 0
(`ELFRelocationError: Unsupported relocation type: 0`), which broke the demo for
the source-run / CI path (no native extension → pyelftools). Emptying the
sections is backend-agnostic.

This is a build-time fixup for the test fixture only; it is NOT part of the
shipped app.

Usage: patch_debug_relocs.py <in.elf> [out.elf]   (default: patch in place)
"""
import sys, struct
sys.path.insert(0, "src")  # for pyelftools if run from repo root; harmless otherwise
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection

R_ARM_NONE = 0
R_ARM_ABS32 = 2
R_ARM_REL32 = 3

# ELF32 section-header layout: sh_size is the 4-byte field at offset 20.
ELF32_SHDR_SH_SIZE_OFF = 20


def patch(in_path: str, out_path: str) -> None:
    with open(in_path, "rb") as fh:
        blob = bytearray(fh.read())
    elf = ELFFile(open(in_path, "rb"))

    e_shoff = elf["e_shoff"]
    e_shentsize = elf["e_shentsize"]
    sections_to_empty = []  # section indices whose sh_size we zero after applying

    for idx, rel in enumerate(elf.iter_sections()):
        if not isinstance(rel, RelocationSection):
            continue
        target = elf.get_section(rel["sh_info"])
        if "debug" not in target.name:
            continue
        symtab = elf.get_section(rel["sh_link"])
        tgt_off = target["sh_offset"]
        tgt_size = target["sh_size"]
        for r in rel.iter_relocations():
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
        sections_to_empty.append(idx)

    # Empty the relocation sections: zero sh_size so both pyelftools and the
    # native parser iterate 0 relocations and leave the pre-applied bytes alone.
    for idx in sections_to_empty:
        shdr = e_shoff + idx * e_shentsize
        struct.pack_into("<I", blob, shdr + ELF32_SHDR_SH_SIZE_OFF, 0)

    with open(out_path, "wb") as fh:
        fh.write(blob)
    print(f"patched {in_path} -> {out_path} (emptied {len(sections_to_empty)} reloc section(s))")


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    patch(src, dst)
