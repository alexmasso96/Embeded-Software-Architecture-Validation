#!/usr/bin/env bash
#
# Build the Phase 3 desktop app (pywebview + FastAPI worker) for the host OS.
# Works on macOS and Linux. For Windows use scripts/build_desktop.ps1.
#
#   ./scripts/build_desktop.sh
#
# Steps: build the React SPA -> build the Rust ELF parser wheel -> install
# Python deps -> run PyInstaller against ArchitectureValidatorDesktop.spec.
# PyInstaller is NOT a cross-compiler: run this once per target OS.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python3}"

echo "==> 1/4 Building React frontend (frontend/dist)"
( cd frontend && npm ci && npm run build )

echo "==> 2/4 Building Rust ELF parser wheel"
"$PYTHON" -m pip install --upgrade pip maturin
MATURIN_ARGS=(build --release --manifest-path native/parser_rust/Cargo.toml --out target/wheels)
if [ "$(uname -s)" = "Linux" ]; then
  # Skip the manylinux repair (needs patchelf); the wheel is only consumed
  # locally by PyInstaller, never published.
  MATURIN_ARGS+=(--compatibility linux)
fi
"$PYTHON" -m maturin "${MATURIN_ARGS[@]}"
"$PYTHON" -m pip install --no-index --find-links target/wheels rust_elf_parser

echo "==> 3/4 Installing Python dependencies"
"$PYTHON" -m pip install -r requirements.txt

echo "==> 4/4 Packaging with PyInstaller (onedir)"
"$PYTHON" -m PyInstaller ArchitectureValidatorDesktop.spec --noconfirm --clean

echo
echo "Build complete. Artifact(s) under dist/:"
if [ "$(uname -s)" = "Darwin" ]; then
  echo "  dist/ArchitectureValidator.app"
else
  echo "  dist/ArchitectureValidator/  (run dist/ArchitectureValidator/ArchitectureValidator)"
fi
