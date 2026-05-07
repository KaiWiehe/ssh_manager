$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host "==> Python" -ForegroundColor Cyan
python --version

Write-Host "==> Checking PyInstaller" -ForegroundColor Cyan
$HasPyInstaller = $false
try {
    python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -eq 0) { $HasPyInstaller = $true }
} catch {
    $HasPyInstaller = $false
}

if (-not $HasPyInstaller) {
    Write-Host "PyInstaller fehlt. Installiere in die aktuelle Python-Umgebung..." -ForegroundColor Yellow
    python -m pip install --upgrade pyinstaller
}

Write-Host "==> Cleaning previous build" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "==> Building portable EXE" -ForegroundColor Cyan
python -m PyInstaller --clean --noconfirm ssh_manager.spec

$Exe = Join-Path $RepoRoot "dist\SSH Manager.exe"
if (!(Test-Path $Exe)) {
    throw "Build fehlgeschlagen: $Exe wurde nicht erzeugt."
}

Write-Host "" 
Write-Host "Fertig: $Exe" -ForegroundColor Green
