# run_record.sh for MediaMTX on Windows: joins a camera's multicast group and
# publishes its H.264 to MediaMTX as RTSP, restarting GStreamer when it stops.
#
# The WebApp backend sets it as each camera path's runOnInit
# (WebApp/backend/app/services/camera_sync.py, RECORD_LAUNCHER=powershell):
#   powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ./run_record.ps1
#     -McastIp "226.226.226.112" -McastPort "112" -RtspUrl "rtsp://127.0.0.1:${RTSP_PORT}/cam1"
#
# MediaMTX runs it in a job object that closes with MediaMTX, so stopping the
# path, or MediaMTX stopping or dying, stops GStreamer too: unlike
# run_record.sh, it does not watch its parent itself.
#
# -Iface is passed to udpsrc's multicast-iface, which GStreamer on Windows
# does not reliably match by name: give the camera network a route for
# 224.0.0.0/4 instead (route -p add 224.0.0.0 mask 240.0.0.0 <camera NIC IP>)
# and leave -Iface out.
param(
    [string]$McastIp = $(if ($env:MCAST_IP_ENV) { $env:MCAST_IP_ENV } else { "226.226.226.112" }),
    [string]$McastPort = $(if ($env:MCAST_PORT_ENV) { $env:MCAST_PORT_ENV } else { "112" }),
    [string]$RtspUrl = "",
    [string]$Iface = $env:IFACE_ENV
)

if (-not $RtspUrl) {
    $port = if ($env:RTSP_PORT) { $env:RTSP_PORT } else { "8554" }
    $path = if ($env:MTX_PATH) { $env:MTX_PATH } else { "hello" }
    $RtspUrl = "rtsp://127.0.0.1:$port/$path"
}

# GStreamer: on PATH, else where its MSVC installer puts it
$gst = (Get-Command gst-launch-1.0.exe -ErrorAction SilentlyContinue).Source
if (-not $gst) {
    $roots = @($env:GSTREAMER_1_0_ROOT_MSVC_X86_64, "C:\Program Files\gstreamer\1.0\msvc_x86_64") | Where-Object { $_ }
    $gst = $roots | ForEach-Object { Join-Path $_ "bin\gst-launch-1.0.exe" } | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $gst) {
    [Console]::Error.WriteLine("gst-launch-1.0.exe was not found: install GStreamer (MSVC 64-bit, Complete) and add its bin folder to PATH")
    exit 1
}

# One argument each, quoted: PowerShell would read the caps' commas as a list
$udpsrc = @("udpsrc", "address=$McastIp", "port=$McastPort", "auto-multicast=true")
if ($Iface) { $udpsrc += "multicast-iface=$Iface" }
$pipeline = @("-e") + $udpsrc + @(
    "!", "application/x-rtp,media=video,encoding-name=H264",
    "!", "rtpjitterbuffer", "latency=0", "drop-on-latency=true",
    "!", "rtph264depay",
    "!", "h264parse",
    "!", "rtspclientsink", "location=$RtspUrl", "protocols=tcp"
)

Write-Output "Using GStreamer: $gst"
Write-Output "Multicast source: udp://${McastIp}:$McastPort"
Write-Output "RTSP destination: $RtspUrl"
Write-Output ("Multicast interface: " + $(if ($Iface) { $Iface } else { "automatic (the route for 224.0.0.0/4)" }))

# Between GStreamer restarts, so a camera that keeps failing does not flood the log
$restartPauseS = 2
while ($true) {
    & $gst @pipeline
    if ($LASTEXITCODE -ne 0) {
        [Console]::Error.WriteLine("GStreamer stopped with an error ($LASTEXITCODE). Restarting...")
    }
    Start-Sleep -Seconds $restartPauseS
}
