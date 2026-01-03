param(
  [string]$Python = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& $Python -m pip install -r requirements.txt
& $Python -m pip install pyinstaller

# Spec-based build so templates / hidden imports are included.
& $Python -m PyInstaller --clean --noconfirm netmon.spec

Write-Host ""
Write-Host "Built: dist\NetMonTUI.exe"

