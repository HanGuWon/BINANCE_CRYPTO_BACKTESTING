# R3 Evaluation Amendment V1 — outcome-blind defect ledger

Recorded 2026-09-04 KST before changing the V1 contract. This review uses only
the V1 text and metadata contracts; no response, return, label, ranking,
performance, final-holdout, or R2B2 value was read.

## Cross-hypothesis defects

1. V1 leaves `h` empty (`H_frozen = ∅`). A future evaluator could choose a
   horizon after opening outcomes.
2. The single universal horizon is not justified by mechanism and is not
   mapped to the six mechanisms.
3. The response endpoint is only described as before a holdout boundary; the
   evaluation-versus-confirmatory calendar/roster partition is not frozen.
4. V1 gives a general bootstrap/sandwich description but not one exact scalar
   test statistic and p-value construction for each hypothesis.
5. The primary UTC-6h block rule is global; source-specific gaps, usable block
   sets, per-hypothesis temporal minima, and roster contributions are absent.
6. Overlapping response behavior, rollover treatment, exact boundary behavior
   for each endpoint, and the incremental treatment of delayed responses are
   not fully executable.

## H01 — execution-quality context

- Observation unit and `(s,d)` definitions exist, but the vector
  `theta_H01=(Cov(Y,s),Cov(Y,d))` creates two possible primary claims while the
  family is declared to contain six tests.
- No single omnibus null, exact joint statistic, or unique p-value is frozen.
- `spread_bps` is non-directional while `microprice_displacement` is
  directional; a raw signed-return regression is not identified as a
  mechanistically coherent context contribution conditional on baseline
  direction.
- Scaling, rank/zero handling, and the exact fixed design matrix are left open.

## H02 — price × open-interest quadrant

- The four cells are named and ordered, but V1 does not freeze the exact
  four-cell omnibus statistic or its p-value algorithm.
- It does not say whether any cell contrast is primary or secondary; a
  post-outcome reference cell could be selected.
- Timestamp alignment and source-specific OI gap-to-block eligibility are not
  operationally mapped.

## H03 — liquidation continuation

- The force-order event key, replay/reconnect deduplication, collision policy,
  and raw-payload identity are unspecified.
- The exact scalar bootstrap statistic/p-value implementation is not written.
- The response window is parameterized by the missing `h`, so the continuation
  endpoint is discretionary until outcomes are visible.

## H04 — liquidation reversion

- V1 defines `theta_H04(h) = -theta_H03(h)` on the identical event set and
  response. These are algebraic negatives rather than independent confirmatory
  estimands.
- No delayed/non-overlapping or explicitly incremental response window exists.
- It inherits the H03 event identity, replay, and missing-horizon defects.

## H05 — crowding × stress modifier

- The two-component vector `(Cov(bY,f), Cov(bY,p))` permits component-level
  significance fishing while the family claims one H05 test.
- No unique omnibus joint null/statistic/p-value is frozen.
- Funding/premium scaling, interaction/modifier construction, baseline-zero
  behavior, and source-specific gap scope are not deterministic.

## H06 — BTC/breadth concordance

- `C_t = mean(sign(r_symbol)*sign(r_BTC))` measures concordance strength but
  removes whether BTC itself is up or down.
- A raw `Cov(Y,C_t)` can cancel bullish and bearish concordant episodes; no
  orientation is frozen.
- The exact scalar statistic/p-value and BTC/breadth source-gap scope are not
  fully specified.

## Required V2 repairs

Freeze one exact horizon map, one scalar primary p-value per H01–H06, a fixed
H01/H05 omnibus design, a four-cell H02 omnibus equality test, non-redundant
H03/H04 windows, an oriented H06 response, force-order identity/deduplication,
source-specific gap/block accounting, per-hypothesis temporal minima, and an
explicit evaluation/untouched-confirmatory firewall. V1 remains immutable and
is superseded by hash; it is not invalid outcome evidence.
