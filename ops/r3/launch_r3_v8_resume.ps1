[CmdletBinding()]
param([switch]$PreflightOnly)

$ErrorActionPreference = 'Stop'
$RepoRoot = 'C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트'
$Python = 'C:\Users\user\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe'
$OpsScript = Join-Path $RepoRoot 'ops\r3\r3_ops.py'
$Collector = Join-Path $RepoRoot 'scripts\run_r3_prospective_collector.py'
$ScientificRoot = 'D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8'
$Roster = Join-Path $RepoRoot 'campaigns\r3_prospective_context_v1\rosters\2026-09.json'
$LaunchManifest = 'D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json'
$LaunchSeal = 'D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json'
$env:PYTHONPATH = 'C:\Users\user\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages'

foreach ($required in @($Python, $OpsScript, $Collector, $ScientificRoot, $Roster, $LaunchManifest, $LaunchSeal)) {
    if (-not (Test-Path -LiteralPath $required)) { Write-Error "required v8 path is missing: $required"; exit 20 }
}

Push-Location -LiteralPath $RepoRoot
try {
    & $Python $OpsScript preflight --exact-v8 --root $ScientificRoot --roster $Roster --manifest $LaunchManifest --seal $LaunchSeal
    $preflightExit = $LASTEXITCODE
    if ($preflightExit -ne 0) { exit $preflightExit }
    if ($PreflightOnly) { exit 0 }

    # Keep the collector in this foreground process so the existing scientific
    # PID lock spans the full lifetime. The collector performs its own resume,
    # chain, and seal checks; this wrapper never creates a fresh root.
    & $Python $Collector --mode SCIENTIFIC --persistent --root $ScientificRoot --roster-artifact $Roster --launch-manifest $LaunchManifest
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
