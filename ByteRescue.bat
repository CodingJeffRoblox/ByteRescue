@echo off
setlocal enableextensions enabledelayedexpansion

rem --- ByteRescue Windows launcher ---
color 0A
title ByteRescue
cls

cd /d "%~dp0"

rem Prefer Python, then fallback to Windows Store launcher
where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    echo.
    echo [ERROR] Python 3.11+ was not found on this system.
    echo Please install Python 3.11 or newer and ensure it is in PATH.
    echo.
    pause
    exit /b 1
  )
  set "PYTHON_CMD=py"
) else (
  set "PYTHON_CMD=python"
)

rem Check Python version requirement
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [ERROR] Python 3.11 or newer is required to run ByteRescue.
  echo Please install a supported version and try again.
  echo.
  pause
  exit /b 1
)

echo ===============================================================
echo                     ByteRescue Launcher
echo ===============================================================
echo.
echo Starting ByteRescue...

%PYTHON_CMD% app.py
if errorlevel 1 (
  echo.
  echo [ERROR] ByteRescue exited with an error.
  echo Review the console output above, then press any key to close.
  echo.
  pause
)

exit /b %errorlevel%
