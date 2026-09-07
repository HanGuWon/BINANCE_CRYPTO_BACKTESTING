# WP2 — Existing sealed-v8 resume and collision closeout

Date: 2026-09-07 KST

The WP2 gate was exercised against the existing
`D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8`
root only. No new root, backfill, raw-history rewrite, roster change, launch
seal change, outcome access, R2B2 access, or ForceOrder V3 migration occurred.

## Receipts

- `168_wp2_launch_receipt_20260907_v3.json` is preserved as a **superseded
  diagnostic**: its first census counted the receipt-producing Python command
  because its command text contained the collector token. It was not used as
  proof and was never overwritten.
- `168_wp2_launch_receipt_20260907_v4.json` is the corrected launch receipt.
  It binds authorization id `78e7002d-d064-4334-80ba-24cf9f870dcf`, consumed at
  `2026-09-07T03:21:55.964916+00:00`, lock owner PID `180656`, exactly one
  Python collector writer, 197 historical cycles plus one observed future
  cycle, and the preserved historical missing-cycle baseline of 87. The
  current grid gap is reported separately because the collector was dead while
  later wall-clock intervals elapsed.
- `167_wp2_collision_receipt_20260907.json` records the canonical
  `-PreflightOnly` collision command with exit code **73**, one live writer
  (PID `180656`), no duplicate writer, and identical manifest-chain SHA before
  and after.

The first canonical launcher invocation was safely blocked before consume by
an implementation-discovered PowerShell variable collision and remains visible
in the terminal history. After the fix was committed, the same single-use
lease was consumed exactly once by the canonical launcher. The subsequent
collision probe returned 73; no second collector was started.

## Current live state

The foreground canonical launcher process is intentionally left running for
WP3 observation. Its collector arguments remain the frozen
`--mode SCIENTIFIC --persistent --root ... --roster-artifact ...
--launch-manifest ...` contract. The active lock owner is the only authorized
writer.

