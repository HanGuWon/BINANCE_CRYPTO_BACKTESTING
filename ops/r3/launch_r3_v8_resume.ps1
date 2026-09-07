[CmdletBinding()]
param(
    [switch]$PreflightOnly,
    [string]$AuthorizationReceipt,
    [string]$PreflightReceipt
)

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
    if (-not $PreflightOnly) {
        if ([string]::IsNullOrWhiteSpace($AuthorizationReceipt)) {
            Write-Output 'an explicit v8 resume authorization receipt is required'
            exit 74
        }
        if (-not (Test-Path -LiteralPath $AuthorizationReceipt -PathType Leaf)) {
            Write-Output "resume authorization receipt is missing: $AuthorizationReceipt"
            exit 74
        }
        try {
            $authorization = Get-Content -Raw -LiteralPath $AuthorizationReceipt | ConvertFrom-Json
            $preflightReceipt = [string]$authorization.preflight_receipt_path
        }
        catch {
            Write-Output "resume authorization receipt is invalid: $AuthorizationReceipt"
            exit 74
        }
        if ([string]::IsNullOrWhiteSpace($preflightReceipt) -or -not (Test-Path -LiteralPath $preflightReceipt -PathType Leaf)) {
            Write-Output 'resume authorization preflight receipt is missing'
            exit 74
        }
    }

    $preflightArgs = @('preflight', '--exact-v8', '--root', $ScientificRoot, '--roster', $Roster, '--manifest', $LaunchManifest, '--seal', $LaunchSeal)
    if (-not [string]::IsNullOrWhiteSpace($PreflightReceipt)) {
        $preflightArgs += @('--receipt', $PreflightReceipt)
    }
    & $Python $OpsScript @preflightArgs
    $preflightExit = $LASTEXITCODE
    if ($preflightExit -ne 0) { exit $preflightExit }
    if ($PreflightOnly) { exit 0 }

    & $Python $OpsScript verify-resume-authorization --exact-v8 --root $ScientificRoot --roster $Roster --manifest $LaunchManifest --seal $LaunchSeal --authorization $AuthorizationReceipt --preflight-receipt $preflightReceipt --consume
    $authorizationExit = $LASTEXITCODE
    if ($authorizationExit -ne 0) { exit $authorizationExit }

    # Re-check identity and the writer census immediately after consuming the
    # lease. A race or collision fails closed and the collector is never called.
    & $Python $OpsScript preflight --exact-v8 --root $ScientificRoot --roster $Roster --manifest $LaunchManifest --seal $LaunchSeal
    $postAuthorizationPreflightExit = $LASTEXITCODE
    if ($postAuthorizationPreflightExit -ne 0) { exit $postAuthorizationPreflightExit }

    # Keep the collector in this foreground process so the existing scientific
    # PID lock spans the full lifetime. The collector performs its own resume,
    # chain, and seal checks; this wrapper never creates a fresh root.
    & $Python $Collector --mode SCIENTIFIC --persistent --root $ScientificRoot --roster-artifact $Roster --launch-manifest $LaunchManifest
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
