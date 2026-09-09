[CmdletBinding()]
param([switch]$ValidateOnly)

$ErrorActionPreference = 'Stop'
$TaskName = 'R3-v8-Guardian-Supervisor'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = 'C:\Users\user\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe'
$Supervisor = Join-Path $RepoRoot 'ops\r3\ensure_r3_v8_guardian.py'
$ActionArgs = ('"{0}" --once' -f $Supervisor)
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$Action = New-ScheduledTaskAction -Execute $Python -Argument $ActionArgs -WorkingDirectory $RepoRoot
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited

$summary = [ordered]@{
  task_name = $TaskName
  action = @{ execute = $Python; arguments = $ActionArgs; working_directory = $RepoRoot }
  trigger = @{ cadence_minutes = 5; repetition = '3650 days'; start_offset_minutes = 1 }
  settings = @{ multiple_instances = 'IgnoreNew'; start_when_available = $true; execution_time_limit_seconds = 0 }
  principal = @{ user = $Principal.UserId; logon_type = 'Interactive'; run_level = 'Limited'; credentials_supplied = $false }
  validate_only = [bool]$ValidateOnly
}
if ($ValidateOnly) {
  $summary | ConvertTo-Json -Depth 6
  exit 0
}
try {
  Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
  $task = Get-ScheduledTask -TaskName $TaskName
  $info = Get-ScheduledTaskInfo -TaskName $TaskName
  $summary.registered = $true
  $summary.task_state = [string]$task.State
  $summary.next_run_time = $info.NextRunTime
  $summary.registration_error = $null
  $summary | ConvertTo-Json -Depth 6
  exit 0
} catch {
  $summary.registered = $false
  $summary.task_state = $null
  $summary.registration_error = "$($_.Exception.GetType().Name): $($_.Exception.Message)"
  if ($_.Exception.Message -match 'Access is denied|denied|0x80070005') {
    $summary.disposition = 'TASK_SCHEDULER_REGISTRATION_BLOCKED_PERMISSION'
  } else {
    $summary.disposition = 'TASK_SCHEDULER_REGISTRATION_ERROR'
  }
  $summary | ConvertTo-Json -Depth 6
  exit 1
}