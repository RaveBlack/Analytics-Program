# PyInstaller spec for a single-file Windows executable.
#
# Build (Windows PowerShell):
#   pyinstaller --clean --noconfirm netmon.spec
#
# Output:
#   dist\NetMonTUI.exe

# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = []
hiddenimports += collect_submodules("scapy")
hiddenimports += collect_submodules("eventlet")
hiddenimports += collect_submodules("engineio")
hiddenimports += collect_submodules("socketio")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("templates/index.html", "templates"),
    ],
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="NetMonTUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

