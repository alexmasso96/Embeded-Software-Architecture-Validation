#!/usr/bin/env bash
# Build ARM ELF fixtures (with DWARF) from the WindowLift C sources.
#
# There is no standalone ARM linker (lld / arm-none-eabi-ld) on the build host,
# so each version's translation units are amalgamated into ONE compile unit and
# emitted as a single relocatable ARM ELF (.elf). That gives the ELF parser
# distinct per-function offsets, sizes, parameters, structs and globals via
# DWARF (-g) without needing a link step. The C source tree stays multi-file
# for the code indexer / code map (which map functions to files from the C
# source, not the ELF).
#
# Usage:  ./build_elf.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
CC=${CC:-clang}
TARGET=arm-none-eabi
CFLAGS="-target ${TARGET} -g -gdwarf-4 -O0 -ffreestanding -nostdlib -fno-builtin"

build_one () {
    local ver="$1"; shift
    local srcdir="${here}/src_${ver}"
    local amalgam="${here}/.amalgam_${ver}.c"
    : > "${amalgam}"
    for c in "$@"; do
        echo "#include \"${c}\"" >> "${amalgam}"
    done
    "${CC}" ${CFLAGS} -I"${srcdir}" -c "${amalgam}" -o "${here}/wlc_${ver}.elf"
    rm -f "${amalgam}"
    # Pre-apply + neutralize DWARF debug relocations so BOTH the native and the
    # pyelftools backends read correct DWARF from this relocatable object.
    "${PYTHON:-python3}" "${here}/patch_debug_relocs.py" "${here}/wlc_${ver}.elf"
    echo "built wlc_${ver}.elf"
    file "${here}/wlc_${ver}.elf"
}

build_one v1 wlc_motor.c wlc_sensor.c wlc_main.c
build_one v2 wlc_motor.c wlc_sensor.c wlc_safety.c wlc_main.c
