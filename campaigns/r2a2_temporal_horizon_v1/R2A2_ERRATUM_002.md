# R2A.2 Erratum 002 — Directional Signal Sign Not Enforced

Date: 2026-08-27 (KST). A follow-up independent audit found a P0 directional
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

- checkpoints_v2 preserved as checkpoints_invalid_superseded_v2/
  (SHA256SUMS.txt + INVALID_REASON.txt). Not scientific evidence.

## Corrected execution

- run_r2a2_v2.py now gates on exact sign match and records signal_value per
  trade; qualification requires explicit sign matching against a slow
  reference implementation before any full run restarts at checkpoints_v3.
