<#
.SYNOPSIS
  Sets KANAT up on this PC, once the installer has copied its files: the
  app's settings, the firewall, the cameras' network adapter, power, and the
  three background tasks (MediaMTX, the backend, the Detection Service), which
  it starts. Run by the installer as Administrator; safe to run again.

.PARAMETER InstallDir
  Where KANAT's files are (the installer's folder, C:\Program Files\KANAT).

.PARAMETER RunMode
  threads    every camera's Run is a thread of one Detection Service process,
             sharing one model
  processes  every camera's Run is a process of its own, with its own model
             (about 4 times the memory)

.PARAMETER CameraAdapter
  The network adapter the cameras are on (Get-NetAdapter shows the names).
  It is set to the Private network profile and given the route for multicast
  (224.0.0.0/4). Empty: Windows picks the adapter for multicast.
#>
param(
    [Parameter(Mandatory)][string]$InstallDir,
    [ValidateSet("threads", "processes")][string]$RunMode = "threads",
    [string]$CameraAdapter = ""
)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\kanat-common.ps1"

# The engineer password that unlocks the app's Logs tab, as scrypt "salt:hash"
# (checked in the app's main process; only the hash is here, never the
# password). Generate from another password with:
#   node -e "const{scryptSync,randomBytes}=require('crypto');const s=randomBytes(16);process.stdout.write(s.toString('hex')+':'+scryptSync(process.argv[1],s,64).toString('hex'))" "YOUR-PASSWORD"
# Current password: admin
$LogsPasswordHash = "4f8b078dd5c79e0b9e81ce3f03a0a52e:d3f16ba48a0a9800a902710d9c3fef795f837beb5d49a52a22cfca2618aecceaf4c5b4c9249a08819bbe4bfd998caf8f9c16574b0bfd60b9ed76e35857af5f41"

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "    $text" -ForegroundColor Green }
function Note($text) { Write-Host "    $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host ""; Write-Host "FAILED: $text" -ForegroundColor Red; exit 1 }

New-Item -ItemType Directory -Force -Path $KanatLogDir | Out-Null
Start-Transcript -Path (Join-Path $KanatLogDir "installer.log") -Append | Out-Null

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "run this as Administrator (right-click, Run as administrator)"
}
foreach ($file in @("video\mediamtx.exe", "video\mediamtx.yml", "backend\python\python.exe", "detection\python\python.exe",
                    "scripts\run.ps1", "app\KANAT.exe")) {
    if (-not (Test-Path (Join-Path $InstallDir $file))) { Fail "$file is missing from $InstallDir (run the installer again)" }
}

# --- 1. Settings: the app's kanat-config.json --------------------------------

Step "Settings"
# The folder is written by the services (as SYSTEM) and read by the app (as the operator)
& icacls.exe $KanatLogDir /grant "*S-1-5-32-545:(OI)(CI)M" /T /Q | Out-Null   # BUILTIN\Users: modify
$config = [ordered]@{ logDir = $KanatLogDir; logsPasswordHash = $LogsPasswordHash }
Write-Utf8 (Join-Path $KanatDataDir "kanat-config.json") ($config | ConvertTo-Json -Depth 20)
Ok "kanat-config.json written for every user; logs in $KanatLogDir"

# --- 2. The network for the cameras -----------------------------------------

Step "Network: firewall and the cameras' adapter"
# MediaMTX receives the cameras' RTP multicast directly (backend camera_sync.py):
# its inbound UDP is allowed, which Windows would otherwise ask about in a window
# nobody sees, and block
$mediamtx = Join-Path $InstallDir "video\mediamtx.exe"
Get-NetFirewallRule -DisplayName "KANAT MediaMTX camera video" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "KANAT MediaMTX camera video" -Direction Inbound -Action Allow `
    -Program $mediamtx -Protocol UDP -Profile Domain, Private, Public | Out-Null
# Its TCP service ports (RTSP, the control API) stay off the network: the app,
# the backend and the Detection Service all reach them on 127.0.0.1
Get-NetFirewallRule -DisplayName "KANAT MediaMTX local only" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "KANAT MediaMTX local only" -Direction Inbound -Action Block `
    -Program $mediamtx -Protocol TCP -Profile Domain, Private, Public | Out-Null
Ok "firewall rules set"

if ($CameraAdapter) {
    $adapter = Get-NetAdapter -Name $CameraAdapter -ErrorAction SilentlyContinue
    if (-not $adapter) { Fail "no network adapter named '$CameraAdapter' (Get-NetAdapter shows the names)" }
    Set-NetConnectionProfile -InterfaceIndex $adapter.ifIndex -NetworkCategory Private -ErrorAction SilentlyContinue
    # The route in both stores: the persistent one applies from the next boot
    # only, the active one now. Windows already has an on-link 224.0.0.0/4
    # route on each adapter, so the active one is that route given metric 1
    Get-NetRoute -DestinationPrefix "224.0.0.0/4" -PolicyStore PersistentStore -ErrorAction SilentlyContinue | Remove-NetRoute -Confirm:$false
    New-NetRoute -DestinationPrefix "224.0.0.0/4" -InterfaceIndex $adapter.ifIndex -RouteMetric 1 `
        -PolicyStore PersistentStore -ErrorAction SilentlyContinue | Out-Null
    $active = Get-NetRoute -DestinationPrefix "224.0.0.0/4" -InterfaceIndex $adapter.ifIndex -PolicyStore ActiveStore -ErrorAction SilentlyContinue
    if ($active) {
        $active | Set-NetRoute -RouteMetric 1 -ErrorAction SilentlyContinue
    } else {
        New-NetRoute -DestinationPrefix "224.0.0.0/4" -InterfaceIndex $adapter.ifIndex -RouteMetric 1 `
            -PolicyStore ActiveStore -ErrorAction SilentlyContinue | Out-Null
    }
    $persistent = Get-NetRoute -DestinationPrefix "224.0.0.0/4" -InterfaceIndex $adapter.ifIndex -PolicyStore PersistentStore -ErrorAction SilentlyContinue
    $active = Get-NetRoute -DestinationPrefix "224.0.0.0/4" -InterfaceIndex $adapter.ifIndex -PolicyStore ActiveStore -ErrorAction SilentlyContinue |
        Where-Object RouteMetric -eq 1
    if (-not $persistent -or -not $active) {
        Fail "could not route multicast to '$CameraAdapter' (persistent: $([bool]$persistent), now: $([bool]$active)); run as Administrator: route -p add 224.0.0.0 mask 240.0.0.0 <this adapter's IPv4 address> metric 1"
    }
    Ok "'$CameraAdapter' is Private, and multicast joins on it"
} else {
    Note "no camera adapter given: Windows picks the adapter for multicast"
}

# --- 3. Never sleep ---------------------------------------------------------

Step "Power: the PC never sleeps"
& powercfg.exe /change standby-timeout-ac 0
& powercfg.exe /change hibernate-timeout-ac 0
& powercfg.exe /hibernate off
Ok "sleep and hibernation off"

# --- 4. The background tasks ------------------------------------------------

Step "The background tasks (MediaMTX, backend, Detection Service: $RunMode)"
# Stopped first, so an update replaces what is running
foreach ($name in $KanatTasks) {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
Stop-KanatProcesses $InstallDir

$run = Join-Path $InstallDir "scripts\run.ps1"
$components = [ordered]@{
    "KANAT MediaMTX"  = "-Component mediamtx"
    "KANAT Backend"   = "-Component backend"
    "KANAT Detection" = "-Component detection -RunMode $RunMode"
}
# At startup, as SYSTEM: they run with no one logged in, and come back by
# themselves after a power cut. run.ps1 starts a component again if it exits;
# the task's own restart covers run.ps1 itself.
$taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -Hidden
foreach ($name in $components.Keys) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $InstallDir `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$run`" $($components[$name])"
    Register-ScheduledTask -TaskName $name -Action $action -Trigger (New-ScheduledTaskTrigger -AtStartup) `
        -Principal $taskPrincipal -Settings $taskSettings | Out-Null
    Start-ScheduledTask -TaskName $name
    Ok "$name registered and started"
}

# --- 5. Check ----------------------------------------------------------------

Step "Checking"
$deadline = (Get-Date).AddMinutes(3)
$status = $null
do {
    Start-Sleep -Seconds 5
    try { $status = Invoke-RestMethod -Uri "http://127.0.0.1:8000/status" -TimeoutSec 5 } catch { $status = $null }
} until (($status -and $status.video_service -and $status.detection_service) -or (Get-Date) -gt $deadline)
if (-not $status) {
    Fail "the backend does not answer on http://127.0.0.1:8000: see $KanatLogDir\backend.err.log and launcher.log"
}
if ($status.video_service) { Ok "backend: up; MediaMTX: up" } else { Note "backend: up; MediaMTX: not answering (task 'KANAT MediaMTX', see launcher.log)" }
if ($status.detection_service) { Ok "Detection Service: up ($RunMode)" } else { Note "Detection Service: not answering yet (it loads its model first; see detection.log)" }

Write-Host ""
Write-Host "KANAT is installed. Open KANAT from the desktop, and add the cameras in Settings." -ForegroundColor Green
Write-Host "  - Logs: $KanatLogDir, and in the app's Logs tab."
Write-Host "  - For the range to come back by itself after a power cut, Windows must log in"
Write-Host "    the operator automatically: run netplwiz, select the user, and clear"
Write-Host "    'Users must enter a user name and password to use this computer'."
Stop-Transcript | Out-Null
