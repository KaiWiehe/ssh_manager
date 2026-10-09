$ErrorActionPreference = "Stop"

function Invoke-BuildStep {
    param(
        [string]$Step,
        [string]$Program,
        [string[]]$Arguments
    )

    Write-Host "==> $Step" -ForegroundColor Cyan
    try {
        & $Program @Arguments
        $ExitCode = $LASTEXITCODE
    }
    catch {
        throw "Build step '$Step' could not run: $($_.Exception.Message)"
    }
    if ($ExitCode -ne 0) {
        throw "Build step '$Step' failed (exit code $ExitCode)."
    }
}

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

Invoke-BuildStep "Python" $Python @("--version")

Invoke-BuildStep "Checking version metadata" $Python @("scripts\bump_version.py", "--check")

Invoke-BuildStep "Installing pinned build dependencies" $Python @("-m", "pip", "install", "-r", "requirements-dev.txt")

Write-Host "==> Cleaning previous build" -ForegroundColor Cyan
foreach ($Directory in @("build", "dist")) {
    # Fixed, absolute targets inside this repository only.
    $BuildPath = Join-Path $RepoRoot $Directory
    if (Test-Path -LiteralPath $BuildPath) {
        Remove-Item -LiteralPath $BuildPath -Recurse -Force -ErrorAction Stop
    }
    if (Test-Path -LiteralPath $BuildPath) {
        throw "Build cleanup failed: $BuildPath still exists."
    }
}

Invoke-BuildStep "Building portable EXE" $Python @("-m", "PyInstaller", "--clean", "--noconfirm", "ssh_manager.spec")

$Exe = Join-Path $RepoRoot "dist\SSH Manager.exe"
if (!(Test-Path -LiteralPath $Exe -PathType Leaf)) {
    throw "Build fehlgeschlagen: $Exe wurde nicht erzeugt."
}
if ((Get-Item -LiteralPath $Exe).Length -eq 0) {
    throw "Build failed: $Exe is empty."
}

Write-Host "" 
Write-Host "Fertig: $Exe" -ForegroundColor Green
