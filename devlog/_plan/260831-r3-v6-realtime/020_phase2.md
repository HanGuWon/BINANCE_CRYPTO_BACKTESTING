# Phase 2 — true wall-clock v6 burn-in

Create only the fresh D-backed root
`D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\engineering_shadow_august_v6_realtime`.
Invoke `run_engineering_shadow_forever` with the August roster, four cycles,
900-second interval, `wait_for_boundary=True`, and no initial-boundary override.
The run must use real Binance-calibrated absolute 15-minute boundaries and may
complete fewer than four cycles if the 2026-09-01 boundary is reached.

Verify target/scheduled/actual times, lateness, cycle spacing, absolute next
execution, calibration references, continuous WS uptime/reconnects/events,
VANRYUSDT open-interest provenance, evidence-mode isolation, manifest chain,
and per-cycle storage deltas plus projections. No returns or outcome fields may
be read or generated.
