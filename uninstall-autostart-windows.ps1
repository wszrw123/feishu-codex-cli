[CmdletBinding()]
param(
  [string]$TaskName = "FeishuCodexCli"
)

$ErrorActionPreference = "Stop"

try {
  Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
} catch {
}

try {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
  Write-Output "scheduled task removed: $TaskName"
} catch {
  Write-Output "scheduled task not found: $TaskName"
}
