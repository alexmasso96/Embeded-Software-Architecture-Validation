<#
.SYNOPSIS
  Build the Phase 3 desktop app (pywebview + FastAPI worker) on Windows.

.DESCRIPTION
  Builds the React SPA, builds the Rust ELF parser wheel, installs Python
  deps, then runs PyInstaller against ArchitectureValidatorDesktop.spec.
  PyInstaller is NOT a cross-compiler: run this on Windows to get the .exe.

  Usage:  ./scripts/build_desktop.ps1
#>
$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $RepoRoot

$Python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }

Write-Host '==> 1/4 Building React frontend (frontend/dist)'
Push-Location frontend
npm ci
npm run build
Pop-Location

Write-Host '==> 2/4 Building Rust ELF parser wheel'
& $Python -m pip install --upgrade pip maturin
& $Python -m maturin build --release --manifest-path native/parser_rust/Cargo.toml --out target/wheels
& $Python -m pip install --no-index --find-links target/wheels rust_elf_parser

Write-Host '==> 3/4 Installing Python dependencies'
& $Python -m pip install -r requirements.txt

Write-Host '==> 4/4 Packaging with PyInstaller (onedir)'
& $Python -m PyInstaller ArchitectureValidatorDesktop.spec --noconfirm --clean

Write-Host ''
Write-Host 'Build complete. Artifact under dist/:'
Write-Host '  dist/ArchitectureValidator/ArchitectureValidator.exe'
