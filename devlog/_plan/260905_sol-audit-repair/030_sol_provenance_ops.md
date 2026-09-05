# Work phase wp3 — provenance, labels, outputs, and portability

This is a metadata/harness repair phase in the isolated worktree. It does not
open a checkpoint, return, performance, or final-holdout artifact and it does
not change the sealed v8 collector identity.

## A08 provenance reconciliation

Compare every referenced R1/R2B/R3 implementation, source-tree, registry,
manifest, and semantic-membership hash. The authoritative R3 V2 contract is the
adversarial amendment and horizon map; the short V2 amendment/manifest remain
preserved historical bytes. Add a new append-only provenance index and report
with an explicit table naming the exact implementation, source-tree, registry,
root, and disposition for each abandoned or active identity. Preserve stale
receipts and roots as immutable `INVALID/SUPERSEDED` or `HISTORICAL_EVIDENCE`
records; never rewrite an old verdict. Correct only live contract references
that are demonstrably stale, and record the old/new file hashes and reason.

The exact new artifacts are `campaigns/r3_prospective_context_v1/operations/SOL_AUDIT_WP3_PROVENANCE_INDEX_20260905.json` and `reports/SOL_AUDIT_WP3_PROVENANCE_RECONCILIATION.md`. The index is created once for the date: if that path exists, an identical canonical byte payload is an idempotent no-op and any different payload fails before mutation; a later correction gets a new date-named index rather than rewriting it. Its deterministic JSON object has exactly these top-level keys in sorted order: `record_type` (string), `branch` (string), `base_commit` (40-hex string), `repair_commits` (ordered list of 40-hex strings), `active_v8_identity` (object), `references` (ordered list), `dispositions` (ordered list), `corrections` (ordered list), `outcome_values_accessed` (boolean false), `final_holdout_status` (string `UNTOUCHED`), `r2b2_status` (string `NOT_STARTED`), and `merge_action` (string `NONE`). Every identity row carries exact `implementation_commit`, `source_tree_sha256`, `registry_sha256`, `causal_or_data_root`, and a disposition (`CURRENT_FROZEN`, `HISTORICAL_EVIDENCE/SUPERSEDED_BY_ADVERSARIAL_V2`, `INVALID_SUPERSEDED/BLOCKED`, `HARNESS_REPAIR_ONLY`, or `HISTORICAL_SNAPSHOT`). Hash sources are explicit repository paths: `R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL.md`, `R3_EVALUATION_HORIZON_MAP_V1.json`, the adversarial reproducibility manifest, and the preserved short V2 amendment/manifest; hashes are computed from exact bytes with SHA-256. The report is a stable rendering of that table plus an old-file-SHA to new-file-SHA correction table; it has no return, performance, or checkpoint values.

The exact metadata-only verifier is `ops/r3/tests/test_sol_audit_wp3_provenance.py::test_wp3_provenance_index_and_report_contract`, run with `python -m pytest -q ops/r3/tests/test_sol_audit_wp3_provenance.py -p no:cacheprovider`. It parses the index/report, checks the key set and types above, 40-hex/hash-source equality, list order and disposition values, report/index identity-table agreement, authoritative amendment/map/manifest hashes, and the three guard values (`outcome_values_accessed=false`, `final_holdout_status=UNTOUCHED`, `r2b2_status=NOT_STARTED`). Correct only demonstrably stale live references and preserve stale receipts/roots byte-for-byte.

## A09 membership label

Modify `scripts/aggregate_r2a2.py` and its tests/reporting so the frozen
Top50-input campaign labels its Top100 diagnostic
`TOP50_MEMBERSHIP_SUBSET_DIAGNOSTIC`, never `TOP100_UNIVERSE`. Derive the input
scope from the registry's explicit `cohort` column when present and use the
campaign's fixed Top50 scope only for the legacy registry that has no column;
mixed/unknown scopes are fail-closed. Put the label in every cohort CSV row,
the aggregate manifest, and a deterministic human-readable aggregate report.
Keep the historical six-thousand-unit arithmetic and all trial/fold counts
unchanged. Tests use only temporary synthetic fixtures and never a canonical
outcome/checkpoint root. Normalize registry `cohort` to exactly `top20`,
`top50`, or `top100`; an absent column means the fixed legacy input scope
`top50`, while empty, mixed, or unknown values fail closed before writing.
The label is required in every row of `cohort_diagnostics.csv`,
`cohort_summary.csv`, and `symbol_cohort_summary.csv` as `membership_label`,
in `aggregate_manifest.json` as `input_membership_scope` and
`top100_membership_label`, and in deterministic `aggregate_report.md` sections
Input membership scope, Diagnostic labels, Unit/trial arithmetic, and
Reproducibility. The report contains no timestamps/outcomes and is added to
the generated artifact hash allowlist; arithmetic remains unchanged.

## A10 immutable outputs

Modify `src/binance_research/reporting.py`, `src/binance_research/registry.py`,
and archive-revision writer to use exclusive immutable writes. Expose
`write_immutable_bytes`/`write_immutable_text` in reporting: reject symlink
destinations, create parents, use `xb` plus flush/fsync, compare existing bytes
on `FileExistsError`, and make identical bytes idempotent while differing bytes
raise before mutation. `ArtifactWriter.write_tables` uses them for every fixed
artifact; `write_report` uses deterministic serialization and a supplied origin
date or `NOT_SPECIFIED`, never a live clock.

`canonical_experiment_identity(record_or_mapping)` serializes the complete
experiment record as compact sorted JSON after excluding only `timestamp` and
returns SHA-256. `ExperimentRegistry.append` scans existing JSONL records;
same experiment id or identity is idempotent only when canonical bytes match,
otherwise `immutable experiment identity collision` is raised with bytes
unchanged. New records append one line through `ab` + flush/fsync.

`append_archive_revision` treats `(archive_url,new_sha256)` as the immutable
key, checks exact duplicates before mutation, rejects conflicting rows, and
appends only a new CSV row (header only for a new file), preserving every prior
byte. Add synthetic tests for repeats, prefix preservation, symlink rejection,
and collision failures for all three writer paths.

## A11 portability

Repair default config/path resolution to be repository-root independent using
the package repository root, make default raw/forward paths absolute to that
root, align pytest discovery with `tests` plus `ops/r3/tests`, and pin the
supported Python/dependency invocation in the project metadata. Add a subprocess
smoke test from an unrelated cwd. Do not commit virtualenv, cache, raw, Parquet,
or chmod noise. Concretely, `src/binance_research/cli.py` must define
`REPO_ROOT = Path(__file__).resolve().parents[2]`; `_load_config(None)` uses
`REPO_ROOT / "configs/core.toml"`, and download raw-root plus collect and
collect-liquidations output defaults are absolute under that root. Explicit
arguments retain their documented meaning. `pyproject.toml` testpaths are
exactly `tests` and `ops/r3/tests`. Add `docs/REPRODUCIBLE_RUNTIME.md` with
supported Python `>=3.11`, canonical invocation
`python -m pytest -q tests ops/r3/tests -p no:cacheprovider`, and supported
install command `python -m pip install -e ".[dev]"`; tests include an
unrelated-cwd subprocess help smoke test that touches no data.

## Deliverables and classification

Update only the canonical text/manifests where identity reconciliation proves
the change. The durable report classifies each diff as
`MERGE_SAFE_NONSCIENTIFIC`, `FUTURE_HARNESS_REPAIR`, or
`R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED`; no merge or V9 migration is performed.
