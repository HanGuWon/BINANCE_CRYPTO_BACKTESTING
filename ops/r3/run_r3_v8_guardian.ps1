[CmdletBinding()]
param(
    [switch]$Once,
    [switch]$Persistent,
    [int]$PollSeconds = 300,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = 'C:\Users\user\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe'
$Guardian = Join-Path $RepoRoot 'ops\r3\r3_v8_guardian.py'
$env:PYTHONPATH = 'C:\Users\user\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages'

foreach ($required in @($Python, $Guardian, $RepoRoot)) {
    if (-not (Test-Path -LiteralPath $required)) { Write-Error "required guardian path is missing: $required"; exit 20 }
}

if ($ValidateOnly) {
    [pscustomobject]@{
        Guardian = $Guardian
        Python = $Python
        WorkingDirectory = $RepoRoot
        DefaultPollSeconds = 300
        PersistentSupported = $true
        StandingPolicy = Join-Path $RepoRoot 'campaigns\r3_prospective_context_v1\operations\R3_V8_STANDING_RECOVERY_AUTHORIZATION_20260907.json'
        AuthorizationMode = 'guardian-minted single-use child only'
        OutcomeBlind = $true
        Valid = $true
    }
    exit 0
}

if (-not $Once -and -not $Persistent) { $Persistent = $true }
if ($Once -and $Persistent) { Write-Error 'choose exactly one of -Once or -Persistent'; exit 21 }

$guardianArgs = @('-m', 'ops.r3.r3_v8_guardian')
if ($Once) { $guardianArgs += '--once' } else { $guardianArgs += '--persistent' }
$guardianArgs += @('--poll-seconds', [string]$PollSeconds)

Push-Location -LiteralPath $RepoRoot
try {
    & $Python @guardianArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
