@echo off
setlocal EnableExtensions EnabledDelayedExpansion

rem ===============================
rem ByteRescue Launcher
rem ===============================

cd /d "%~dp0"
set "APP_FILE=%~dp0app.py"

if not exist "%APP_FILE%" (
  cls
  color 0C
  echo.
  echo [ERROR] app.py was not found in the current folder.
  echo Please make sure ByteRescue is installed correctly.
  echo.
  pause
  exit /b 1
)

color 0A
title ByteRescue
cls

rem Fancy banner
echo  .---.      .-''-.   .--.   .-./`) ,---.    .-'''-.  
echo  |   |  .--./) / _ `\\  |  |  \ _ /| |   |  / _     \
 echo  |   | / _ /|  // / /  |  |  ( ' ) |   |  | / )   | |
 echo  |   |( ' )|  || | |  |  |  .(_./) |   |  .-.\  | |
 echo  |   | / /  |  || | |  |  |  .---. |   |  |  '|'  | |
 echo  |   |(_/  .|  || | |  |  |  |   | |   |  |  | |  | |
 echo  |   |     /|  \\ \_\_/  |  |  |   | |   |  |  | |  | |
 echo  |   |   .' |   `-.__.'|  |  |   | |   |  |  | |  | |
 echo  '---'---'   `-.__.-'  '--'  '--'   '---'  `-._| |-' 
 echo.
 echo    ======  B Y T E  R E S C U E  ======
 echo.

echo Starting ByteRescue...

where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    cls
    color 0C
    echo.
    echo [ERROR] Python 3.11+ was not found on this system.
    echo Please install Python 3.11 or newer and make sure it is in PATH.
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
  echo [ERROR] Python 3.11 or newer is required to run ByteRescue.
  echo Your current Python version is too old or not configured correctly.
  echo.
  pause
  exit /b 1
)

%PYTHON_CMD% app.py
if errorlevel 1 (
  echo.
  echo [ERROR] ByteRescue exited with an error.
  echo Review the console output above and press any key to exit.
  echo.
  pause
)

exit /b %errorlevel%
