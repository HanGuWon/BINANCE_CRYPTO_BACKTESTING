# Phase 1 — Preserve V1 and Freeze the V2 Contract

## Scope

This phase creates only outcome-blind contract artifacts and governance pointers.
It never opens D-backed payload values and never edits V1.

## Exact changes

1. Add `campaigns/r3_prospective_context_v1/R3_EVALUATION_HORIZON_V1.json` with
   exactly the human-authorized fields: `horizon_key` equal to
   `R3_HORIZON_15M_NEXT_NATIVE_BAR_V1`, `interval` `15m`, `bars` `1`, `primary`
   `true`, `alternative_horizons` `[]`, selection basis
   `EX_ANTE_NATIVE_COLLECTION_CADENCE_AND_MECHANISM_ALIGNMENT`,
   `outcome_values_accessed` `false`, and `human_authorized` `true`. Add exact
   temporal fields defining one complete native interval after `T_exec`, with
   `source_available_time < next_executable_open_time` and equality rejected.
2. Add `R3_EVALUATION_AMENDMENT_V2.md` as a new immutable amendment. State the
   V1 SHA and classification `SUPERSEDED_PREREGISTRATION_BLOCKED`; preserve V1
   as historical preregistration evidence, not invalid outcome evidence. Freeze
   exactly H01–H06 and their existing estimands, the one 15m response notation,
   UTC 6h primary blocks, wild cluster bootstrap (10,000 Rademacher replicates),
   secondary symbol-and-block sandwich, Holm step-down alpha 0.05, and NW lag
   `ceil(15m/15m)-1 = 0`.
3. In V2 replace lifetime `missing_cycle_count == 0` with explicit accounting:
   integrity failures are global blockers; legitimate restart/source/missing/
   rollover gaps are preserved, never imputed, censored, and attributed to exact
   affected blocks. Retain all numerical minima unchanged and keep evaluation
   authorization separate from horizon authorization.
4. Add `R3_EVALUATION_AMENDMENT_V2_REPRODUCIBILITY_MANIFEST.json` with V1/V2/
   horizon SHA, frozen implementation/source/registry identities, exact formulas,
   and a no-outcome-access declaration.
5. Update `campaign_spec.toml`, `R3_PROTOCOL.md`, `metrics_contract.md`,
   `multiple_testing_plan.md`, and `promotion_policy.md` to point to V2 and the
   horizon artifact, set only the horizon-design authorization, keep
   `evaluation_human_authorized = false`, and use the preregistered-collection
   state taxonomy. No H01–H06 definition or numeric minimum changes.

## Verification / activation

- Parse the JSON and TOML; compute V1, horizon, and V2/manifest SHA256.
- Run a synthetic contract fixture through the checker with one horizon and assert
  horizon PASS but minima failure.
- Activation scenario: a fixture with two horizon keys must fail closed, while the
  one-key fixture passes the horizon gate without creating any response field.

## Bypass and residual

The contract is enforced by the checker and review receipts (E6); direct callers
can bypass the CLI by importing pure functions. This residual is explicit and does
not justify changing the sealed scientific source.
