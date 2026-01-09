# -*- mode: python ; coding: utf-8 -*-
#
# Build (Windows recommended):
#   pyinstaller --clean muse_vision_recorder/pyinstaller.spec
#
# Output:
#   dist/MuseVisionRecorder/MuseVisionRecorder.exe
#
# Notes:
# - We explicitly collect pylsl dynamic libs (liblsl) because missing liblsl is a
#   common cause of "instant crash" in packaged builds.
# - We also add tkinter hidden imports because the GUI imports tkinter lazily.

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


block_cipher = None

binaries = []
datas = []
hiddenimports = []

# pylsl (LSL + liblsl)
try:
    binaries += collect_dynamic_libs("pylsl")
    datas += collect_data_files("pylsl")
    hiddenimports += ["pylsl"]
except Exception:
    # Allow building even if pylsl isn't present in build env;
    # the build scripts install requirements first.
    pass

# tkinter (lazy-imported in gui mode)
hiddenimports += ["tkinter", "tkinter.ttk", "tkinter.simpledialog", "tkinter.messagebox"]

a = Analysis(
    ["muse_vision_recorder/app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
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
    [],
    exclude_binaries=True,
    name="MuseVisionRecorder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # set True for debugging crash logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MuseVisionRecorder",
)

