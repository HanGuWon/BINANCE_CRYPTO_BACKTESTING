# 050 — Phase 5 (r3-v8-wp6-closeout-20260907)

## MODIFY / NEW / DELETE map

- NEW: a CXC test receipt for the broader operations suite and a second receipt
  for the full repository pytest run.  These are local orchestration evidence
  only and are not scientific data.
- MODIFY: only the intentional operations/governance allowlist from WP1–WP4;
  no `scripts/`, `src/`, root `tests/`, `configs/`, raw/Parquet, checkpoint,
  outcome, return, R2B2, or holdout file may be staged.
- NEW: the final closeout receipt under the WP6 devlog plan after the commit,
  recording exact HEAD and all immutable hashes.
- DELETE: none.

## TESTS

- `pytest -q ops/r3/tests` must pass with exit 0.
- `python -m pytest -q` must pass with exit 0; this is a read-only regression
  check and does not authorize any outcome run.
- Re-run receipt/body/file hash checks for V2/V3/V6/V7, continuation V2, the
  standing policy, and the 17-case synthetic qualification.
- Confirm `git status --short -- scripts src tests configs` is empty and
  `git diff --check` passes for every staged path.

## Verification (C)

- Capture each test result via `cxc receipt test`, including command, exit code,
  final summary, implementation/source identity, timestamp, and scientific
  status.
- Before commit, verify one live guardian authority and one collector writer,
  both locks held, chain PASS, seal SEALED, latest cycle newer than guardian
  start, and all outcome/holdout/migration firewall fields unchanged.
- Stage only the explicit operations/governance allowlist and commit once with
  a normal non-force commit.  Do not push from this phase unless the host
  explicitly permits the required network escalation.
