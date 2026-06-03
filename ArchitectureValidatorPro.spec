# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

# Build a console-enabled executable when ARCH_BUILD_CONSOLE is set (e.g. by
# build_windows.bat --debug). A console build prints Python tracebacks to the
# terminal, which makes diagnosing startup crashes in a fresh VM much easier.
console_build = bool(os.environ.get('ARCH_BUILD_CONSOLE'))

# Platform application icon. PyInstaller uses .ico for the Windows EXE and
# .icns for the macOS .app bundle. The PNG is bundled as data so the running
# app can set its window/taskbar icon at runtime (see src/main.py).
ICON_DIR = os.path.join('Media', 'icon')
ICON_ICO = os.path.join(ICON_DIR, 'app.ico')
ICON_ICNS = os.path.join(ICON_DIR, 'app.icns')
ICON_PNG = os.path.join(ICON_DIR, 'icon_1024.png')
exe_icon = ICON_ICO if sys.platform == 'win32' else (ICON_ICNS if sys.platform == 'darwin' else None)

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    # NOTE: do NOT add collect_data_files('PyQt6') here. PyInstaller's bundled
    # PyQt6 hook already ships the needed Qt libraries and platform plugins and
    # prunes unused ones. Collecting the whole PyQt6 package as data overrides
    # that pruning and bundles every Qt framework + QML + .sip dev files,
    # roughly doubling the build (macOS .app went 138 MB -> 281 MB).
    datas=[(ICON_PNG, ICON_DIR)],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtNetwork',
        'PyQt6.sip',
        'elftools',
        'elftools.elf.elffile',
        'pandas',
        'openpyxl',
        'rapidfuzz',
        'capstone',
        'bcrypt',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='ArchitectureValidatorPro',
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
    name='ArchitectureValidatorPro',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='ArchitectureValidatorPro.app',
        icon=ICON_ICNS,
        bundle_identifier='com.architecture.validator.pro',
    )
