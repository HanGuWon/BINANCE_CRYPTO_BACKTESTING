# 010 — Phase 1 (r3-v8-wp6-closeout-20260907)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

- NEW: `devlog/_plan/260905_sol-audit-independent-attestation-20260905/180_wp6_live_guardian_closeout_20260907.json`
  records the fresh process census, guardian start decision, PID/parent/start
  command, collector PID/lock, and live safety fields.  It is append-only and
  never contains credentials.
- MODIFY: none in `scripts/`, `src/`, root `tests/`, `configs/`, or the sealed
  data root.  The only runtime mutation permitted is starting the one canonical
  `ops/r3/run_r3_v8_guardian.ps1 -Persistent -PollSeconds 300` process when a
  fresh census proves zero guardians.
- DELETE: none.

## TESTS

- Process census excludes the census shell itself and proves exactly one
  guardian authority after the start gate; a second guardian is never started.
- Existing collector PID, parent, command, lock and one-writer state remain
  unchanged; no `Stop-Process` or restart command is allowed.

## Verification (C)

- Read-only PowerShell `Get-CimInstance Win32_Process` census: exit 0, one
  canonical guardian Python module and its wrapper parent, collector still
  present.
- `Test-Path`/`Get-Content` guardian and collector locks: exit 0; guardian lock
  is held, collector lock identifies the same live writer.
- `python -m ops.r3.r3_ops status --root ...scientific_raw_v8`: exit 0 and
  `chain=PASS`, `seal=SEALED`, exact identity, outcome firewall PASS.
