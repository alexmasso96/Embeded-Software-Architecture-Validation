#!/usr/bin/env bash
# Build one ARM ELF (with DWARF) per VCU release.
#
# No standalone ARM linker (lld / arm-none-eabi-ld) is available on the build
# host, so each release's translation units are amalgamated into ONE compile
# unit and emitted as a single relocatable ARM ELF (ET_REL). That gives the ELF
# parser distinct per-function offsets, sizes, parameters, structs and globals
# via DWARF (-g) without a link step. patch_debug_relocs.py then pre-applies the
# DWARF debug relocations so both parser backends read identical, correct data.
#
# Usage:  ./build_all.sh            (or: PYTHON=.venv/bin/python ./build_all.sh)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
CC=${CC:-clang}
TARGET=arm-none-eabi
CFLAGS="-target ${TARGET} -g -gdwarf-4 -O0 -ffreestanding -nostdlib -fno-builtin -Wno-unused"
PYTHON_BIN="${PYTHON:-python3}"

build_one () {
    local rel="$1"
    local srcdir="${here}/releases/${rel}/src"
    local amalgam="${here}/.amalgam_${rel}.c"
    local out="${here}/releases/${rel}/vcu_${rel}.elf"

    : > "${amalgam}"
    # Amalgamate every translation unit. vcu_main.c last so prototypes are seen.
    while IFS= read -r c; do
        rel_path="${c#${srcdir}/}"
        echo "#include \"${rel_path}\"" >> "${amalgam}"
    done < <(find "${srcdir}" -name '*.c' ! -name 'vcu_main.c' | sort)
    echo "#include \"vcu_main.c\"" >> "${amalgam}"

    "${CC}" ${CFLAGS} -I"${srcdir}" -c "${amalgam}" -o "${out}"
    rm -f "${amalgam}"
    "${PYTHON_BIN}" "${here}/patch_debug_relocs.py" "${out}"
    printf 'built %-22s ' "vcu_${rel}.elf"
    ls -lh "${out}" | awk '{print $5}'
}

for rel in R1.0 R2.0 R3.0 R4.0 R5.0; do
    build_one "${rel}"
done
echo "All ELFs built."
