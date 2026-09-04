# Phase 5 — synthetic qualification and full metadata-only verification

## Scope and hard stop

Run only constructed-fixture qualification and metadata verifiers. Do not
materialize responses, compute returns/PnL/Sharpe/hit rates, inspect any R3
outcome/performance artifact, access final holdout/R2B2, or stop the scientific
collector. A live-root check may inspect only identities, manifests, health,
seals, roster/gap metadata, and file statistics; it must not parse payload
values.

## Required evidence

1. Run the strict checker/inventory/forceOrder synthetic test matrix twice with
   cxc receipts. Compare the canonical JSON verifier output and test summary
   byte-for-byte; any difference blocks the phase.
2. Run `verify_r3_v2_horizon_contract.py`,
   `verify_r3_inventory_contract.py`, the registry verifier, and the existing
   R3 firewall verifier. Capture command, exit code, implementation/registry/
   source-tree identities, and holdout/R2B2 status.
3. Run the full `python -m pytest -q` suite once. Record the exact final
   summary, warning count, timestamp, and scoped scientific Git status. A
   dirty scientific source tree blocks qualification; unrelated archival or
   `.codexclaw` files are not silently staged.
4. Perform a metadata-only collector/live identity watch proving one writer,
   duplicate writers zero, manifest chain PASS, launch seal SEALED, outcomes
   NOT_STARTED, final holdout UNTOUCHED, and no R2B2 checkpoint. Confirm the
   D-backed root and launch manifest identities remain equal to the frozen
   pins before and after the watch.

## Exit condition

The phase exits only with reproducible receipts, all verifiers PASS, full
pytest PASS, no forbidden outcome access, and an unchanged scientific root.
It does not authorize or launch historical R3 evaluation; the following phase
is governance commit/report only.
