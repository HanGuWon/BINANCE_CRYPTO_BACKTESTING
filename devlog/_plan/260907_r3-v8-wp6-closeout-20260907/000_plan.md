# 000 — r3-v8-wp6-closeout-20260907: Plan

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## Objective

Close the R3 v8 recovery-accounting and guardian-self-healing work without
touching the sealed scientific collector, historical outcomes, R2B2, or the
final holdout.  The observed operational gap is that the corrected append-only
accounting and child-authorization code exists, but the canonical persistent
guardian has not yet been started and live one-guardian/one-writer evidence has
not been captured after the guarded implementation was installed.  The evidence
base is the immutable V2/V3 outage receipts, V6/V7 firewall receipts, the
standing-policy and synthetic qualification artifacts, and the live v8 root.

## Loop-spec

- Loop archetype: verifier-defined operations closeout with judged safety gates.
- Write scope / out-of-scope: operations/governance files under `ops/r3`,
  `campaigns/r3_prospective_context_v1/operations`, and this devlog plan only.
  Do not modify `scripts/`, `src/`, repository-root `tests/`, `configs/`, the
  sealed v8 root, any raw/Parquet data, or historical scientific receipts.
- Budget / bounds: one canonical guardian start at most; collector is never
  stopped; no backfill, migration, outcome/return computation, R2B2, or
  holdout access.  Run only synthetic/read-only verification and tests.

## Work-phase map (one phase = one full PABCD cycle)

| WP | Doc | Slice | Depends on |
|----|-----|-------|------------|
| 1 | `010_phase1.md` | Census and start exactly one persistent guardian | WP3 guardian implementation |
| 2 | `020_phase2.md` | Verify immutable accounting/firewall and write continuation V2 | WP1 |
| 3 | `030_phase3.md` | Focused and broader operations qualification | WP1, WP2 |
| 4 | `040_phase4.md` | Scientific-scope/firewall audit, intentional commit, closeout | WP1–WP3 |
| 5 | `050_phase5.md` | Final full-suite proof and intentional operations commit | WP4 |

## Accept criteria

- c-1: one healthy v8 writer and one guardian, locks/chain/seal/identity and
  continuing cycles verified without collector interruption.
- c-2: immutable V3/V7 accounting decomposition remains valid.
- c-3: standing policy and child authorization remain identity-, preflight-,
  parent-, expiry-, and replay-bound.
- c-4: synthetic guardian matrix and re-entry/throttling tests remain PASS.
- c-5: operations-only clean scope, tests, continuation V2, and all outcome /
  holdout / migration firewalls are PASS.
