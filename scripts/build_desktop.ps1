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

Write-Host '==> 1/4 Building React frontend (src/frontend/dist)'
Push-Location src/frontend
npm ci
npm run build
Pop-Location

Write-Host '==> 2/4 Building Rust ELF parser wheel'
& $Python -m pip install --upgrade pip maturin
& $Python -m maturin build --release --manifest-path src/native/parser_rust/Cargo.toml --out target/wheels
& $Python -m pip install --no-index --find-links target/wheels rust_elf_parser

Write-Host '==> 3/4 Installing Python dependencies'
& $Python -m pip install -r requirements.txt

Write-Host '==> 4/4 Packaging with PyInstaller (onedir)'
& $Python -m PyInstaller ArchitectureValidatorDesktop.spec --noconfirm --clean

Write-Host ''
Write-Host 'Build complete. Artifact under dist/:'
Write-Host '  dist/ArchitectureValidator/ArchitectureValidator.exe'
Write-Host ''
Write-Host 'Target-machine prerequisites (the pywebview winforms backend needs both):' -ForegroundColor Yellow
Write-Host '  * Microsoft Edge WebView2 Evergreen Runtime - match the CPU arch.'
Write-Host '    A missing/wrong-arch runtime shows a BLANK WHITE WINDOW (seen on Windows-on-ARM).'
Write-Host '    Install the ARM64 runtime on ARM devices, x64 on x64.'
Write-Host '  * .NET Framework 4.7.2 or newer (pythonnet/clr_loader bootstrap target).'
Write-Host '    Absent/old .NET => "Failed to resolve Python.Runtime.Loader.Initialize".'
Write-Host ''
Write-Host 'If the app fails to start, the full traceback is written to:'
Write-Host '  %LOCALAPPDATA%\ArchitectureValidator\crash.log'
Write-Host 'For a live console + tracebacks, build the debug variant:'
Write-Host '  $env:ARCH_BUILD_CONSOLE = "1"; ./scripts/build_desktop.ps1'
