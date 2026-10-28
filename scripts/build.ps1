$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

Push-Location $ProjectRoot
try {
    & $VenvPython -m PyInstaller --noconfirm --clean DnDSimulator.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

Write-Host "Build complete: $ProjectRoot\dist\DnDSimulator\DnDSimulator.exe"
