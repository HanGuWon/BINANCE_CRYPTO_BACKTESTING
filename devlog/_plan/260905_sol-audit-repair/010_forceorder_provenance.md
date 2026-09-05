# Work phase wp0 — ForceOrder and provenance audit

## Inputs read and scope

Read-only inputs are `campaigns/r3_prospective_context_v1/R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL.md`, `campaigns/r3_prospective_context_v1/R3_SOURCE_DEPENDENCY_MATRIX_V2_FORCEORDER.json`, `ops/r3/r3_forceorder_identity.py`, its two ForceOrder test modules, the R2B premium manifest/audit paths, and the D-backed v8 raw JSONL. Outcome files, checkpoint trades, returns, and holdout paths are prohibited.

## Audit matrix

1. Hash the exact V2 amendment, dependency matrix, roster, horizon map, and registry; enumerate H01–H06 and verify H03/H04 are distinct estimands, H01/H05 deterministic, and H06 orientation is explicit.
2. Census every `raw_v1/<um|cm>/<symbol>/liquidation.jsonl` envelope by market, event, stream, schema, endpoint, order-key shape, `st`, `ps`, symbol/pair, missingness, continuity, and file/row counts. Record a stable read window and re-check counts if the append-only root changes during the census.
3. Compare raw fields with official Binance USDⓈ-M and COIN-M market-stream schemas. In particular, treat `st=1/2` as symbol type and `ps` as pair symbol after CM migration; do not infer position side from `ps`.
4. Classify the observed `ps_ENUM_INVALID` population exactly as A validator defect, B collector normalization defect, C source schema change, D genuinely invalid records, or E mixed, with counts and representative metadata-only examples. A classification is accepted only when schema and raw evidence agree.
5. Verify the identity tuple and `forceorder:v2:<sha256(canonical identity JSON)>` for exact duplicates, reconnect replays, same timestamp/different liquidation, same order ID, side/quantity differences, UM/CM namespace differences, and a monkey-patched digest collision. Check that duplicate/collision counts and deterministic representative selection are invariant.
6. Inspect live v8 lock/process and sealed manifest metadata only: PID liveness, lock path, writer count, chain/manifest status, implementation/source/registry identities, cycle count, and `final_holdout_status`. Do not stop, restart, append, or repair it.

## Decision and deliverables

Write `reports/SOL_AUDIT_WP0_FORCEORDER_PROVENANCE.md` with command lines,
timestamps, hashes, raw census, official-source links, classification, V2
preserve/V3-required decision, stale-root table, and an explicit no-outcome
attestation. Because the official/raw evidence confirms a material `ps`
contract defect, wp1 must create the versioned V3 parser/matrix/verifier path;
it may not fall back to a non-scientific V2 repair. Classify the new path as
`R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED`; never patch live v8.

## Verification commands

Run the actual existing verifiers after checking their source paths:

- `python ops/r3/verify_r3_registry_contract.py`
- `python ops/r3/verify_r3_v2_horizon_contract.py`
- `python ops/r3/verify_r3_inventory_contract.py`
- `python ops/r3/verify_ops_layer.py`
- `python -m pytest -q ops/r3/tests/test_forceorder_identity.py ops/r3/tests/test_forceorder_dependency_matrix.py -p no:cacheprovider`

Save exit codes and outputs in the phase ledger. A failed or race-unstable
read-only audit blocks the phase; it is not repaired by changing the evidence.
