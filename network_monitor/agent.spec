# PyInstaller spec for building a single-file agent executable.
#
# Build (Windows/macOS):
#   pyinstaller agent.spec
#
# Output:
#   dist/network-monitor-agent(.exe)
#

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("socketio")

a = Analysis(
    ["agent.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="network-monitor-agent",
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
