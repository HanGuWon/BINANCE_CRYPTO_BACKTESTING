[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = 'C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트'
$Python = 'C:\Users\user\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe'
$OpsScript = Join-Path $RepoRoot 'ops\r3\r3_ops.py'
$ScientificRoot = 'D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8'
$Roster = Join-Path $RepoRoot 'campaigns\r3_prospective_context_v1\rosters\2026-09.json'
$LaunchManifest = 'D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json'
$LaunchSeal = 'D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json'
$env:PYTHONPATH = 'C:\Users\user\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages'

Push-Location -LiteralPath $RepoRoot
try {
    & $Python $OpsScript watch --exact-v8 --root $ScientificRoot --roster $Roster --manifest $LaunchManifest --seal $LaunchSeal
    exit $LASTEXITCODE
}
finally { Pop-Location }
