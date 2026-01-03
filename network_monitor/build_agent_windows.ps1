$ErrorActionPreference = "Stop"

Write-Host "Building Windows agent exe..." -ForegroundColor Cyan

python -m pip install --upgrade pip
python -m pip install -r "requirements-agent.txt"

if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

python -m PyInstaller "agent.spec"

$exePath = Join-Path "dist" "network-monitor-agent.exe"
if (!(Test-Path $exePath)) { throw "Expected exe not found: $exePath" }

Write-Host "Built: $exePath" -ForegroundColor Green

Write-Host ""
Write-Host "Optional signing (requires signtool + a code signing cert):" -ForegroundColor Yellow
Write-Host "  signtool sign /fd SHA256 /td SHA256 /tr http://timestamp.digicert.com /f cert.pfx /p <password> $exePath"
