[CmdletBinding(SupportsShouldProcess)]
param([switch]$Remove, [switch]$ValidateOnly)

$ErrorActionPreference = 'Stop'
$RepoRoot = 'C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트'
$Launcher = Join-Path $RepoRoot 'ops\r3\run_r3_v8_guardian.ps1'
$Startup = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $Startup 'R3-Prospective-Scientific-v8.lnk'

if (-not (Test-Path -LiteralPath $Launcher)) { Write-Error "launcher is missing: $Launcher"; exit 20 }
if ($Remove) {
    if ($PSCmdlet.ShouldProcess($ShortcutPath, 'Remove R3 v8 startup shortcut')) { Remove-Item -LiteralPath $ShortcutPath -Force -ErrorAction SilentlyContinue }
    exit 0
}

$shell = New-Object -ComObject WScript.Shell
if ($ValidateOnly) {
    if (-not (Test-Path -LiteralPath $ShortcutPath)) { Write-Error "startup shortcut is missing: $ShortcutPath"; exit 21 }
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $valid = ($shortcut.TargetPath -ieq (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')) -and ($shortcut.Arguments -like "*-File*run_r3_v8_guardian.ps1*") -and ($shortcut.Arguments -like "*-Persistent*") -and ($shortcut.Arguments -like "*-PollSeconds 300*") -and ($shortcut.WorkingDirectory -ieq $RepoRoot)
    [pscustomobject]@{Shortcut=$ShortcutPath;TargetPath=$shortcut.TargetPath;Arguments=$shortcut.Arguments;WorkingDirectory=$shortcut.WorkingDirectory;Valid=$valid;CredentialsCommitted=$false}
    if (-not $valid) { exit 22 }
    exit 0
}

if ($PSCmdlet.ShouldProcess($ShortcutPath, 'Install R3 v8 startup shortcut')) {
    New-Item -ItemType Directory -Path $Startup -Force | Out-Null
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $Launcher + '" -Persistent -PollSeconds 300'
    $shortcut.WorkingDirectory = $RepoRoot
    $shortcut.WindowStyle = 7
    $shortcut.Description = 'R3 v8 outcome-blind guardian (sealed identity; authorization-gated resume)'
    $shortcut.Save()
    & $PSCommandPath -ValidateOnly
}
