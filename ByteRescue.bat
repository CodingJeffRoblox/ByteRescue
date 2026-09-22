@echo off
setlocal EnableExtensions EnabledDelayedExpansion

title ByteRescue
color 0A
cd /d "%~dp0"

set "APP_PATH=%~dp0app.py"

if not exist "%APP_PATH%" (
  cls
  color 0C
  echo.
  echo [ERROR] app.py was not found in: %~dp0
  echo Please make sure the project files are complete.
  echo.
  pause
  exit /b 1
)

cls
echo.
echo   .-------------------------------.
echo   |       ByteRescue             |
echo   |      Starting up...           |
echo   '-------------------------------'
echo.
echo   Checking requirements...

where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    cls
    color 0C
    echo.
    echo [ERROR] Python 3.11+ was not found.
    echo Install Python 3.11 or newer and add it to PATH.
    echo.
    pause
    exit /b 1
  )
  set "PYTHON_CMD=py"
) else (
  set "PYTHON_CMD=python"
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 (
  cls
  color 0C
  echo.
  echo [ERROR] Python 3.11 or newer is required.
  echo Detected version is too old or not configured correctly.
  echo.
  pause
  exit /b 1
)

echo   Python check passed.
echo   Launching ByteRescue...
echo.
%PYTHON_CMD% app.py
if errorlevel 1 (
  echo.
  echo [ERROR] ByteRescue exited unexpectedly.
  echo Review the console output above, then press any key to close.
  echo.
  pause
)

exit /b %errorlevel%
