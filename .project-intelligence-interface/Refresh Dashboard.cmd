@echo off
rem Rebuild the dashboard snapshot, then open it. Needs Python 3.10+ and Git on PATH.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  py -3 refresh.py
) else (
  python refresh.py
)
if errorlevel 1 (
  echo Refresh failed. The previous snapshot was preserved.
  pause
  exit /b 1
)
start "" "%~dp0index.html"
