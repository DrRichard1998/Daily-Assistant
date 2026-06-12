@echo off
setlocal

set "APP_DIR=%~dp0"
set "BUNDLED_PY=%APP_DIR%runtime\python\python.exe"
set "SOURCE_BUILD_SCRIPT=%APP_DIR%tools\build_portable.ps1"

if exist "%BUNDLED_PY%" (
  "%BUNDLED_PY%" "%APP_DIR%assistant.py" %*
  exit /b %ERRORLEVEL%
)

if exist "%SOURCE_BUILD_SCRIPT%" (
  where python >nul 2>nul
  if errorlevel 1 (
    echo DailyAssistant portable runtime was not found.
    echo This source checkout needs Python only to build or run in development mode.
    echo Build the portable package with:
    echo powershell -NoProfile -ExecutionPolicy Bypass -File "%SOURCE_BUILD_SCRIPT%"
    exit /b 9009
  )

  python "%APP_DIR%assistant.py" %*
  exit /b %ERRORLEVEL%
)

echo DailyAssistant portable runtime was not found.
echo Expected: "%BUNDLED_PY%"
echo This portable package is incomplete. Rebuild or copy the full DailyAssistantPortable directory.
exit /b 9009
