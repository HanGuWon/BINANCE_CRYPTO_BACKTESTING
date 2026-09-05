# R3 Evaluation Amendment V2 — Diff-Level Roadmap

## Loop-spec header

- **Archetype:** spec-satisfaction repair with an outcome-blind governance boundary.
- **Trigger:** V1 is blocked because no horizon is frozen and its lifetime
  `missing_cycle_count == 0` completeness rule conflicts with legitimate,
  explicitly recorded gaps.
- **Goal:** freeze one native 15-minute horizon, repair the metadata-only
  readiness contract, and leave evaluation locked while collection continues.
- **Non-goals:** no R3 response/return materialization, no historical labels,
  no performance calculation, no holdout/R2B2 access, no v8 source or root rewrite,
  no alternative horizon comparison, and no scientific collector edits.
- **Verifier:** focused `pytest` for `ops/r3/tests`, JSON/TOML/hash checks,
  live `r3_ops.py watch --exact-v8` with the Hermes dependency path, and final
  Git/source-scope checks. The verifier reads the changed governance/ops files
  and metadata only; it never reads response values.
- **Stop condition:** all five work-phases are committed, focused tests pass,
  source/registry/root identities remain frozen, the live writer is one and the
  sealed collector is running, and readiness is
  `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES` with minima unmet.
- **Memory artifact:** this roadmap, its numbered phase documents, the cxc loop
  goalplan, and timestamped V2 inventory/readiness receipts.
- **Expected terminal outcomes:** `DONE` when all gates pass; `BLOCKED` only for
  an external causal-data or live-identity failure; `UNSAFE` if a requested
  action would stop/rewrite the sealed collector; `NEEDS_HUMAN` only if the
  explicitly supplied 15m authorization is insufficient; `NOOP` is not expected;
  `BUDGET_EXHAUSTED` is not permitted without a recorded resource bound.
- **Escalation:** if any operation would touch `scripts`, `src`, `tests`, or
  `configs` in the sealed scientific identity, stop before editing and report the
  identity conflict; if the live collector is dead, use only the existing
  authorized resume launcher and preserve a restart gap.
- **HOTL bounds:** use only local PowerShell/Python, the existing Hermes runtime,
  D-backed v8 metadata, and repository governance paths; no external credentials,
  no external upload, no new root; bounded commands are 30 seconds for focused
  tests/watch probes and the foreground collector is managed as one long-running
  session. No historical outcome command is allowed.

## Current evidence and conventions

- Repository root: `C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트`.
- Branch/identity at planning: `research/r2b-restricted-derivatives-v1`,
  HEAD/origin `5bbd08c472f52f1239c974faa9a0a1a93d6e0aa1`, frozen implementation
  `ecebc49dff41eeec33af62c2c85a75c5a0bd2922`, source SHA
  `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688`, registry
  SHA `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a`.
- v8 root is `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8`.
- Existing operations-only owners are `ops/r3/check_r3_evaluation_readiness.py`,
  `ops/r3/build_r3_evidence_inventory.py`, and
  `ops/r3/tests/test_evaluation_readiness.py`; their direct consumers are the
  campaign spec and timestamped operations receipts.
- Existing style is append-only timestamped JSON/JSONL under
  `campaigns/r3_prospective_context_v1/operations`, numbered devlog docs under
  `devlog/_plan`, and stdlib-only operations tooling. No new dependency or
  parallel helper module is planned.
- `cxc map .` was attempted and unavailable in this checkout; the fallback
  structure evidence is the directory listing plus `rg --files` and direct reads
  of each owner/consumer above.

## No-code options rejected

1. **Do nothing:** rejected because the current checker cannot map timestamped
   gaps, permanently fails legitimate missing cycles, and cannot accredit the
   verified September roster.
2. **Configuration-only change:** rejected because the gap-to-block and roster
   rules require executable metadata logic and tests.
3. **Reuse V1 unchanged:** rejected because V1 must remain immutable evidence and
   is internally inconsistent for the current live gap state.
4. **Scientific-source edit:** explicitly excluded; governance remains in `ops/r3`
   and campaign docs so the sealed implementation/source-tree identity is stable.

## Dependency-ordered work-phase map

| Phase | Diff-level document | Scope and activation scenario | Verifier | Output |
| --- | --- | --- | --- | --- |
| `wp0-roadmap` | this file | Reverify branch, identity, live writer, and V1 SHA; write all phase docs before implementation. | `git` identity checks, Hermes `r3_ops.py watch --exact-v8`, V1 `Get-FileHash`. | Locked roadmap and current-state evidence. |
| `wp1-contract` | `010_contract.md` | Create immutable horizon JSON and V2 amendment; update governance pointers; activation is a V2 parser/checker fixture with one horizon. | JSON/TOML parse, SHA checks, focused contract tests. | V1 supersession note, horizon artifact, V2 amendment and reproducibility manifest. |
| `wp2-checker` | `020_checker.md` | Replace aggregate gap subtraction with timestamp/range-to-UTC-6h mapping and verified roster accounting; activation fixtures cover each gap class and invalid identity. | `pytest ops/r3/tests` plus forbidden-field import/read firewall. | Fail-closed readiness implementation and metadata-only tests. |
| `wp3-inventory` | `030_inventory.md` | Extend inventory with explicit gaps/blocks, raw vs primary-eligible counts, verified roster months, and V2 report/receipts; activation is current D-backed metadata run. | Builder/checker commands against sealed root, receipt schema/hash checks. | Versioned V2 inventory, readiness receipt, and accrual report. |
| `wp4-verification` | `040_verification.md` | Run focused tests, recheck live collector, prove scientific scope clean, commit and push intentional governance/ops files. | Focused pytest, `r3_ops.py watch --exact-v8`, Git 0/0 and source/registry hashes. | Final synchronized branch and exact readiness state. |

## Planned file change map

- **NEW:** `campaigns/r3_prospective_context_v1/R3_EVALUATION_HORIZON_V1.json`;
  `R3_EVALUATION_AMENDMENT_V2.md`;
  `R3_EVALUATION_AMENDMENT_V2_REPRODUCIBILITY_MANIFEST.json`;
  `operations/R3_EVALUATION_READINESS_V2_<timestamp>.json`;
  `operations/R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_V2_<timestamp>.json`;
  `reports/R3_EVIDENCE_ACCRUAL_V2.md`; numbered metadata-only tests/fixtures if
  existing test owners do not cover the required cases.
- **MODIFY:** `ops/r3/check_r3_evaluation_readiness.py` and
  `ops/r3/build_r3_evidence_inventory.py`; `ops/r3/tests/test_evaluation_readiness.py`;
  `campaign_spec.toml`, `R3_PROTOCOL.md`, `metrics_contract.md`,
  `multiple_testing_plan.md`, and `promotion_policy.md` only where V2 pointers
  and state taxonomy must be synchronized; `R3_CANONICAL_STATE_INDEX.json` and
  `reports/R3_CURRENT_STATE.md` only as current metadata surfaces.
- **PRESERVE byte-for-byte:** `R3_EVALUATION_AMENDMENT_V1.md`, all prior V1
  inventories/readiness receipts, sealed D-backed raw evidence, launch manifest,
  launch seal, roster, implementation source, and registry.
- **DELETE:** none. No raw archive, Parquet, cache, `.codexclaw`, holdout, or
  historical receipt is deleted.

## Conditional-path activation and bypass records

| Path | Activation scenario | Tier / executing surface | Known bypass | Residual risk / wording |
| --- | --- | --- | --- | --- |
| Gap block exclusion | Synthetic metadata has two gaps in one 6h block and one spanning a boundary; receipt lists each block once. | E6, `check_r3_evaluation_readiness.py` + tests | A caller can bypass the CLI by importing the pure function; tests and final review are the enforcement boundary. | Runtime is fail-closed for supplied metadata; call it a contract gate, not tamper-proof isolation. |
| Roster accreditation | Fixture supplies verified September hash/replay, duplicate September, then September+October. | E6, checker CLI | Caller can pass no roster path; live CLI derives/validates the artifact and missing accreditation remains a failed gate. | Filename-only claims are rejected; wording remains “verified metadata”. |
| Forbidden-field firewall | Fixture injects `future_return`, forbidden path token, holdout, or R2B2 key; checker raises before counting. | E7, `_reject_forbidden` and tests | Direct filesystem access outside checker is outside scope. | It is metadata-only enforcement, not a filesystem sandbox. |
| Current-live inventory | `build_r3_evidence_inventory.py` reads only D-backed raw envelopes/health metadata and writes a new timestamped path. | E6, inventory CLI | Existing output path refusal prevents overwrite; a user can run another process, but no data is rewritten. | Append-only receipt and source identity checks preserve provenance. |

## Acceptance checklist

1. V1 SHA is recorded and V1 is classified `SUPERSEDED_PREREGISTRATION_BLOCKED`;
   no V1 bytes change.
2. Horizon JSON has exactly one primary native 15m/one-bar key and no alternatives;
   symbolic response interval is `[T_exec, T_exec + 15m]` and equality at the
   executable open is rejected.
3. V2 retains exactly H01–H06, Holm six-family alpha 0.05, UTC 6h primary blocks,
   NW lag 0, strict causal boundary, explicit censoring, and no lifetime
   `missing_cycle_count == 0` requirement.
4. Every timestamped gap maps to exact UTC 6h block IDs; duplicate/integrity
   defects fail closed; affected blocks are excluded once; raw counts remain
   descriptive and primary counts exclude ineligible blocks.
5. Verified roster artifacts accredit one September month, deduplicate identities,
   and reject invalid hash/replay; the minimum remains two.
6. Focused tests exercise all ten required gap/integrity cases, five roster cases,
   horizon firewall, state taxonomy, and no outcome import/read.
7. Current live metadata produces a versioned V2 inventory/readiness receipt and
   `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`; evaluation is never invoked.
8. Final watch has one writer and alive lock, chain PASS, seal SEALED, root/source/
   registry unchanged; Git scientific scope is clean and remote is synchronized.
