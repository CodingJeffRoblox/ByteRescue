@echo off
:: Thin double-click shim -- the real launcher logic (elevation, Python
:: detection/auto-install, launching the app) lives in ByteRescue.ps1.
:: Batch is a poor fit for that logic; see ByteRescue.ps1's header comment.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ByteRescue.ps1"
exit /b %errorlevel%
