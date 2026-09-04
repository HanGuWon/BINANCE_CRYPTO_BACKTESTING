# Phase 4 — V2 checker contract and adversarial synthetic matrix

## Scope and firewall

This unit hardens the outcome-blind readiness checker and synthetic contract
verifier only. It may inspect amendment/spec/map hashes and constructed
metadata. It must not open the D-backed collector root, response values,
labels, returns, rankings, holdout, R2B2, or any materializer/executor. The
collector remains running and all scientific identities remain unchanged.

## Exact implementation contract

1. Add a checker function `validate_primary_family_metadata(amendment,
   horizon_map, manifest)` that requires exactly the ordered six keys
   `H01` through `H06` (the canonical horizon-map/manifest family; inventory
   scope names remain `R3_H01` through `R3_H06`), exactly six primary p-value slots, a matching
   horizon-map SHA256 and amendment SHA256, and no hidden component-level or
   alternate-horizon keys. Extra p-value keys, duplicate keys, malformed
   hashes, or a component-level p-value map fail closed.
2. Cross-check the identity pins in the manifest: frozen implementation
   commit, frozen scientific source-tree SHA256, frozen registry SHA256,
   scientific root, sealed launch manifest and launch-seal status. A missing
   or mismatched identity fails closed; `git rev-parse HEAD` alone is never
   accepted as a dirty-tree proof.
3. Require the amendment/spec text to contain the exact point-in-time rule
   `source_available_time < next_executable_open_time` and the six frozen
   estimand identifiers. A source-open timestamp, ambiguous backward-bar
   wording, or an alternate horizon fails closed. Equality at an executable
   open must be rejected semantically, not merely documented.
4. Preserve the existing metadata firewall: no materializer/executor import,
   no outcome-value keys, final holdout `UNTOUCHED`, R2B2 `NOT_STARTED`, and no
   evaluation authorization side effect. The checker may report a blocked or
   collection-continues state but never starts work.
5. Require V2 inventory fields `gap_blocks_by_scope`,
   `excluded_block_ids_by_hypothesis`, `usable_blocks_by_hypothesis`,
   `usable_days_by_hypothesis`, `roster_contribution_by_hypothesis`, and
   `used_roster_identities`; validate them with the Phase 3 functions and invoke
   `validate_primary_family_metadata` in the same governance verifier. Require
   exact six-H coverage and cross-check the amendment/map hashes before any
   inventory gate is reported. Legacy
   fixture compatibility is limited to the pre-existing V2 synthetic tests and
   cannot weaken strict V2 validation.

## Synthetic tests

Add `ops/r3/tests/test_r3_checker_contract_v2.py` with constructed fixtures for
exactly-six `H01`–`H06` p-values, hidden component rejection, map/hash and
implementation/registry/source/root identity mismatch, horizon ambiguity,
holdout/R2B2 firewall, strict source-availability wording, equality-at-open
rejection, semantic rejection of a `source_open_time` substitution, and
materializer import absence. Include a regression that runs the verifier twice
and compares byte-identical JSON receipts. Fixtures contain no market values
and no D-root path.

Update `ops/r3/verify_r3_inventory_contract.py` or add a sibling governance
verifier so it exercises both the strict inventory maps and the six-key family,
cross-checks all frozen implementation/registry/source/root/launch-seal
identities, reports the superseding matrix hash, and refuses forbidden output
paths.

## Exit evidence

The phase exits with a commit and cxc receipt showing the synthetic checker
matrix passes, V1/V2/map hashes are preserved, exactly six primary slots are
enforced, and no live root/outcome/holdout access occurred.
