param(
  [string]$Python = "py"
)

$ErrorActionPreference = "Stop"

Write-Host "Creating venv..."
& $Python -m venv .venv

Write-Host "Activating venv..."
& .\.venv\Scripts\Activate.ps1

Write-Host "Installing runtime deps..."
pip install -r controller_turbo_windows\requirements.txt

Write-Host "Installing build deps..."
pip install -r controller_turbo_windows\requirements-build.txt

Write-Host "Building exe with PyInstaller..."
pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name turbo_pad_win `
  --hidden-import inputs `
  --hidden-import vgamepad `
  controller_turbo_windows\main.py

Write-Host ""
Write-Host "Built: dist\turbo_pad_win.exe"

