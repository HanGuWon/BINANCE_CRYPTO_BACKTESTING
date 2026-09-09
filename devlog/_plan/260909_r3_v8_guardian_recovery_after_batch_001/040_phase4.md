# 040 — Phase 4: future observation and live postcheck

## Scope

WP10–WP11. Observe at least two genuinely new cycles strictly after recovery. Historical cycles and already-completed receipts do not count.

## MODIFY / NEW / DELETE map

- NEW: `campaigns/r3_prospective_context_v1/operations/R3_V8_POST_RECOVERY_WATCHDOG_20260908.json`, binding the recovery time, first and second new cycle IDs, health/manifest receipt hashes, preserved missing intervals, final process/lock counts, identity, chain, seal, and disk state.
- MODIFY: none.
- DELETE: none.

## Observation protocol

- Capture a pre-recovery boundary and a post-recovery boundary from the scheduler/cycle metadata.
- For each qualifying cycle require a new cycle ID, target boundary strictly after recovery, health receipt, manifest entry, exact v8 identity, and chain continuity. A first resumed cycle whose target precedes recovery is retained as nonqualifying evidence.
- Watch the guardian and collector through both cycles. Historical gaps may remain, but the post-recovery watchdog must no longer be RED solely because the writer is absent.

## Verification

- Run the exact-v8 watchdog after each cycle and once after the second; exit `0` with `collector=1`, `guardian=1`, both locks alive, duplicates empty, chain PASS, seal SEALED, disk not RED, and unchanged source/registry identities.
- Compare cycle IDs and timestamps against the pre-recovery receipt using an independent script; no returns, PnL, hit rate, or performance fields are read.

## Acceptance

Two strict future cycles plus the final live postcheck are required. If the guardian or writer dies before two cycles, preserve the evidence and stop in the appropriate blocked state rather than counting old cycles.

