<#
.SYNOPSIS
  Runs one of KANAT's background components and starts it again whenever it
  exits. What each "KANAT ..." scheduled task runs (install-services.ps1).

.PARAMETER Component
  mediamtx   the camera video server
  backend    the WebApp backend (applies the database migrations, then serves)
  detection  the Detection Service's supervisor, which runs the service

.PARAMETER RunMode
  detection only: how each camera's Run runs, as threads of one process
  (one shared model) or as a process of its own (a model each).
#>
param(
    [Parameter(Mandatory)][ValidateSet("mediamtx", "backend", "detection")][string]$Component,
    [ValidateSet("threads", "processes")][string]$RunMode = "threads"
)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\kanat-common.ps1"

$Root = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Force -Path $KanatLogDir | Out-Null

# What the launcher itself does is in launcher.log; each component's own log
# (backend.log, detection.log) is written by the component, which is what the
# app's Logs tab reads. What a component prints before it can log (a crash on
# start) is in <component>.out.log and .err.log, the last start's.
function Log($text) {
    $line = "{0:yyyy-MM-dd HH:mm:ss} [{1}] {2}" -f (Get-Date), $Component, $text
    try { Add-Content -Path (Join-Path $KanatLogDir "launcher.log") -Value $line -Encoding UTF8 } catch { }
}

# launcher.log grows with every restart: keep one past copy of about 5 MB
$launcherLog = Join-Path $KanatLogDir "launcher.log"
if ((Test-Path $launcherLog) -and (Get-Item $launcherLog).Length -gt 5MB) {
    Move-Item -Force $launcherLog "$launcherLog.prev"
}

# One copy of this component: what is left of a previous run (its task stopped,
# its processes not) would hold the port. Only this component's folder: the other
# two tasks start at the same time, and what they run is not this task's to end
$ownFolder = @{ mediamtx = "video"; backend = "backend"; detection = "detection" }[$Component]
Stop-KanatProcesses $Root -Only $ownFolder

# The command this component runs: the program, its arguments, its folder and
# its settings (environment variables, which the child inherits)
function Get-ComponentCommand {
    switch ($Component) {
        "mediamtx" {
            return @{ File = (Join-Path $Root "video\mediamtx.exe"); Args = @("mediamtx.yml"); Cwd = (Join-Path $Root "video") }
        }
        "backend" {
            $env:DATABASE_URL = "sqlite:///" + ((Join-Path $KanatDataDir "kanat.db") -replace "\\", "/")
            $env:LOG_DIR = $KanatLogDir
            $env:MEDIAMTX_CONFIG = Join-Path $Root "video\mediamtx.yml"
            # WeasyPrint's Pango and GTK libraries, carried with KANAT
            $env:WEASYPRINT_DLL_DIRECTORIES = Join-Path $Root "backend\gtk\bin"
            return @{ File = (Join-Path $Root "backend\python\python.exe"); Cwd = (Join-Path $Root "backend\service")
                      Args = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--timeout-graceful-shutdown", "2") }
        }
        "detection" {
            $env:YOLO_OFFLINE = "1"   # the PC is offline: ultralytics checks nothing online
            $mode = if ($RunMode -eq "processes") { "process" } else { "thread" }
            return @{ File = (Join-Path $Root "detection\python\python.exe"); Cwd = (Join-Path $Root "detection\service")
                      Args = @("-m", "detection.supervisor", "--run-mode", $mode, "--log-dir", $KanatLogDir,
                               "--backend-url", "http://127.0.0.1:8000") }
        }
    }
}

# Runs `file args` to its end in `cwd`, its output in the component's files; its exit code
function Invoke-Component($file, $arguments, $cwd) {
    $out = Join-Path $KanatLogDir "$Component.out.log"
    $err = Join-Path $KanatLogDir "$Component.err.log"
    $p = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $cwd -WindowStyle Hidden `
        -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    # Windows PowerShell 5.1: without the handle cached first, ExitCode of a -PassThru process is
    # $null after the wait, and `$null -ne 0` made every migration look failed
    $null = $p.Handle
    $p.WaitForExit()
    if ($null -eq $p.ExitCode) { return 1 }
    return [int]$p.ExitCode
}

# Settings every component reads: Python's own, so the PC's user packages and
# a console's code page never change what runs
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"

$spec = Get-ComponentCommand
if (-not (Test-Path $spec.File)) {
    Log "FAILED: $($spec.File) is missing (reinstall KANAT)"
    exit 1
}
Log "starting: $($spec.File) $($spec.Args -join ' ')"

$delay = 1
while ($true) {
    $started = Get-Date
    try {
        $ready = $true
        if ($Component -eq "backend") {
            # The database is created or brought up to date before the backend serves
            $code = Invoke-Component $spec.File @("-m", "alembic", "upgrade", "head") $spec.Cwd
            if ($code -ne 0) { Log "the database migration failed (exit $code): see backend.err.log"; $ready = $false }
        }
        if ($ready) {
            $code = Invoke-Component $spec.File $spec.Args $spec.Cwd
            Log "stopped with exit code $code"
        }
    } catch {
        Log "FAILED to run: $($_.Exception.Message)"
    }
    # A component that ran well starts again at once; one that keeps dying waits longer each time
    if (((Get-Date) - $started).TotalSeconds -ge 60) { $delay = 1 }
    Log "starting again in $delay s"
    Start-Sleep -Seconds $delay
    $delay = [Math]::Min($delay * 2, 30)
}
