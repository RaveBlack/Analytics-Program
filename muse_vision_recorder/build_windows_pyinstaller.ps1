Param(
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

Write-Host "Creating venv..."
& $Python -m venv .venv
& .\.venv\Scripts\Activate.ps1

Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

Write-Host "Installing runtime requirements..."
pip install -r muse_vision_recorder\requirements.txt

Write-Host "Installing PyInstaller..."
pip install pyinstaller

Write-Host "Building EXE..."
pyinstaller --clean muse_vision_recorder\pyinstaller.spec

Write-Host "Done. Output in dist\MuseVisionRecorder\"

