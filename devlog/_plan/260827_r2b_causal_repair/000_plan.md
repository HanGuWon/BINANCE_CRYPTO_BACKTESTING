# R2B causal premium repair and pre-outcome readiness

## Loop specification

- Archetype: spec-satisfaction repair with a hard pre-outcome scientific gate.
- Trigger: the repaired R2B panel still uses kline open timestamps as availability proof.
- Goal: produce a causally valid, preregistered, UM-only R2B experiment ready for a later separately authorized outcome campaign.
- Non-goals: no R2B outcome run, no final-holdout access, no performance inspection, no R2A.2 reinterpretation, no raw archive rewrite.
- Verifier: adversarial causal tests, materialization/guard proof, UM-only qualification, directional tests, and full python -m pytest -q.
- Stop condition: R2B_READY_FOR_PREOUTCOME_FREEZE only after all criteria are evidenced; otherwise an explicit blocked state.
- Memory artifact: .codexclaw/goalplans/safely-repair-r2b-premium-availability-timestamp/ledger.jsonl plus campaign manifests.
- Expected terminal outcomes: DONE/R2B_READY_FOR_PREOUTCOME_FREEZE, R2B_BLOCKED_CAUSAL_DATA, R2B_BLOCKED_SIGNAL_SEMANTICS, or R2B_BLOCKED_IMPLEMENTATION.
- Escalation: upward reclaim after two failed delegated packets; downward delegation only by a new P-phase amendment.
- HOTL bounds: repository-local files only; no network acquisition; no holdout paths; each phase bounded to one focused implementation/verification cycle.

## Dependency-ordered work phases

1. 010_causal_source_contract.md: inspect raw schema, prove the open-time defect, and define source availability fields and adversarial tests.
2. 020_materialization_guard_root.md: implement causal resampling/alignment, preserve/hash old root, materialize a new D-backed root, and emit an availability-time proof.
3. 030_semantics_qualification.md: correct UM-only qualification artifacts, quarantine old performance artifacts, freeze pre-outcome premium semantics, and implement directional tests/reference parity.
4. 040_readiness_freeze.md: run targeted gates and full pytest, pin hashes, update provenance, and close with exact R2B readiness disposition.

## Scope boundary

IN: scripts/materialize_r2b_premium_panel.py, R2B readiness/qualification tests and campaign docs/manifests, new errata/proof files, and compact source provenance.

OUT: R1/R2A source semantics, raw archives, existing repaired root contents, final-holdout data, R2B outcome executors/results, and historical performance artifacts.

## Acceptance criteria

- Every materialized premium row carries source open, close, availability, and derived max-constituent-close timestamps; joins require strict availability before executable open.
- Old repaired root is hashed and marked INVALID/SUPERSEDED; new root is distinct, pre-holdout, and coverage is measured rather than copied.
- Guard proof checks every row, complete derived buckets, no forward-asof, segment resets, zero holdout rows, and no holdout source path access.
- Qualification is UM-only and covers 15m/1h/4h, both sides, every registered horizon, funding signs, gaps, missingness, warmup, sign rejection, and next-open parity against a slow reference.
- Semantics are frozen in an amendment with equations, signs, missing/warmup/event rules, and final registry hash before any outcome access.
- Full pytest passes from a clean scientific source tree; final holdout remains untouched.
