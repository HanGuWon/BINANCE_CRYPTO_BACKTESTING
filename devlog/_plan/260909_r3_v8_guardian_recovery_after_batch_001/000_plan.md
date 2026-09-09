# 000 — r3_v8_guardian_recovery_after_batch_001: Plan

Batch 001의 과학적 결과와 high-water는 이미 검증되었고, 이번 단위는 그 결과를 다시 계산하지 않은 채 사망한 exact-v8 guardian/collector를 복구하는 운영 작업이다. 복구 중 누락 구간은 gap으로만 기록하며, 복구 후 두 개의 새로운 미래 cycle과 단일 guardian/단일 writer 상태를 확인한 뒤 Batch 001의 차단 closeout을 supersede한다.

## Loop-spec

- Loop archetype: fail-closed incident recovery and operational hardening.
- Trigger: `c302b70a-f070-43e2-9b5e-56128c9a5ae0/pasted-text-1.txt`의 Batch 001 postcheck 복구 요청.
- Goal: sealed-v8 collection을 미래 시점부터 복구하고, guardian 사망 원인을 근거 기반으로 분류하며, 단일 외부 supervisor 설계를 남긴다.
- Non-goals: Batch 001 재실행/수정, raw-v8 수정, high-water 전진, gap backfill, Batch 002, outcomes/returns/PnL, R2B2, final holdout, live identity·registry·V3 parser 변경.
- Verifier: `ops/r3/r3_ops.py watch --exact-v8`, `launch_r3_v8_resume.ps1 -PreflightOnly`, `run_r3_v8_guardian.ps1 -ValidateOnly`, process/lock census, manifest-chain/seal checks, and synthetic guardian/service tests. Conditional paths name their triggering state in the phase docs.
- Stop condition: two strictly future post-recovery cycles, final live postcheck, failure analysis, one supervisor decision/qualification, firewall, and superseding closeout are all evidenced; otherwise stop in the exact blocked state without inventing recovery.
- Memory artifact: this unit under `devlog/_plan/260909_r3_v8_guardian_recovery_after_batch_001/`, campaign operations receipts, and `.codexclaw/goalplans/recover-dead-r3-v8-guardian-and-collector-after/`.
- Expected terminal outcomes: `R3_V8_GUARDIAN_AND_COLLECTION_RECOVERED_WITH_PRESERVED_GAP`; `R3_V8_COLLECTION_RECOVERED_GUARDIAN_SUPERVISION_HARDENING_PENDING`; `R3_V8_RECOVERY_BLOCKED_HOST_OR_CONTROL_PLANE_UNAVAILABLE`; or `R3_V8_RECOVERY_BLOCKED_IDENTITY_OR_EVIDENCE_FAILURE`.
- Escalation condition: identity mismatch, active/duplicate locks, permission failure, an unsafe supervisor mutation, or any request to access outcomes/holdout requires a stop and user direction. No delegation is planned.

## Current evidence and invariants

- Branch: `research/r2b-restricted-derivatives-v1`.
- Sealed identity: implementation `ecebc49dff41eeec33af62c2c85a75c5a0bd2922`; source tree `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688`; registry `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a`.
- Raw root: `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8`.
- Batch 001 remains verified, immutable, and not replayed. Its scientific root and high-water are outside this change unit.
- The last observed live cycle was `cycle-20260908T071504498269Z`; the current watchdog is RED because both old processes are absent. This is a starting observation, not recovery proof.

## Dependency-ordered work-phase map

| Goalplan phase | Doc | Scope | Depends on |
|---|---|---|---|
| `wp0-roadmap` | `000_plan.md` | Lock this full roadmap and its prohibitions | — |
| `wp1-visibility-census` | `010_phase1.md` | WP0–WP1 host visibility and fresh process census | `wp0-roadmap` |
| `wp2-evidence-outage-locks` | `020_phase2.md` | WP2–WP5 evidence, outage episode, and stale-lock classification | `wp1-visibility-census` |
| `wp3-guardian-recovery` | `030_phase3.md` | WP6–WP9 guardian-first recovery and future-only resume | `wp2-evidence-outage-locks` |
| `wp4-future-observe` | `040_phase4.md` | WP10–WP11 two-cycle observation and live postcheck | `wp3-guardian-recovery` |
| `wp5-failure-supervision` | `050_phase5.md` | WP12–WP17 failure analysis and one external supervisor | `wp4-future-observe` |
| `wp6-closeout-firewall` | `060_phase6.md` | WP18–WP20 supersession, firewall, and closeout | `wp5-failure-supervision` |

## Repository conventions and source-of-truth sync

The repository already uses `devlog/_plan/YYMMDD_slug/` with `000_`, `010_`, … decade documents and campaign operation receipts. This unit reuses those paths; it does not introduce `docs/` or a new runtime package. Operational implementation remains under `ops/r3`; scientific source (`src/`, `scripts/`, root `tests/`, `configs/`) and D-backed data remain unchanged. The operational source of truth is `ops/r3/README.md` plus `campaigns/r3_prospective_context_v1/R3_PROTOCOL.md`; any contract change is patched in the same implementation phase as its verifier.

## Preflighted verifier commands

These commands were run before this plan was written and are real commands that observe the named targets:

- `& .\ops\r3\run_r3_v8_guardian.ps1 -ValidateOnly` — exit `0`; directly reads the guardian wrapper, canonical Python path, standing policy path, and repository root. It validates the launch contract, not live liveness.
- `& .\ops\r3\launch_r3_v8_resume.ps1 -PreflightOnly` — exit `0`; directly reads the D-backed raw root, roster, launch manifest, launch seal, and exact-v8 identity. It may report zero writers; that is not a failure of the preflight contract.
- `python ops\r3\r3_ops.py --help` — exit `0`; exposes `watch`, `preflight`, and `verify-resume-authorization` commands.
- `python ops\r3\r3_ops.py watch --exact-v8` — read-only watchdog; its current result is `RED`, so this is an early-warning observation and not a passing recovery gate.

## Global change map

- NEW: the phase receipts named by `010_phase1.md` through `060_phase6.md` and this plan directory.
- MODIFY: only operations scripts/configuration explicitly selected in `050_phase5.md` after evidence proves a supervisor is available; any modification receives its own test and local commit.
- DELETE: none. Stale locks and prior blocked closeouts are preserved; no raw/data/cache/Parquet or `.codexclaw` content is committed.

