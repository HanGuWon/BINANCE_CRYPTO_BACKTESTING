# 010 — Phase 1: visibility and process census

## Scope

WP0–WP1 only. Establish that the repository, D: raw root, launch-control root, process table, disk, clock, and timezone are reachable; then independently enumerate all relevant processes by command line. No recovery launch occurs in this phase.

## MODIFY / NEW / DELETE map

- NEW: `campaigns/r3_prospective_context_v1/operations/R3_V8_RECOVERY_VISIBILITY_CENSUS_20260909.json`, containing command strings, exit codes, canonical cwd, path existence, disk state, UTC/local clock, process rows, and `outcomes_accessed: false`.
- MODIFY: none.
- DELETE: none.

## Exact census and activation conditions

- Run `Get-CimInstance Win32_Process` with a literal command-line filter for `run_r3_v8_guardian.ps1`, `r3_v8_guardian`, `launch_r3_v8_resume.ps1`, and `run_r3_prospective_collector.py`; exclude the census shell itself. Activation is a matching command line, not a stale receipt or lock.
- Count canonical exact-v8 collector candidates, guardian candidates, wrappers/parents, and hidden duplicates. Record PID, parent PID, executable, command line, creation time, and exit/availability result.
- If the host or control plane cannot be reached, write the receipt with the failed command and stop as `R3_V8_RECOVERY_BLOCKED_HOST_OR_CONTROL_PLANE_UNAVAILABLE`.

## Verification

- `Test-Path` for repository, raw root, launch-control root, manifest, seal, and roster: exit `0` for each required path; receipt reads each path directly.
- `Get-CimInstance Win32_OperatingSystem`, `Get-Date -AsUTC`, `Get-TimeZone`, and `Get-Volume`: exit `0`; disk must not be RED.
- `python ops\r3\r3_ops.py watch --exact-v8`: exit `0`; the JSON is retained as a fresh RED/YELLOW/GREEN observation and is not relabeled as PASS.

## Acceptance

The phase passes only when all visibility commands are reachable and a fresh census (including zero-process and duplicate-process cases) is stored. A lock file alone cannot satisfy a process count.

