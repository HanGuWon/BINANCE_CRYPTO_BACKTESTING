# R2A.2 Erratum 002 — Directional Signal Sign Not Enforced

Date: 2026-08-26 (KST). A follow-up independent audit found a P0 directional
signal defect affecting R2A.2 v0/v1/v2 executors AND the historical
r2a_engine.py used by R2A and R2A.1.

## Defect

The frozen SIGNAL_SEMANTICS defines directional values: +1 = bullish (LONG),
-1 = bearish (SHORT), 0 = no signal. But every executor only tested raw != 0
and then chose trade direction from the trial side alone.
Consequences:

- LONG trials executed on bearish (-1) signals (e.g., EMA death cross,
  RSI overbought, Donchian lower breakdown, negative funding sign).
- SHORT trials executed on bullish (+1) signals.
- Spot LONG-only trials were contaminated with short-side signals.

## Corrected rule (frozen semantics, not a redesign)

- LONG executes ONLY when signal == +1.
- SHORT executes ONLY when signal == -1.
- raw == 0 never enters. Opposite-sign never enters.

## Historical verdict disposition (R2A / R2A.1)

- r2a_engine.py contains the same raw != 0 defect, so R2A and R2A.1 outcomes
  mixed long/short signal directions within trials.
- R2A final: VERIFIED with NO Grade A/B after corrections — that null result
  is direction-mixed but still cannot be claimed as positive evidence either
  way; it must be treated as DIRECTIONALLY INVALID for per-direction inference.
- R2A.1 corrective: VERIFIED, prior positives did not survive — its null
  conclusion is unchanged in practice (no promoted evidence existed), but the
  underlying trade-level results are also DIRECTIONALLY INVALID and must not
  be reused for any per-direction claim.
- No historical conclusion is silently rewritten: both campaigns retain their
  published artifacts under superseded archives; this erratum documents that
  their per-direction trade data cannot support directional claims.

## Disposition of R2A.2 v2 checkpoints

- All superseded/interrupted roots are preserved on D: with `SHA256SUMS.txt`
  and `INVALID_REASON.txt`; none is eligible for scientific resumption. The
  exact executable commit associated with each root is recorded below:

| root | status | implementation commit |
|---|---|---|
| `checkpoints_invalid_superseded_v0` | incomplete/failed legacy run | not recorded in manifest |
| `checkpoints_invalid_superseded_v1` | invalid gap-unsafe state | `d6f452e999986859d098e6de660be5aa238a0e0f` |
| `checkpoints_invalid_superseded_v2` | invalid directional-sign state | `18cbb166c06489c9d820e48457bcdf03de9e7aad` |
| `checkpoints_invalid_superseded_v2_run` | preserved `checkpoints_v2` run | `e10b4cecbd6c8be63acbca890aede03200b0e8b6` |
| `checkpoints_invalid_superseded_v3` | interrupted/cache-sentinel state | `82c9b2e3037b8430ea358d1437ae69c238a7bf94` |
| `checkpoints_invalid_superseded_v4` | interrupted, superseded | `de4913789b365463eb8137f48320bb0d6731b9b8` |
| `checkpoints_invalid_superseded_v5_shard0/1` | shard attempt, superseded | `32f91b7e5ebb88d75d2797a267f078b4a819d9ce` |
| `checkpoints_invalid_superseded_v6_shard0/1` | shard attempt, superseded | `48607e19a12ba3c089d01e469d873fdfc6ec9bc6` |
| `checkpoints_invalid_superseded_v7` | interrupted, superseded | `a93928c93e46040a15194e77069cc8d831c4954a` |
| `checkpoints_invalid_superseded_v8` | interrupted, superseded | `f0e28c2eb6b67c82fb74ebe2f298a0d4048cfaed` |
| `checkpoints_invalid_superseded_v9_dirty_source` | stopped before strict qualification audit | `ca6bb9800ed3893c09fbf146186cd10aeeb47c25` |

The historical plan references to `checkpoints_v4` and the earlier session
identity (`b2251de...`/`de491378...`) are provenance for abandoned phases, not
the active executable. The next clean run is pinned to a newly committed
source identity and `checkpoints_v10`.

## Corrected execution

- run_r2a2_v2.py now gates on exact sign match and records signal_value per
  trade; the qualification matrix must exercise every registered horizon for
  Spot/UM, all three timeframes, both UM sides, funding events, and gap
  segments before any full run restarts at `checkpoints_v10`.
