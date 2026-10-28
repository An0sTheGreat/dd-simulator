$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment not found. Run .\scripts\setup.ps1 first."
}

$env:QT_QPA_PLATFORM = "offscreen"
$TestTempBase = if ($env:DDSIM_TEST_TEMP_ROOT) {
    $env:DDSIM_TEST_TEMP_ROOT
} else {
    Join-Path ([System.IO.Path]::GetTempPath()) "DnDSimulatorTests"
}
$TestRun = Join-Path $TestTempBase ([guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TestRun | Out-Null

& $VenvPython -m pytest `
    --basetemp (Join-Path $TestRun "pytest") `
    -o "cache_dir=$(Join-Path $TestRun 'cache')" `
    (Join-Path $ProjectRoot "tests")
exit $LASTEXITCODE
