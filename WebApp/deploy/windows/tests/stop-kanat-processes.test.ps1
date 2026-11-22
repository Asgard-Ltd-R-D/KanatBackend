# Checks Stop-KanatProcesses (scripts\kanat-common.ps1) on a fake install folder:
# a launcher ends only its own component, the installer ends the whole install,
# and the app is left alone unless it is asked for. Windows PowerShell 5.1:
#   powershell -NoProfile -File WebApp\deploy\windows\tests\stop-kanat-processes.test.ps1
# Stand-ins are copies of cmd.exe, put where KANAT's programs are installed and
# started waiting, so they match by path as the real ones do.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\..\scripts\kanat-common.ps1"

$root = Join-Path ([IO.Path]::GetTempPath()) ("kanat-test-" + [guid]::NewGuid().ToString("N"))
$programs = [ordered]@{
    mediamtx  = "video\mediamtx.exe"
    backend   = "backend\python\python.exe"
    detection = "detection\python\python.exe"
    app       = "app\KANAT.exe"
}
$failed = 0

function Assert($condition, $what) {
    if ($condition) { Write-Host "ok:     $what" } else { Write-Host "FAILED: $what"; $script:failed++ }
}

function Start-Programs {
    $started = [ordered]@{}
    foreach ($name in $programs.Keys) {
        $exe = Join-Path $root $programs[$name]
        New-Item -ItemType Directory -Force -Path (Split-Path $exe) | Out-Null
        Copy-Item (Join-Path $env:SystemRoot "System32\cmd.exe") $exe
        $started[$name] = Start-Process $exe -ArgumentList "/c", "ping -n 120 127.0.0.1 >nul" -WindowStyle Hidden -PassThru
    }
    Start-Sleep -Milliseconds 700
    return $started
}

function Running($process) { return [bool](Get-Process -Id $process.Id -ErrorAction SilentlyContinue) }

function Stop-All($started) {
    foreach ($p in $started.Values) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
}

try {
    # A launcher asks for its own folder: the other components keep running
    $p = Start-Programs
    Stop-KanatProcesses $root -Only "backend"
    Assert (-not (Running $p.backend)) "-Only backend ends the backend"
    Assert ((Running $p.mediamtx) -and (Running $p.detection) -and (Running $p.app)) "-Only backend leaves MediaMTX, detection and the app running"
    Stop-All $p

    $p = Start-Programs
    Stop-KanatProcesses $root -Only "video"
    Assert (-not (Running $p.mediamtx)) "-Only video ends MediaMTX"
    Assert ((Running $p.backend) -and (Running $p.detection) -and (Running $p.app)) "-Only video leaves the backend, detection and the app running"
    Stop-All $p

    $p = Start-Programs
    Stop-KanatProcesses $root -Only "detection"
    Assert (-not (Running $p.detection)) "-Only detection ends detection"
    Assert ((Running $p.mediamtx) -and (Running $p.backend) -and (Running $p.app)) "-Only detection leaves MediaMTX, the backend and the app running"
    Stop-All $p

    # The installer asks for the whole install, the app aside
    $p = Start-Programs
    Stop-KanatProcesses $root
    Assert (-not ((Running $p.mediamtx) -or (Running $p.backend) -or (Running $p.detection))) "no -Only ends all three services"
    Assert (Running $p.app) "no -Only leaves the app running"
    Stop-All $p

    # The uninstaller asks for the app too, and a root written with a trailing backslash is the same root
    $p = Start-Programs
    Stop-KanatProcesses ($root + "\") -IncludeApp
    Assert (-not ((Running $p.mediamtx) -or (Running $p.backend) -or (Running $p.detection) -or (Running $p.app))) "-IncludeApp ends everything, the root with a trailing backslash too"
    Stop-All $p

    # Nothing outside the install folder is touched
    $other = Start-Process (Join-Path $env:SystemRoot "System32\cmd.exe") -ArgumentList "/c", "ping -n 120 127.0.0.1 >nul" -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 300
    Stop-KanatProcesses $root -IncludeApp
    Assert (Running $other) "a process outside the install folder is left alone"
    Stop-Process -Id $other.Id -Force -ErrorAction SilentlyContinue
}
finally {
    Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 300
    Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
}

if ($failed -gt 0) { Write-Host "$failed check(s) FAILED"; exit 1 }
Write-Host "all checks passed"
