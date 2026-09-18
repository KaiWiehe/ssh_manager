$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

Write-Host "==> Python" -ForegroundColor Cyan
& $Python --version

Write-Host "==> Installing pinned build dependencies" -ForegroundColor Cyan
& $Python -m pip install -r requirements-dev.txt

Write-Host "==> Cleaning previous build" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "==> Building portable EXE" -ForegroundColor Cyan
& $Python -m PyInstaller --clean --noconfirm ssh_manager.spec

$Exe = Join-Path $RepoRoot "dist\SSH Manager.exe"
if (!(Test-Path $Exe)) {
    throw "Build fehlgeschlagen: $Exe wurde nicht erzeugt."
}

Write-Host "" 
Write-Host "Fertig: $Exe" -ForegroundColor Green
