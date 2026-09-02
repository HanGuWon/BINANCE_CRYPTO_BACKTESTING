# 000 — r3-v3-discovery-launch: Plan

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## Objective

Close the remaining R3 launch evidence gap and, only if it passes, complete the
isolated production-v3 prospective launch. The observed gap is that
`campaigns/r3_prospective_context_v1/R3_AUGUST_SOURCE_EXPECTED_SET_PARITY_RECEIPT.json`
claims `ranking_input = precomputed_artifact_control_only`; it does not prove the
new month-scoped Binance Vision discovery path. The current identity audit shows
HEAD `3d7d0d338e2bbd45e0d0e2f055d3dd41acb689dc`, origin parity 0/0, `778ba211`
ancestor-only receipt commit, clean scientific source scope, source-tree SHA
`2ebbc126e811e2d914ba7c8994c67fd529e7d1797a222bd879c40f47ef49baa8`, and registry
SHA `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a`.
Production-v1/v2 remain immutable. No returns, PnL, holdout, or R2B2 data may be
read. A parity failure terminates as `R3_BLOCKED_DISCOVERY_PATH_PARITY` and the
v3 launch is not attempted.

## Loop-spec

- Loop archetype: verifier-defined repair then gated execution
- Write scope / out-of-scope: only the files listed in the phase docs, append-only
  outcome-blind receipts, and the reserved D-backed v3 roots; out of scope are
  outcome/performance artifacts, final holdout, R2B2, manual symbol edits, and
  mid-launch scientific code changes.
- Budget / bounds: use existing repository Python/toolchain and public Binance
  Vision/UM endpoints; one parity replay, one production-v3 launch attempt, and
  at least two completed 15-minute scientific cycles. Stop on any fail-closed
  blocker; never delete v1/v2 evidence.

## Work-phase map (one phase = one full PABCD cycle)

| WP | Doc | Slice | Depends on |
|----|-----|-------|------------|
| wp1-id | 010_phase1.md | Identity reconciliation, immutable-root audit, fresh-root gate | — |
| wp2-parity | 020_phase2.md | General month-scoped discovery path and outcome-blind parity preflight | wp1-id |
| wp3-v3 | 030_phase3.md | Freeze launch identity, calibrated production-v3, roster, shadow and seal | wp2-parity |
| wp4-live | 040_phase4.md | Activate collector, verify persistent cycles, seal activation receipt | wp3-v3 |

## Accept criteria

- Identity/origin/scope and v1/v2 preservation proven; v3/scientific roots fresh.
- True July-to-August discovery-path parity receipt pins discovery inventory,
  verified source, ranking, and exact committed Top50 parity, or records the
  explicit blocked state.
- Clean launch identity and v3 manifest/seal are pinned before collection.
- At least two real outcome-blind SCIENTIFIC cycles independently verify.
- Final report records hashes/counts and leaves outcomes/final holdout/R2B2
  untouched.
