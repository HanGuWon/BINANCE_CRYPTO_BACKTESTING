# Work phase wp3 — provenance, labels, outputs, and portability

## A08 provenance reconciliation

Compare every referenced R1/R2B/R3 implementation, source-tree, registry,
manifest, and semantic-membership hash. Preserve stale receipts and roots as
immutable `INVALID/SUPERSEDED` records; add an explicit table naming the exact
implementation that produced each abandoned root. Do not rewrite old verdicts.

## A09 membership label

Modify `scripts/aggregate_r2a2.py` and its tests/reporting so an aggregation
whose input roster is already Top50 is labelled a
`TOP50_MEMBERSHIP_SUBSET_DIAGNOSTIC`, not a Top100 universe result. Keep the
historical six-thousand-unit arithmetic unchanged and make the label visible in
machine-readable and human-readable outputs.

## A10 immutable outputs

Modify `src/binance_research/reporting.py` and registry/output writers to use an
immutable experiment directory or content-addressed filename, reject collisions
when bytes differ, and preserve prior bytes on append. Define the identity rule:
same canonical experiment metadata plus identical bytes is idempotent; the same
identity plus different bytes raises without modifying the existing artifact.
Add collision and reproducibility tests for every writer path; never overwrite
a prior scientific artifact.

## A11 portability

Repair default config/path resolution to be repository-root independent, align
test discovery with `tests` plus `ops/r3/tests`, and pin the supported Python /
dependency invocation in docs and tests. Do not commit virtualenv, cache, raw,
Parquet, or chmod noise.

## Deliverables and classification

Update only the canonical text/manifests where identity reconciliation proves
the change. The durable report classifies each diff as
`MERGE_SAFE_NONSCIENTIFIC`, `FUTURE_HARNESS_REPAIR`, or
`R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED`; no merge or V9 migration is performed.
