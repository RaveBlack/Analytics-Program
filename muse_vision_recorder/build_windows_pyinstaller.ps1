Param(
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

function Remove-DirIfExists([string]$Path) {
  if (Test-Path $Path) {
    try {
      Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
    } catch {
      Write-Host "Failed to delete '$Path'. Close any running EXE, pause OneDrive sync, and try again."
      throw
    }
  }
}

Write-Host "Creating venv..."
& $Python -m venv .venv
& .\.venv\Scripts\Activate.ps1

Write-Host "Upgrading pip..."
python -m pip install --upgrade pip

Write-Host "Installing runtime requirements..."
pip install -r muse_vision_recorder\requirements.txt

Write-Host "Installing PyInstaller..."
pip install pyinstaller

# Build into a non-OneDrive folder to avoid WinError 5 permission issues.
$BuildRoot = Join-Path $env:LOCALAPPDATA "MuseVisionRecorderBuild"
$DistPath = Join-Path $BuildRoot "dist"
$WorkPath = Join-Path $BuildRoot "work"

Write-Host "Cleaning old build output..."
Remove-DirIfExists $DistPath
Remove-DirIfExists $WorkPath

Write-Host "Building EXE..."
pyinstaller --noconfirm --clean --distpath $DistPath --workpath $WorkPath muse_vision_recorder\pyinstaller.spec

Write-Host "Done. Output in:"
Write-Host "  $DistPath\\MuseVisionRecorder\\MuseVisionRecorder.exe"

