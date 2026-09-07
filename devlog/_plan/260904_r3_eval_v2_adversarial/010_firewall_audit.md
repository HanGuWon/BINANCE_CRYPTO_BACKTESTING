# Phase 0 — firewall and V1 statistical audit

## Evidence required

- branch/HEAD/origin and scoped scientific status;
- frozen implementation, registry, and source-tree identities;
- exact-v8 collector writer/lock/chain/seal/outcome metadata;
- exact D-backed root path, file count, tree hash before/after, and no-root-or-
  manifest-rewrite proof;
- byte SHA of V1;
- a defect table for H01–H06 covering unit, feature, window, null/statistic,
  p-value, dependence, missingness, censoring, and multiplicity.

## Safety

Only file metadata, schema, timestamps, identities, and contract text may be
read. No market response, label, return, PnL, performance, ranking, holdout,
or R2B2 value may be materialized or inspected.

The pass predicates are: scoped scientific status empty; `HEAD...origin` `0 0`;
one live authorized writer; zero duplicate writers; live lock; manifest chain
PASS; launch seal SEALED; exact frozen implementation/source-tree/registry/root
identity; and outcomes NOT_STARTED. A root hash is a read-only integrity
snapshot (the collector remains append-only); before/after hashes must match
within the audit window. Any mismatch is a hard stop.

## Exit

Freeze the audit evidence and enter the horizon/estimand phase only if the
sealed collector and scientific identity remain valid.
