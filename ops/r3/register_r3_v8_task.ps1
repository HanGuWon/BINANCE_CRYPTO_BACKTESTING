[CmdletBinding(SupportsShouldProcess)]
param([switch]$ValidateOnly)

$ErrorActionPreference = 'Stop'
$TaskName = 'R3-Prospective-Scientific-v8'
$RepoRoot = 'C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트'
$Python = 'C:\Users\user\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe'
$OpsScript = Join-Path $RepoRoot 'ops\r3\r3_ops.py'
$Launcher = Join-Path $RepoRoot 'ops\r3\launch_r3_v8_resume.ps1'
$DependencySite = 'C:\Users\user\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages'
$ScientificRoot = 'D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8'
$Roster = Join-Path $RepoRoot 'campaigns\r3_prospective_context_v1\rosters\2026-09.json'
$LaunchManifest = 'D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json'
$LaunchSeal = 'D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json'

foreach ($required in @($Python, $OpsScript, $Launcher, $ScientificRoot, $Roster, $LaunchManifest, $LaunchSeal)) {
    if (-not (Test-Path -LiteralPath $required)) { Write-Error "required v8 path is missing: $required"; exit 20 }
}

$env:PYTHONPATH = $DependencySite
Push-Location -LiteralPath $RepoRoot
try {
    & $Python $OpsScript verify --exact-v8 --root $ScientificRoot --roster $Roster --manifest $LaunchManifest --seal $LaunchSeal
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + $Launcher + '"') -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    if ($ValidateOnly) {
        [pscustomobject]@{TaskName=$TaskName; Trigger='AtLogOn'; MultipleInstancesPolicy='IgnoreNew'; RestartCount=3; RestartInterval='PT1M'; Launcher=$Launcher; ScientificRoot=$ScientificRoot; CredentialsCommitted=$false}
        exit 0
    }
    if ($PSCmdlet.ShouldProcess($TaskName, 'Register or update v8 Task Scheduler task')) {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
        $task = Get-ScheduledTask -TaskName $TaskName
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        [pscustomobject]@{TaskName=$task.TaskName; State=$task.State; LastTaskResult=$info.LastTaskResult; Trigger='AtLogOn'; MultipleInstancesPolicy='IgnoreNew'; RestartCount=3; RestartInterval='PT1M'; Launcher=$Launcher; CredentialsCommitted=$false}
    }
}
finally { Pop-Location }
