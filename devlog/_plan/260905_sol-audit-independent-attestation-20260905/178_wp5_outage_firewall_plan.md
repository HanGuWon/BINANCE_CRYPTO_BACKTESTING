# WP5 — Outage/recovery receipt, daily operations receipt, and firewall closeout

## Scope

This is an operations-only closeout for the already recovered sealed-v8
collector. It does not start, stop, or restart the live writer and does not
read market payloads, returns, PnL, R2B2, or the final holdout. The exact
firewall enums for this plan are `outcomes_accessed=false`,
`final_holdout=UNTOUCHED`, `r2b2=NOT_ACCESSED`, and
`forceorder_v3_migration=NOT_STARTED`. The safety prerequisite is recorded
separately as `FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED`; no
ForceOrder V3 migration is resumed or started here.

## Frozen identity

* Root: `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8`
* Implementation: `ecebc49dff41eeec33af62c2c85a75c5a0bd2922`
* Scientific source-tree SHA256: `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688`
* Registry SHA256: `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a`
* Roster SHA256: `bb05514dfc78cfca3b736488b1454f4cb022da0110e2cbf69f53c505f543ea79`
* Launch manifest SHA256: `cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659`
* Launch seal SHA256: `ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85`

## Evidence actions

1. Preserve the immutable WP0 anchor
   `devlog/_plan/260905_sol-audit-independent-attestation-20260905/145_recovery_wp0_watchdog_20260907.json`
   (SHA256 `5a0222eb49684ae79afea006c368262727ad88b406f4d50c13138c286b49d8ad`)
   and the WP3 verification anchor. Recompute the boundary assertion as
   `expected_cycle_count - observed_cycle_count = 284 - 197 = 87` and retain
   the exact last pre-outage cycle ID; do not rewrite or delete either anchor.
   The WP3 verification anchor is
   `devlog/_plan/260905_sol-audit-independent-attestation-20260905/175_wp3_verification_20260907.json`
   (SHA256 `b99e7ae8de773b3517a5751d5023b3a41c53115b42d583d88acf419044e67aa9`).
2. Verify the shared append-only daily file
   `C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트\campaigns\r3_prospective_context_v1\operations\R3_V8_DAILY_OPERATIONS_RECEIPTS.jsonl`
   using its canonical lock
   `C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트\campaigns\r3_prospective_context_v1\operations\R3_V8_DAILY_OPERATIONS_RECEIPTS.lock`.
   The canonical append implementation uses an exclusive lock and flushes the
   appended line before release. The lock is short-lived and must be absent
   (no stale append lock) at verification time. Select the unique
   `date=2026-09-07` line, hash that exact line, and require writer=1,
   `lock_alive=true`, `duplicate_writers=[]`, chain PASS, seal SEALED,
   latest cycle, and `outcomes_accessed=false`.
3. Record the absolute path
   `C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트\campaigns\r3_prospective_context_v1\operations\R3_V8_OUTAGE_AND_RECOVERY_20260907_V2.json`
   as the corrected immutable file (the unsuffixed draft is retained as
   superseded evidence) with a closed `schema_version`, source anchor paths
   and hashes, identity block, no-backfill declaration, and body SHA256. Its
   file SHA256 is `3212f220c6ece18cc0a830b8051891f85f0cbf78b7a00aaf7c049e2f602b2e13`
   and body SHA256 is `97eacca30891f2a9c04f4b937a6b2441e66d0e0ad72ffcfd08202f331877a61e`.
   The superseded unsuffixed draft remains preserved with file SHA256
   `796fabfe9fa164de1a9e6ec26b2fb27aaf061a24d9c5187bcd08f26d2d0f1dc4`.
   Its publication contract is `O_CREAT|O_EXCL`, no overwrite, flush+fsync before
   atomic publish, and a canonical body hash. The
   87-boundary gap and the nonqualifying first post-launch target remain
   explicit. Record `UNKNOWN` as the cause because operational evidence does
   not establish a more specific failure class.
4. Record the absolute path
   `C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트\campaigns\r3_prospective_context_v1\operations\R3_V8_FORCEORDER_V3_MIGRATION_CONTINUATION_20260907.json`
   with a closed schema, identity block, body SHA256, and the same
   `O_CREAT|O_EXCL`, no-overwrite, flush+fsync, atomic-publish contract. It
   must carry the exact firewall enums (`outcomes_accessed=false`,
   `final_holdout=UNTOUCHED`, `r2b2=NOT_ACCESSED`,
   `forceorder_v3_migration=NOT_STARTED`) plus the distinct field
   `migration_prerequisite_state=FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED`.
   A separate explicit Goal is required for migration.
5. Run this exact outcome-blind firewall command from the repository root:
   `C:\Users\user\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe -m ops.r3.verify_r3_v8_wp5_firewall --receipt campaigns/r3_prospective_context_v1/operations/R3_V8_WP5_FIREWALL_RECEIPT_20260907_V6.json`
   with `PYTHONPATH` set to
   `C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트;C:\Users\user\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages`.
   The verifier allowlist is exactly the seven absolute paths in its PASS
   output (the two WP5 receipts, the daily JSONL, its canonical append-lock
   path, and WP0/WP2/WP3 anchors),
   and its output schema must be a JSON object with `status=PASS`,
   `daily_date`, `daily_latest_cycle`, `daily_writer_pid`,
   `historical_gap_formula=284 - 197 = 87`, `outcomes_accessed=false`,
   `final_holdout=UNTOUCHED`, `r2b2=NOT_ACCESSED`, and
   `forceorder_v3_migration=NOT_STARTED`. Require exit 0 and record the
   command, allowlist, exit code, stdout/stderr SHA256, and verifier path in
   the bound receipt
   `C:\Users\user\Documents\ChatGPT\BINANCE 지표용 테스트\campaigns\r3_prospective_context_v1\operations\R3_V8_WP5_FIREWALL_RECEIPT_20260907_V6.json`
   (file SHA256 `607a768fdddcdcdcb1c38792ee3f46e802a383905dfc2f805bbb7f9cdf57e89b`,
   body SHA256 `db7575a75dc508c87d3fa02744bac6983827c198c124e6f9c3deac29591ba103`).
   The V6 writer is O_CREAT|O_EXCL plus fsync and atomic hard-link publish,
   and the verifier re-loads the bound V5 file after publication to validate
   its closed schema, body hash, command binding, allowlist, checks, and
   identity. The prior V1 manual receipt and V2/V3/V4/V5 generated receipts are
   retained as superseded evidence and are not the bound result. The verifier
   also asserts the outage claims (284 - 197 = 87, no_backfill=true,
   failure_cause=UNKNOWN, preserved qualifying-cycle IDs), continuation
   claims (migration_action_in_this_goal=NONE and separate authorization),
   and explicit absence fields
   `forward_response_materialization_accessed=false` and
   `forward_response_materialization_present=false`.
   The check must assert no forward-response materialization, no H03/H04
   performance inspection, no R2B2/holdout access, and no scientific-scope
   Git changes. It must not read or grep excluded performance artifacts.
6. Complete WP5 tasks and criterion c-5 only after the receipt hashes, daily
   line hash, WP0 gap formula, exact identity comparison, and live
   single-writer metadata check pass.

## Acceptance

* No new scientific bytes, roster, launch seal, or manifest history are
  changed.
* The live collector remains one authorized writer with an alive lock,
  duplicate writers empty, chain PASS, and seal SEALED.
* Historical missingness is preserved and no backfill is attempted.
* `outcomes_accessed=false`, final holdout is `UNTOUCHED`, R2B2 is
  `NOT_ACCESSED`, and ForceOrder V3 migration is `NOT_STARTED` (paused).
* Final state is
  `R3_PROSPECTIVE_COLLECTION_RECOVERED_WITH_PRESERVED_GAP` plus
  `FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED`.
