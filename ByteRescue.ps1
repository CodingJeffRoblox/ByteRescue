# ByteRescue launcher.
#
# Requests Administrator privileges (physical-drive scanning needs them),
# makes sure a working Python 3.11+ is available -- installing it via
# winget if it isn't -- then launches the application.
#
# ByteRescue.bat is a thin double-click shim that just runs this script;
# this is where the actual logic lives. Batch (.bat) is a poor fit for
# "elevate, detect, conditionally install, retry" -- the earlier all-batch
# version of this launcher had three real, independently-reproduced bugs
# in far simpler logic than this (see CHANGELOG.md), which is why this
# was rewritten in PowerShell instead of patched further in place.

Set-StrictMode -Version Latest
$ScriptDir = $PSScriptRoot
Set-Location -Path $ScriptDir

function Write-Banner {
    Write-Host ""
    Write-Host "  .-------------------------------." -ForegroundColor Green
    Write-Host "  |          ByteRescue           |" -ForegroundColor Green
    Write-Host "  |        Starting up...         |" -ForegroundColor Green
    Write-Host "  '-------------------------------'" -ForegroundColor Green
    Write-Host ""
}

function Write-ErrorAndWait {
    param([string[]]$Lines)
    Write-Host ""
    foreach ($line in $Lines) { Write-Host $line -ForegroundColor Red }
    Write-Host ""
    Read-Host "Press Enter to close" | Out-Null
}

Write-Banner

$appPath = Join-Path $ScriptDir "app.py"
if (-not (Test-Path -LiteralPath $appPath)) {
    Write-ErrorAndWait @(
        "[ERROR] app.py was not found in: $ScriptDir",
        "Please make sure the project files are complete."
    )
    exit 1
}

# --- Elevate to Administrator if not already running elevated ---------------
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "  Administrator privileges are required (for physical-drive scanning)."
    Write-Host "  Requesting elevation -- a new window will open; you can close this one."
    Write-Host ""
    $psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    try {
        Start-Process -FilePath "powershell" -ArgumentList $psArgs `
            -WorkingDirectory $ScriptDir -Verb RunAs -ErrorAction Stop | Out-Null
    } catch {
        Write-ErrorAndWait @(
            "[ERROR] Administrator privileges are required to run ByteRescue.",
            "Elevation was cancelled, or failed: $($_.Exception.Message)"
        )
        exit 1
    }
    exit 0
}

# --- Find a working Python 3.11+, trying `python` then the `py` launcher ----
function Get-WorkingPython {
    foreach ($cmd in @("python", "py")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if (-not $found) { continue }
        & $cmd -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return $cmd }
    }
    return $null
}

function Update-SessionPathFromRegistry {
    # An installer run from THIS session updates PATH in the registry, but
    # this already-running process keeps the PATH it started with -- new
    # child processes inherit that stale copy, not a fresh one, so without
    # this, even a successful install would look like it "didn't work"
    # until the window was closed and reopened.
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = @($machinePath, $userPath) -join ";"
}

Write-Host "  Checking requirements..."
$pythonCmd = Get-WorkingPython

if (-not $pythonCmd) {
    Write-Host "  Python 3.11 or newer was not found."
    $winget = Get-Command winget -ErrorAction SilentlyContinue

    if (-not $winget) {
        Write-ErrorAndWait @(
            "[ERROR] Python 3.11+ is required, and winget is not available to install it automatically.",
            "Please install Python 3.11 or newer from https://www.python.org/downloads/",
            "(check 'Add python.exe to PATH' during install), then run ByteRescue again."
        )
        exit 1
    }

    Write-Host "  Installing Python via winget -- this can take a few minutes..."
    $installedOk = $false
    foreach ($id in @("Python.Python.3.13", "Python.Python.3.12", "Python.Python.3.11")) {
        winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $installedOk = $true; break }
    }

    if (-not $installedOk) {
        Write-ErrorAndWait @(
            "[ERROR] Automatic installation via winget did not succeed.",
            "Please install Python 3.11 or newer from https://www.python.org/downloads/",
            "(check 'Add python.exe to PATH' during install), then run ByteRescue again."
        )
        exit 1
    }

    Update-SessionPathFromRegistry
    $pythonCmd = Get-WorkingPython

    if (-not $pythonCmd) {
        Write-ErrorAndWait @(
            "[ERROR] Python was installed, but this window still can't see it.",
            "Close this window and run ByteRescue again -- a fresh window will pick up the update."
        )
        exit 1
    }
    Write-Host "  Python installed successfully. Retrying..."
}

Write-Host "  Python check passed."
Write-Host "  Launching ByteRescue..."
Write-Host ""

& $pythonCmd $appPath
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-ErrorAndWait @(
        "[ERROR] ByteRescue exited unexpectedly -- exit code $exitCode.",
        "Review the console output above for details."
    )
}
exit $exitCode
