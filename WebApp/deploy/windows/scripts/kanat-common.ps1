# What the KANAT scripts share (dot-sourced: . "$PSScriptRoot\kanat-common.ps1").
# Windows PowerShell 5.1, so no PowerShell 7 syntax.

# The three things that run in the background, each its own scheduled task
$KanatTasks = @("KANAT MediaMTX", "KANAT Backend", "KANAT Detection")

# Logs, the database and kanat-config.json: kept when KANAT is updated or uninstalled
$KanatDataDir = Join-Path $env:ProgramData "Kanat"
$KanatLogDir = Join-Path $KanatDataDir "logs"

# Writes a file as UTF-8 without a byte order mark: Windows PowerShell's
# -Encoding UTF8 adds one, which the app's JSON reader refuses
function Write-Utf8($path, $text) {
    [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $false))
}

# Ends every process that runs from KANAT's install folder: both Python
# environments (the backend, the Detection Service, its supervisor and every
# Run's process) and MediaMTX. The app (KANAT.exe) too, with -IncludeApp.
# Asked for by path, so nothing of the PC's own (another Python, another
# MediaMTX) is touched.
function Stop-KanatProcesses([string]$Root, [switch]$IncludeApp) {
    $prefix = $Root.TrimEnd('\') + '\'
    $appPrefix = $prefix + 'app\'
    $found = @(Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -and
        ($IncludeApp -or -not $_.ExecutablePath.StartsWith($appPrefix, [StringComparison]::OrdinalIgnoreCase))
    })
    foreach ($p in $found) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    # They are gone, or about to be: a file in use blocks the installer's copy
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        $left = @($found | Where-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
        if ($left.Count -eq 0) { return }
        Start-Sleep -Milliseconds 300
    }
}
