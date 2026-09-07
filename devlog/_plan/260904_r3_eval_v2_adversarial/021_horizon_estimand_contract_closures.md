# Phase 1 audit closure — deterministic rank, event, and bootstrap rules

The independent A review identified six blockers. This note records the
repair decisions before B implementation; no response or outcome data was
opened.

1. **Canonical linkage.** The previous single-15m manifest remains unchanged
   under `R3_EVALUATION_AMENDMENT_V2_REPRODUCIBILITY_MANIFEST.json`. A new
   manifest pins `R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL.md`, the exact-six
   `R3_EVALUATION_HORIZON_MAP_V1.json`, both hashes, and the old manifest SHA.
2. **Omnibus degeneracy.** H01/H05 require full nuisance rank and tested rank
   exactly 2; H02 requires all four fixed cells and cell-design rank 4. Any
   rank deficiency, non-positive robust variance, non-finite statistic, or
   fewer than two complete blocks is an eligibility failure, never a sentinel
   p-value. Moore–Penrose inversion is permitted only after the tested rank
   check passes.
3. **H06 zero-return handling.** BTC return must be finite and nonzero, and at
   least one selected non-BTC breadth symbol must be valid. Otherwise the
   observation is censored rather than represented by a zero sign or zero
   oriented response.
4. **H03/H04 event universe.** Build one candidate forceOrder universe after
   identity and replay validation. H03 and H04 then apply separate endpoint
   filters (+15m for H03; both +15m and +60m for H04) and report independent
   unique counts. This removes the prior contradiction while preserving shared
   event identity and sign.
5. **Source timestamps.** REST snapshots use normalized
   `corrected_response_receipt_time` (fallback `response_received_at`) and
   forceOrder uses `corrected_response_receipt_time` (fallback
   `collector_receipt_time`). Select the latest finite record strictly before
   `T_exec` by the ascending tuple
   `(source_available_time, exchange_event_time, source_identity)`, taking the
   lexicographically greatest eligible tuple. ForceOrder event time is
   normalized payload `E`; order `T`/`t` is descriptive. The executable open is
   the first scheduled open strictly after both event and source-available
   times.
6. **Bootstrap determinism.** For each declared statistic, fit the restricted
   null, multiply complete-block residuals by the seeded 10,000-draw Rademacher
   sequence, refit, and use the observed studentization. The inclusive
   two-sided p-value is `(1 + count(|T_boot| >= |T_obs|))/10001`; no rounding,
   alternate tail, or component p-value exists.

The amended V2 and map are still metadata-only. These decisions must be
covered by synthetic degenerate/event/timestamp/bootstrap tests before the
phase is accepted.
