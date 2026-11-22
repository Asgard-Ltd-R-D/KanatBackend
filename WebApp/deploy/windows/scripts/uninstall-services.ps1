<#
.SYNOPSIS
  Stops KANAT and takes out what install-services.ps1 put in the PC: the three
  background tasks and the firewall rules. Run by the uninstaller (and by the
  installer, with -StopOnly, before it replaces KANAT's files).

  Kept: the database, the logs and kanat-config.json in C:\ProgramData\Kanat
  (delete the folder by hand to remove them), and the multicast route and
  power settings, which belong to the PC.
#>
param(
    [Parameter(Mandatory)][string]$InstallDir,
    [switch]$StopOnly
)
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\kanat-common.ps1"

foreach ($name in $KanatTasks) {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $StopOnly) { Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue }
}
Stop-KanatProcesses $InstallDir -IncludeApp

if (-not $StopOnly) {
    foreach ($rule in @("KANAT MediaMTX camera video", "KANAT MediaMTX local only")) {
        Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    }
}
exit 0
