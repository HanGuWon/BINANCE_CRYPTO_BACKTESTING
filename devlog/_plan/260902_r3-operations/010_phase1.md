# 010 — Phase 1: live identity and process audit

## MODIFY / NEW / DELETE

- NEW: outcome-blind audit receipt under `campaigns/r3_prospective_context_v1/operations/`.
- MODIFY: none in `scripts/`, `src/`, `tests/`, or `configs/`.
- DELETE: none.

## Checks and activation scenarios

- Identity drift trigger: load `implementation_commit` from the sealed v8 launch manifest and compare `git diff --name-status <implementation_commit>..HEAD -- scripts src tests configs`; also compare the evidence-only receipt commits `04dcfca..457106a`. Any scientific-scope delta activates `R3_BLOCKED_POST_LAUNCH_IDENTITY_DRIFT`.
- Duplicate-writer trigger: enumerate `Win32_Process` command lines containing the exact v8 root, then bind the lock-file PID to the process tree; an independent second root writer activates `R3_BLOCKED_MULTIPLE_WRITERS`.
- Continued-cycle trigger: record a fresh baseline count/last cycle first, then parse only cycle metadata, health receipts, and manifest chain. Require the next observed count to exceed that baseline (or explicitly record `WAITING_FOR_NEXT_BOUNDARY`), SCIENTIFIC mode, roster/manifest links, and valid chain/seal. No hard-coded count is used.
- Storage baseline trigger: measure D: free bytes and raw/health byte deltas from operational evidence; no payload outcome fields are read.

## Verifiers (run before implementation)

Exact reproducible commands (run from repository root; expected exit code 0) are:

```powershell
$env:PYTHONPATH='src'; @'
from pathlib import Path
from scripts.prepare_r3_post_boundary_launch import _source_tree_sha256
print(_source_tree_sha256())
'@ | python -
git rev-parse HEAD
git rev-parse origin/research/r2b-restricted-derivatives-v1
git merge-base --is-ancestor ecebc49 HEAD
git status --short -- scripts src tests configs
```

The manifest/seal verifier is a complete Python invocation that names its inputs:

```powershell
$env:PYTHONPATH='src'; @'
import json, pathlib
from binance_research.r3_operations import verify_manifest_chain, verify_launch_seal
base=pathlib.Path(r'D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1')
control=base/'launch_control'/'2026-09-production-v8'; sci=base/'scientific_raw_v8'
manifest=control/'R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json'; seal=control/'R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json'
roster=json.loads(manifest.read_text(encoding='utf-8'))['roster_sha256']
assert verify_manifest_chain(sci/'raw_v1'/'manifest_chain.jsonl')
assert verify_launch_seal(seal, manifest, roster_sha256=roster, scientific_root=sci)['seal']['status']=='SEALED'
print('MANIFEST_CHAIN=True LAUNCH_SEAL=SEALED')
'@ | python -
```

The writer verifier must map the lock PID to its complete parent/child tree and
count only the live lock owner as the authorized writer; wrapper processes are
recorded but do not inflate `authorized_writer_count`.

Reproducible writer command (expected exit code 0; it reads only process metadata
and the lock file, never raw payloads):

```powershell
$root='D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8'
$lock=Join-Path $root 'control\collector.lock'
$owner=[int](Get-Content $lock -Raw).Trim()
$all=@(Get-CimInstance Win32_Process)
$byPid=@{}; foreach($p in $all){ $byPid[[int]$p.ProcessId]=$p }
$seen=[Collections.Generic.HashSet[int]]::new(); $stack=[Collections.Generic.Stack[int]]::new(); $stack.Push($owner)
while($stack.Count -gt 0){ $id=$stack.Pop(); if(-not $seen.Add($id)){continue}; if($byPid.ContainsKey($id)){ $parent=$byPid[$id].ParentProcessId; if($byPid.ContainsKey([int]$parent)){ $stack.Push([int]$parent) } ; foreach($child in $all | Where-Object { [int]$_.ParentProcessId -eq $id }){ $stack.Push([int]$child.ProcessId) } } }
$tree=@($all | Where-Object { $seen.Contains([int]$_.ProcessId) })
$tree | Select-Object ProcessId,ParentProcessId,CreationDate,ExecutablePath,CommandLine
$ownerRow=$byPid[$owner]; $cmd=($ownerRow.CommandLine -replace '\s+',' ').Trim().ToLowerInvariant()
$required=@('run_r3_prospective_collector.py','--mode scientific','--persistent','scientific_raw_v8','2026-09.json','r3_prospective_launch_manifest_2026-09.json')
if (($required | Where-Object { $cmd -notlike "*$_*" }).Count -gt 0) { exit 2 }
$authorized=@($all | Where-Object { $line=(($_.CommandLine -replace '\s+',' ').Trim().ToLowerInvariant()); ($required | Where-Object { $line -notlike "*$_*" }).Count -eq 0 })
$outside=@($authorized | Where-Object { -not $seen.Contains([int]$_.ProcessId) })
if ($outside.Count -gt 0) { Write-Error 'independent authorized writer detected'; exit 3 }
Write-Output 'authorized_writer_count=1'
```

The expected output has one lock-owner PID plus every reachable ancestor/descendant
wrapper row; only the lock owner counts toward `authorized_writer_count`. The
required-token check is case-insensitive and insensitive to quoting/order. Any
authorized command outside this recursive tree is an independent writer and fails
the audit.

## Acceptance

Receipt records exact process start times, parent-child relationship, authorized command/root/roster/manifest/seal, lock-owner PID, current baseline cycle/health counts, gaps/reconnects, disk baseline, verifier commands/exit codes, and an explicit `outcomes_accessed=false` field. It repeats the v8 manifest/seal paths and hashes and does not inspect v3-v7 roots.
