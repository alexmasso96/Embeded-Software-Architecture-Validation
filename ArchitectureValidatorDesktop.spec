# -*- mode: python ; coding: utf-8 -*-
#
# Phase 3 desktop shell (pywebview + FastAPI worker). Separate from the legacy
# PyQt spec (ArchitectureValidatorPro.spec) so both can ship side-by-side during
# the Phase 4 cutover window. Entry = src/desktop/main.py.
#
# Onedir (COLLECT) is deliberate: a onefile build re-extracts every launch,
# which re-triggers the EDR small-file scanning penalty this whole migration
# exists to avoid.
#
# NOTE: this spec has not been validated by an actual build here — PyInstaller
# specs always need a round of iteration on the real target OS (and the Windows
# WebView2 runtime check). Build + smoke-test on macOS and an EDR Windows box
# before relying on it (plan §5, §9 risk row "WebView2 missing").
import os
import sys

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None
console_build = bool(os.environ.get('ARCH_BUILD_CONSOLE'))

ICON_DIR = os.path.join('Media', 'icon')
ICON_ICO = os.path.join(ICON_DIR, 'app.ico')
ICON_ICNS = os.path.join(ICON_DIR, 'app.icns')
ICON_PNG = os.path.join(ICON_DIR, 'icon_1024.png')
exe_icon = ICON_ICO if sys.platform == 'win32' else (ICON_ICNS if sys.platform == 'darwin' else None)

# Bundle the built SPA at <bundle>/frontend/dist so backend.static.frontend_dist()
# finds it under sys._MEIPASS. Run `npm run build` in src/frontend/ BEFORE
# packaging. Source path is src/frontend/dist; bundle dest stays frontend/dist.
datas = [
    ('src/frontend/dist', 'frontend/dist'),
    (ICON_PNG, ICON_DIR),
]
# uvicorn/webview import their backends lazily — collect them so the frozen app
# can find the event loop, HTTP/WS protocols, and the platform webview backend.
datas += collect_data_files('webview')

hiddenimports = [
    'elftools', 'elftools.elf.elffile',
    'pandas', 'openpyxl', 'rapidfuzz', 'capstone', 'bcrypt',
    'rust_elf_parser', 'cpp_demangle', 'cryptography',
]
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('webview')

a = Analysis(
    ['src/desktop/main.py'],
    pathex=['.', 'src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The desktop shell never touches Qt; keep it out of the bundle.
    excludes=['PyQt6', 'PyQt6.sip'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ArchitectureValidator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=console_build,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=exe_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ArchitectureValidator',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='ArchitectureValidator.app',
        icon=ICON_ICNS,
        bundle_identifier='com.architecture.validator.desktop',
    )
