<#
.SYNOPSIS
  Installs KANAT on an offline Windows 10/11 PC from the bundle this script
  sits in (build-bundle.sh): Docker Desktop with WSL 2, GStreamer, MediaMTX,
  the WebApp's containers and the KANAT app.

.DESCRIPTION
  Run it as Administrator, as the Windows user that will operate the range
  (Docker Desktop and MediaMTX start when that user logs in):

    powershell -ExecutionPolicy Bypass -File .\install.ps1 -CameraInterface "Ethernet 2"

  It can be run again at any time: each step checks what is already there.
  The first run on a PC without WSL turns it on and asks for a restart; run
  it again after the restart. Running it from a newer bundle updates KANAT,
  keeping its database and recordings.

  The SQLite database (on a Docker volume) starts empty: the bundle carries no data.

.PARAMETER CameraInterface
  The network adapter the cameras are on (Get-NetAdapter shows the names). It
  is set to the Private network profile and given the route for multicast
  (224.0.0.0/4). Asked for when the PC has several adapters and it is not
  given; leave it out on a PC with one.

.PARAMETER InstallDir
  Where KANAT's files go (default C:\Kanat): WebApp\ (the containers'
  configuration) and VideoService\ (MediaMTX, its recordings).

.PARAMETER TimeZone
  The PC's time zone as an IANA name (default Asia/Jerusalem): MediaMTX names
  its recordings in local time, which the backend's container reads.

.PARAMETER CpuOnly
  Run the Detection Service on the CPU even if an NVIDIA GPU is usable.
#>
param(
    [string]$CameraInterface = "",
    [string]$InstallDir = "C:\Kanat",
    [string]$TimeZone = "Asia/Jerusalem",
    [switch]$CpuOnly
)

$Bundle = $PSScriptRoot
$DataDir = Join-Path $env:ProgramData "Kanat"
$LogDir = Join-Path $DataDir "logs"
$WebAppDir = Join-Path $InstallDir "WebApp"
$VideoDir = Join-Path $InstallDir "VideoService"
$Version = (Get-Content (Join-Path $Bundle "VERSION") -Raw).Trim()

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "    $text" -ForegroundColor Green }
function Note($text) { Write-Host "    $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host ""; Write-Host "FAILED: $text" -ForegroundColor Red; exit 1 }
# Windows PowerShell's -Encoding UTF8 starts the file with a byte order mark,
# which Docker Desktop's and the app's JSON readers refuse
function Write-Utf8($path, $text) { [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $false)) }

# A native program's exit code, failing the install on anything but 0 (and
# the codes in $Allowed, e.g. 3010: done, restart needed)
function Run($file, $arguments, [int[]]$Allowed = @()) {
    $p = Start-Process -FilePath $file -ArgumentList $arguments -Wait -PassThru
    if ($p.ExitCode -ne 0 -and $Allowed -notcontains $p.ExitCode) {
        Fail "$file $arguments exited with $($p.ExitCode)"
    }
    return $p.ExitCode
}

# --- checks ----------------------------------------------------------------

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "run this script as Administrator (right-click PowerShell, Run as administrator)"
}
$build = [int](Get-CimInstance Win32_OperatingSystem).BuildNumber
if ($build -lt 19045) {
    Fail "Windows build ${build}: Docker Desktop needs Windows 10 22H2 (build 19045) or Windows 11"
}
$freeGb = [math]::Floor((Get-PSDrive C).Free / 1GB)
if ($freeGb -lt 30) {
    Fail "C: has $freeGb GB free: Docker and KANAT's images need 30 GB"
}
# Docker Desktop needs the Server service (file sharing to its VM) running
Set-Service -Name LanmanServer -StartupType Automatic
Start-Service -Name LanmanServer -ErrorAction SilentlyContinue
Write-Host "KANAT ${Version}: installing into $InstallDir for user $env:USERNAME"

# --- 1. WSL 2 --------------------------------------------------------------

Step "WSL 2 (Docker Desktop runs its containers in it)"
$restart = $false
foreach ($feature in @("Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform")) {
    $state = (Get-WindowsOptionalFeature -Online -FeatureName $feature).State
    if ($state -ne "Enabled") {
        $result = Enable-WindowsOptionalFeature -Online -FeatureName $feature -All -NoRestart
        if ($result.RestartNeeded) { $restart = $true }
        Ok "$feature turned on"
    } else {
        Ok "$feature already on"
    }
}
$wslMsi = Get-ChildItem (Join-Path $Bundle "installers") -Filter "wsl.*.x64.msi" | Select-Object -First 1
$wslVersion = $null
# wsl.exe writes UTF-16 unless told otherwise
$env:WSL_UTF8 = "1"
try { $wslVersion = (& wsl.exe --version 2>$null | Select-Object -First 1) } catch { $wslVersion = $null }   # no wsl.exe at all
if (-not ($wslVersion -match "\d+\.\d+\.\d+")) {
    # The inbox wsl.exe of Windows 10 has no --version: the packaged WSL is not installed
    Run "msiexec.exe" "/i `"$($wslMsi.FullName)`" /qn /norestart" -Allowed 3010 | Out-Null
    $restart = $true
    Ok "WSL installed from $($wslMsi.Name)"
} else {
    Ok "WSL already installed: $wslVersion"
}
if ($restart) {
    Note "Windows must restart to finish turning WSL on."
    Note "Restart, log in as $env:USERNAME, and run this script again."
    exit 0
}

# --- 2. Docker Desktop -----------------------------------------------------

Step "Docker Desktop"
# Where Docker Desktop's installer puts it: Docker\Docker in older versions,
# Docker in newer ones (4.94 on Windows 10)
function Find-DockerDesktop {
    @("Docker\Docker Desktop.exe", "Docker\Docker\Docker Desktop.exe") |
        ForEach-Object { Join-Path $env:ProgramFiles $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
}
$dockerExe = Find-DockerDesktop
if (-not $dockerExe) {
    $installer = Join-Path $Bundle "installers\Docker Desktop Installer.exe"
    Run $installer "install --quiet --accept-license --backend=wsl-2 --always-run-service" | Out-Null
    $dockerExe = Find-DockerDesktop
    if (-not $dockerExe) { Fail "Docker Desktop's installer finished, but Docker Desktop.exe is not in $env:ProgramFiles\Docker" }
    Ok "installed: $dockerExe"
} else {
    Ok "already installed: $dockerExe"
}
# Lets this user use Docker without being an administrator
& net.exe localgroup docker-users $env:USERNAME /add 2>$null | Out-Null
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

# Started with Windows (when this user logs in), without its welcome screens
$settingsFile = Join-Path $env:APPDATA "Docker\settings-store.json"
New-Item -ItemType Directory -Force -Path (Split-Path $settingsFile) | Out-Null
$settings = @{}
if (Test-Path $settingsFile) {
    $json = Get-Content $settingsFile -Raw | ConvertFrom-Json
    $json.PSObject.Properties | ForEach-Object { $settings[$_.Name] = $_.Value }
}
$settings["AutoStart"] = $true
$settings["DisplayedOnboarding"] = $true
$settings["OpenUIOnStartupDisabled"] = $true
# The PC is offline: no update checks or usage reports
$settings["AutoDownloadUpdates"] = $false
$settings["AnalyticsEnabled"] = $false
Write-Utf8 $settingsFile ($settings | ConvertTo-Json -Depth 20)
# The login entry Docker Desktop makes for AutoStart, made here too, in case
# it only applies the setting once its window has been opened
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Docker Desktop" -Value "`"$dockerExe`" -Autostart"
Ok "starts when $env:USERNAME logs in"

if (-not (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue)) {
    Start-Process $dockerExe
}
Write-Host "    waiting for Docker to start (a few minutes the first time)..."
$deadline = (Get-Date).AddMinutes(10)
do {
    Start-Sleep -Seconds 5
    & docker.exe info *> $null
    $up = ($LASTEXITCODE -eq 0)
} until ($up -or (Get-Date) -gt $deadline)
if (-not $up) {
    Fail "Docker did not start within 10 minutes. Open Docker Desktop to see why (virtualization off in the BIOS is the usual cause), then run this script again"
}
Ok "running"

# --- 3. GStreamer ----------------------------------------------------------

Step "GStreamer (joins each camera's multicast for MediaMTX)"
function Find-Gst {
    $root = [Environment]::GetEnvironmentVariable("GSTREAMER_1_0_ROOT_MSVC_X86_64", "Machine")
    foreach ($dir in @($root, "$env:ProgramFiles\gstreamer\1.0\msvc_x86_64") | Where-Object { $_ }) {
        $exe = Join-Path $dir "bin\gst-launch-1.0.exe"
        if (Test-Path $exe) { return $exe }
    }
    return $null
}
$gst = Find-Gst
if (-not $gst) {
    $installer = Get-ChildItem (Join-Path $Bundle "installers") -Filter "gstreamer-1.0-msvc-x86_64-*.exe" | Select-Object -First 1
    # Its runtime only, with the Visual C++ runtime it embeds, for all users
    Run $installer.FullName "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /ALLUSERS /TYPE=runtime" | Out-Null
    $gst = Find-Gst
    if (-not $gst) { Fail "GStreamer installed, but gst-launch-1.0.exe was not found" }
    Ok "installed"
} else {
    Ok "already installed"
}
$gstBin = Split-Path $gst
$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if (($machinePath -split ";") -notcontains $gstBin) {
    [Environment]::SetEnvironmentVariable("Path", "$machinePath;$gstBin", "Machine")
    Ok "added to PATH: $gstBin"
}
$env:Path += ";$gstBin"
& $gst --version | Select-Object -First 1 | ForEach-Object { Ok $_ }
$inspect = Join-Path $gstBin "gst-inspect-1.0.exe"
foreach ($element in @("udpsrc", "rtpjitterbuffer", "rtph264depay", "h264parse", "rtspclientsink")) {
    & $inspect $element *> $null
    if ($LASTEXITCODE -ne 0) { Fail "GStreamer has no ${element}: reinstall it with every runtime component" }
}
Ok "has every element the cameras need"

# --- 4. KANAT's files -------------------------------------------------------

Step "KANAT's files in $InstallDir"
New-Item -ItemType Directory -Force -Path $WebAppDir, $VideoDir, $LogDir | Out-Null
# The configuration is replaced by the bundle's; .env, the recordings and the
# replay cache stay
Copy-Item -Recurse -Force (Join-Path $Bundle "app\WebApp\*") $WebAppDir
Get-Process mediamtx -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
Copy-Item -Recurse -Force (Join-Path $Bundle "app\VideoService\*") $VideoDir
New-Item -ItemType Directory -Force -Path (Join-Path $VideoDir "recordings"), (Join-Path $VideoDir "replay-cache") | Out-Null
# The log folder is written by the app as this user, and by the containers
& icacls.exe $LogDir /grant "*S-1-5-32-545:(OI)(CI)M" /T /Q | Out-Null   # BUILTIN\Users: modify
Ok "copied; logs in $LogDir"

# --- 5. Settings: .env and kanat-config.json --------------------------------

Step "Settings"
$envFile = Join-Path $WebAppDir ".env"
$values = [ordered]@{}
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match "^\s*([A-Z_]+)=(.*)$") { $values[$Matches[1]] = $Matches[2] }
    }
}
$values["COMPOSE_PROFILES"] = "app"
$values["KANAT_VERSION"] = $Version
$values["KANAT_LOG_DIR"] = $LogDir
$values["RECORD_LAUNCHER"] = "powershell"
$values["KANAT_TZ"] = $TimeZone
$values.Keys | ForEach-Object { "$_=$($values[$_])" } | Set-Content -Path $envFile -Encoding ASCII
Ok ".env written"

$appConfig = Join-Path $DataDir "kanat-config.json"
$config = [ordered]@{ logDir = $LogDir }
# The engineer password that unlocks the app's Logs tab, as scrypt "salt:hash"
# (checked in the app's main process; only the hash is here, never the password).
# Leave empty to keep the Logs tab open. Generate from your chosen password with:
#   node -e "const{scryptSync,randomBytes}=require('crypto');const s=randomBytes(16);process.stdout.write(s.toString('hex')+':'+scryptSync(process.argv[1],s,64).toString('hex'))" "YOUR-PASSWORD"
# Current password: admin
$LogsPasswordHash = "4f8b078dd5c79e0b9e81ce3f03a0a52e:d3f16ba48a0a9800a902710d9c3fef795f837beb5d49a52a22cfca2618aecceaf4c5b4c9249a08819bbe4bfd998caf8f9c16574b0bfd60b9ed76e35857af5f41"
if ($LogsPasswordHash) { $config["logsPasswordHash"] = $LogsPasswordHash }
Write-Utf8 $appConfig ($config | ConvertTo-Json)
Ok "kanat-config.json written for every user"

# --- 6. The network for the cameras -----------------------------------------

Step "Network: firewall and the cameras' adapter"
# GStreamer receives the cameras' multicast: allowed in, which Windows would
# otherwise ask about in a window nobody sees, and block
Get-NetFirewallRule -DisplayName "KANAT GStreamer camera video" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "KANAT GStreamer camera video" -Direction Inbound -Action Allow `
    -Program $gst -Protocol UDP -Profile Domain, Private, Public | Out-Null
# MediaMTX receives the cameras' RTP multicast directly (backend camera_sync.py),
# so its inbound UDP is allowed, as GStreamer's is
Get-NetFirewallRule -DisplayName "KANAT MediaMTX camera video" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "KANAT MediaMTX camera video" -Direction Inbound -Action Allow `
    -Program (Join-Path $VideoDir "mediamtx.exe") -Protocol UDP -Profile Domain, Private, Public | Out-Null
# Its TCP service ports (RTSP, the control and playback APIs) stay off the
# network: the app and the containers reach them on 127.0.0.1 / host.docker.internal
Get-NetFirewallRule -DisplayName "KANAT MediaMTX local only" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "KANAT MediaMTX local only" -Direction Inbound -Action Block `
    -Program (Join-Path $VideoDir "mediamtx.exe") -Protocol TCP -Profile Domain, Private, Public | Out-Null
Ok "firewall rules set"

$adapters = @(Get-NetAdapter -Physical | Where-Object Status -eq "Up")
if (-not $CameraInterface -and $adapters.Count -gt 1) {
    Write-Host "    Connected adapters:"
    $adapters | ForEach-Object { Write-Host "      $($_.Name)  ($($_.InterfaceDescription))" }
    $CameraInterface = Read-Host "    Which one are the cameras on? (Enter to skip)"
}
if ($CameraInterface) {
    $adapter = Get-NetAdapter -Name $CameraInterface -ErrorAction SilentlyContinue
    if (-not $adapter) { Fail "no network adapter named '$CameraInterface'" }
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
        Fail "could not route multicast to '$CameraInterface' (persistent: $([bool]$persistent), now: $([bool]$active)); run as Administrator: route -p add 224.0.0.0 mask 240.0.0.0 <this adapter's IPv4 address> metric 1"
    }
    Ok "'$CameraInterface' is Private, and multicast joins on it"
} else {
    Note "no camera adapter given: Windows picks the adapter for multicast"
}

# --- 7. Never sleep ---------------------------------------------------------

Step "Power: the PC never sleeps"
& powercfg.exe /change standby-timeout-ac 0
& powercfg.exe /change hibernate-timeout-ac 0
& powercfg.exe /hibernate off
Ok "sleep and hibernation off"

# --- 8. The containers -----------------------------------------------------

Step "Loading the containers' images"
# The GPU image (several GB) only where an NVIDIA driver could run it
$mayUseGpu = (-not $CpuOnly) -and [bool](Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)
Get-ChildItem (Join-Path $Bundle "images") -Filter "*.tar" | Where-Object { $mayUseGpu -or $_.Name -notlike "*-cuda.tar" } | ForEach-Object {
    Write-Host "    $($_.Name)..."
    & docker.exe load -i $_.FullName | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "docker load $($_.Name)" }
}
Ok "loaded"

Step "The Detection Service: GPU or CPU"
$gpu = $false
$cudaImage = "kanat-detection:$Version-cuda"
& docker.exe image inspect $cudaImage *> $null
$hasCudaImage = ($LASTEXITCODE -eq 0)
if ($CpuOnly) {
    Note "CPU, as asked (-CpuOnly)"
} elseif (-not (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)) {
    Ok "CPU: no NVIDIA driver on this PC"
} elseif (-not $hasCudaImage) {
    Note "CPU: this bundle has no GPU image"
} else {
    # The GPU counts only if a container can use it, as the service would
    & docker.exe run --rm --gpus all --entrypoint python $cudaImage -c "import sys, torch; sys.exit(0 if torch.cuda.is_available() else 1)" *> $null
    if ($LASTEXITCODE -eq 0) {
        $gpu = $true
        Ok "GPU: $((& nvidia-smi.exe --query-gpu=name --format=csv,noheader | Select-Object -First 1))"
    } else {
        Note "CPU: an NVIDIA GPU is here, but Docker cannot use it (update its driver to use it)"
    }
}
$values["COMPOSE_FILE"] = if ($gpu) { "docker-compose.yml;docker-compose.gpu.yml" } else { "docker-compose.yml" }
$values.Keys | ForEach-Object { "$_=$($values[$_])" } | Set-Content -Path $envFile -Encoding ASCII

Step "Starting the containers"
Push-Location $WebAppDir
& docker.exe compose up -d --no-build --remove-orphans
$composeExit = $LASTEXITCODE
Pop-Location
if ($composeExit -ne 0) { Fail "docker compose up (see its output above)" }
Ok "started; Docker starts them again whenever it starts"

# --- 9. MediaMTX at login ---------------------------------------------------

Step "MediaMTX, started when $env:USERNAME logs in"
$taskName = "KANAT MediaMTX"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute (Join-Path $VideoDir "mediamtx.exe") -Argument "mediamtx.yml" -WorkingDirectory $VideoDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$taskSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $taskSettings `
    -User "$env:USERDOMAIN\$env:USERNAME" -RunLevel Limited | Out-Null
Start-ScheduledTask -TaskName $taskName
Ok "registered and started"

# --- 10. The KANAT app ------------------------------------------------------

Step "The KANAT app"
$setup = Get-ChildItem (Join-Path $Bundle "installers") -Filter "KANAT-Setup-*.exe" | Select-Object -First 1
Run $setup.FullName "/S" | Out-Null
Ok "installed (desktop and Start menu shortcut: KANAT)"

# --- 11. Check -------------------------------------------------------------

Step "Checking"
$deadline = (Get-Date).AddMinutes(3)
$status = $null
do {
    Start-Sleep -Seconds 5
    try { $status = Invoke-RestMethod -Uri "http://127.0.0.1:8000/status" -TimeoutSec 5 } catch { $status = $null }
} until (($status -and $status.video_service -and $status.detection_service) -or (Get-Date) -gt $deadline)
if (-not $status) {
    Fail "the backend does not answer on http://127.0.0.1:8000: see 'docker compose logs backend' in $WebAppDir"
}
if ($status.video_service) { Ok "backend: up; MediaMTX: up" } else { Note "backend: up; MediaMTX: not answering (Task Scheduler, task '$taskName')" }
if ($status.detection_service) { Ok "Detection Service: up ($(if ($gpu) { 'GPU' } else { 'CPU' }))" } else { Note "Detection Service: not answering yet ('docker compose logs detection')" }

Write-Host ""
Write-Host "KANAT $Version is installed." -ForegroundColor Green
Write-Host "  - Open KANAT from the desktop, and add the cameras in Settings."
Write-Host "  - Logs: $LogDir, and in the app's Logs tab."
Write-Host "  - For the range to come back by itself after a power cut, Windows must log in"
Write-Host "    $env:USERNAME automatically: run netplwiz, select the user, and clear"
Write-Host "    'Users must enter a user name and password to use this computer'."
