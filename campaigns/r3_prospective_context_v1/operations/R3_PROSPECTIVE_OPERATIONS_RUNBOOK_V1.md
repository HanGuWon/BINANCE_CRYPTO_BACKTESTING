# R3 v8 prospective collection operations runbook

This is an operations document for the already sealed September v8 collector.
It does not amend the scientific protocol or change the meaning of H01–H06.
The raw scientific root, manifests, roster, registry, and frozen implementation
are immutable evidence.

## Frozen identity

| item | value |
| --- | --- |
| branch | `research/r2b-restricted-derivatives-v1` |
| frozen implementation | `ecebc49dff41eeec33af62c2c85a75c5a0bd2922` |
| source-tree SHA256 | `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688` |
| registry SHA256 | `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a` |
| scientific root | `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8` |
| launch manifest SHA256 | `cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659` |
| launch seal SHA256 | `ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85` |
| roster | September 2026, SHA `bb05514dfc78cfca3b736488b1454f4cb022da0110e2cbf69f53c505f543ea79` |

The current live command must continue to name this root, roster, manifest, and
the existing Python environment. A source-scope change in `scripts`, `src`,
`tests`, or `configs` blocks launch until a new identity is explicitly sealed.

## Service start and authorized resume

Run from an elevated or ordinary user PowerShell as appropriate for the local
Task Scheduler registration:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  "C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트\ops\r3\launch_r3_v8_resume.ps1"
```

The launcher performs the v8 manifest/seal/source/registry/roster preflight,
requires the existing `raw_v1` directory, and then invokes only:

```text
C:\Users\user\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe
  scripts\run_r3_prospective_collector.py --mode SCIENTIFIC --persistent
  --root D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8
  --roster-artifact campaigns\r3_prospective_context_v1\rosters\2026-09.json
  --launch-manifest D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json
```

`PYTHONPATH` is set only for the child process to the already installed local
Hermes dependency site-packages; no credentials or private API is used. The
existing `scientific_raw_v8\control\collector.lock` is the sole writer lock.
The launcher is synchronous so that lock lifetime covers the collector. A
second invocation returns `COLLECTOR_LOCK_COLLISION` (exit code 73) and does not
start a second writer. It never creates a new root or bypasses a seal.

The preferred Task Scheduler registration is provided by
`ops/r3/register_r3_v8_task.ps1` and the sanitized XML template. On this host,
both `Register-ScheduledTask` and `schtasks /Create` were attempted with the
current user token and returned `Access is denied`; no task was created. As a
native, credential-free fallback, `ops/r3/install_r3_v8_startup.ps1` installs
the user Startup shortcut
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\R3-Prospective-Scientific-v8.lnk`.
It targets the same launcher, runs at logon, and is validated without stopping
the live collector. If Task Scheduler permission is later granted, register
the named task and remove the fallback only after `Get-ScheduledTask` and
`Get-ScheduledTaskInfo` show the expected identity and `IgnoreNew` policy.

The phase-3 qualification receipt is written by
`ops/r3/qualify_r3_v8_service.py`; it records the Task Scheduler denial,
Startup fallback validation, collision result, safe-skip restart decision, and
the outcome-blind storage/watchdog evidence.

## Watchdog and staleness

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  "C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트\ops\r3\watch_r3_v8.ps1"
```

The watchdog reads only process metadata, the cycle-metadata stream, health
receipts, manifest-chain metadata, launch identity/seal, gap counters, source
availability timestamps, and filesystem capacity. It does not open market
payload streams or outcome/performance materializations.

Cycle eligibility is evaluated in calibrated UTC. With a 15-minute grid and a
fixed 120-second grace:

* GREEN: live authorized writer, sealed identity and valid chain, no overdue
  boundary beyond grace, and projected free capacity of at least 30 days.
* YELLOW: one late/missing boundary, a reported source/restart gap, or 7–30
  projected days of free capacity while evidence remains append-only.
* RED: dead collector, duplicate writer, broken chain/seal/identity, two or
  more consecutive missing boundaries, expired roster, or less than 7 projected
  days of capacity. RED never deletes or rewrites evidence.

## Failure and gap semantics

| condition | response |
| --- | --- |
| process crash or machine reboot | authorized resume only; preserve an explicit `RESTART_GAP`; resume at the next future absolute boundary |
| network outage/reconnect | retain source/poll/reconnect gap records; never fabricate observations |
| rate limit or source outage | preserve the failure and gap category; no synthetic replacement |
| identity, chain, or seal mismatch | do not launch; escalate as a blocked identity |
| multiple writer | do not launch a second collector; audit the complete process tree before any intervention |
| raw or manifest damage | stop and preserve the v8 root; never compact, delete, or rewrite in this runbook |

## Daily operations receipt

Append one UTC record per day outside `raw_v1`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  "C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트\ops\r3\write_r3_daily_receipt.ps1"
```

The append-only file is
`campaigns/r3_prospective_context_v1/operations/R3_V8_DAILY_OPERATIONS_RECEIPTS.jsonl`.
It is guarded by a separate operations PID lock, flushed and fsynced per line,
and rejects duplicate UTC dates. Each record repeats implementation,
source-tree, registry, roster, launch-manifest and seal identities; first/last
cycle metadata; expected/observed/missing cycle counts; gap/reconnect counts;
chain/seal checks; process identity; raw byte growth; free disk; watchdog state;
and `outcomes_accessed=false`. No returns, PnL, signal accuracy, or other
performance field is permitted.

## Safe restart qualification

The production v8 process is not stopped by default. First qualify launcher
collision and authorized-resume behavior on an isolated fixture. If a live
restart is ever explicitly authorized, stop gracefully, verify the process is
absent, invoke the same launcher, require a `RESTART_GAP`, require no duplicate
cycle ID, and wait for two new real cycles with chain/seal still valid. If that
would endanger immutable evidence, record `SAFE_SKIP_LIVE_RESTART` and leave
the collector running.

## October rollover

At `2026-10-01T00:00:00Z`, the September roster expires. Without a separately
sealed October roster the collector must suspend and write
`UNIVERSE_ROLLOVER_GAP`; it must not continue September membership and this
runbook does not create an October roster now. After September closes:

1. perform month-scoped September discovery;
2. verify complete prior-month candidates;
3. rank with the frozen method;
4. freeze and replay the October Top50 roster;
5. build and seal the rollover authorization;
6. resume from the next future boundary.

No September return or performance result may affect October membership.

## Scientific boundary

Evaluation remains `NOT_YET_AUTHORIZED`; outcomes are `NOT_STARTED`; R2B2 is
`NOT_STARTED`; the final holdout is `UNTOUCHED`. Do not inspect future returns or
performance artifacts while operating this service.
