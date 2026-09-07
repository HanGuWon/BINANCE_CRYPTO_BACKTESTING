# 020 — Phase 2 (r3-v3-discovery-launch)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

1. `scripts/prepare_r3_post_boundary_launch.py` (MODIFY): factor the current
   August-only inventory into a month-parameterized discovery/eligibility helper;
   preserve the August production wrapper, actual S3 object listing, monthly vs
   discovered daily fallback, integrity blocking, and no-source/partial states.
2. `scripts/qualify_r3_discovery_path.py` (NEW): invoke the same helper against
   source month `2026-07`, resolve only actual listed objects into a temporary
   D-backed qualification root, verify complete-month inputs, call the frozen
   ranking, compare exact ordered Top50/logical SHA with
   `campaigns/r3_prospective_context_v1/rosters/2026-08.json`, and emit no outcome
   fields. Never use `precomputed_artifact_control_only`.
3. `tests/test_r3_discovery_path.py` (NEW): synthetic inventory fixtures for
   monthly, daily fallback, partial, no-source, discovered-404, checksum and
   exact parity; assert no guessed URLs and outcome-blind receipt schema.
4. `campaigns/r3_prospective_context_v1/R3_AUGUST_DISCOVERY_PATH_HISTORICAL_PARITY_RECEIPT.json`
   (NEW, append-only): pin implementation/source/registry, source/effective
   months, inventory/verified/ranking/roster hashes, counts, and PASS/FAIL.

## TESTS

Run the new discovery-path tests plus existing R3 production/ranking/universe
tests. The parity command must use authoritative public Binance Vision listing
and the temporary qualification root, with `outcomes_accessed=false`.

## Verification (C)

`python -m pytest -q tests/test_r3_discovery_path.py tests/test_r3_production_wiring.py`;
run the discovery preflight CLI with source month July/effective August and
temporary D root; verify receipt fields and exact roster parity. Expected exit 0
and `ranking_input=AUTHORITATIVE_MONTH_SCOPED_DISCOVERY`; on any mismatch exit 2
with `R3_BLOCKED_DISCOVERY_PATH_PARITY` and do not proceed.
