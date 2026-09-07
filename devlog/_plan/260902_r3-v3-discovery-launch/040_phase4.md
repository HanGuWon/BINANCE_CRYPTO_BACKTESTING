# 040 — Phase 4 (r3-v3-discovery-launch)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

No source changes. Production writes
`D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v1`
operational raw/health/manifest-chain files and appends
`R3_PROSPECTIVE_COLLECTION_ACTIVATION_RECEIPT.json` under the v3 control root.
The collector command is the existing `run_r3_prospective_collector.py` with
`--mode SCIENTIFIC --persistent`, bound to the sealed v3 manifest and September
roster. Leave the collector running after verification.

## TESTS

Use `_probe_scientific_evidence`/manifest-chain and health validators. Verify at
least two completed 15-minute SCIENTIFIC cycles, roster/manifest/seal bindings,
calibrated timing, reconnect/gap metadata, and no shadow contamination. Never
read future returns, PnL, Sharpe, hit rate, H01-H06, holdout, or R2B2.

## Verification (C)

Poll the persistent collector and inspect only `cycle_metadata`, manifest-chain,
and health receipts. Require `cycles_completed >= 2`, `manifest_chain_pass=true`,
`health_pass=true`, and process still running. Run the final R3 pytest suite and
scoped Git status; emit an activation receipt and final report. Expected exit 0;
otherwise stop as `R3_BLOCKED_SEPTEMBER_SHADOW` or
`R3_BLOCKED_LAUNCH_IDENTITY` with preserved evidence.

## Completed v8 evidence (2026-09-02 KST)

- Control root: `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8`
- Scientific root: `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8`
- Persistent collector: one parent/child process tree (PIDs 158632 -> 153760), both invoking the same SCIENTIFIC command and root.
- `cycle_metadata.jsonl`: 9 completed 15-minute cycles; latest completion `2026-09-02T10:51:54.384023+00:00`.
- `health_receipts.jsonl`: 9 records; latest manifest SHA `543890722983eaabffbb837fc9a68061082117d4c0a03f9e313d0735bf71ae44`.
- `verify_manifest_chain`: `True`; `verify_launch_seal`: `SEALED` (launch manifest SHA `cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659`).
- All cycle and health envelopes carry `evidence_mode=SCIENTIFIC`; no shadow or outcome data was read.
- Scoped scientific Git status (`scripts src tests configs`): clean.
