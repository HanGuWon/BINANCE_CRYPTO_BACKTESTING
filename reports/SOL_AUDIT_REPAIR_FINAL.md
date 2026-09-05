# SOL audit repair — final outcome-blind closeout

**Read window:** 2026-09-05 KST  
**Branch:** `codex/sol-audit-repair-v1`  
**Implementation commit (executable source):** `6b5e5c5d5c49a17583c269d10e34c0b5e92534a2`  
**Execution source-tree SHA-256:** `ad3130626cd661274ba96488d7b0998bf021a433b84af7c0801e41b1cae80163`  
**Scientific source status:** clean at qualification; final report/receipts are metadata-only additions.  
**Final state:** `SOL_AUDIT_REPAIR_BRANCH_VERIFIED_READY_FOR_MIGRATION_REVIEW`

## Boundary and disposition

This branch is an isolated repair branch created from canonical
`research/r2b-restricted-derivatives-v1` at baseline
`9e532aeea014547283776b1728b2222ae1622fad`. No merge, push, v9 migration,
historical R2B/R3 outcome run, return calculation, checkpoint-trade read, or
final-holdout read was performed. The active v8 collector and its raw root
remain read-only and untouched. R3 outcomes remain `NOT_STARTED`; final
holdout remains `UNTOUCHED`; R2B2 remains `NOT_STARTED`.

The original full pytest command was executed with the explicit
`SOL_AUDIT_OUTCOME_BLIND=1` boundary and a Python audit hook that rejects any
open under the D-backed R2A/R2B/R3 raw or checkpoint roots. The one existing
historical checkpoint regression node is explicitly skipped in that mode. The
static allowlist records that node as blocked when the safety mode is absent;
that is a deliberate guard, not a hidden change to historical conclusions.

## ForceOrder provenance bug

The WP0 metadata-only audit found that the V2 validator treated `ps` as the
position-side enum `{BOTH,LONG,SHORT}` and read `o.ps`, while Binance's merged
UM+CM stream defines `ps` as the pair symbol and `st` as the symbol type. The
primary sources used were [Binance USDⓈ-M WebSocket market-stream
documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market)
and [Binance COIN-M market-stream
documentation](https://developers.binance.com/en/docs/catalog/derivatives/coin-margined-futures/websocket-market-streams/Live-Subscribing).

Metadata-only census: 748 liquidation JSONL files, 51,236 events, UM `50,864`,
CM `372`, malformed `0`, contradictory top-level/nested values `0`. V2 bytes
are preserved; the corrected parser, normalizer, matrix, and adapters are
versioned V3 and classified `R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED`. No V3
launch or outcome is authorized by this branch.

## Repair classifications

| Finding | Classification | Disposition |
| --- | --- | --- |
| A02 readiness fail-closed; A04 strict next-open embargo; A05 short/equity accounting; A06 periodic Deflated Sharpe inputs; A07 decision-time attribution; A12 arbitrary-index/gap helpers | `FUTURE_HARNESS_REPAIR` | Corrected with synthetic regression fixtures only; no historical conclusions rewritten. |
| A08 provenance reconciliation; A09 Top100 membership labeling; A10 immutable generic outputs; A11 repository-relative runtime/test defaults; qualification guards, receipts, and comparator | `MERGE_SAFE_NONSCIENTIFIC` | Metadata, portability, and integrity changes; v8 scientific identity is not changed. |
| ForceOrder V3 schema/identity/parser/adapter | `R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED` | Required because the V2 `ps` interpretation is materially wrong; V2 remains immutable. |

## Canonical v8 identity and stale roots

The read-only WP0 identity index records active v8 as:

- root: `D:/BINANCE_CRYPTO_BACKTESTING_DATA/r3_prospective_context_v1/scientific_raw_v8`;
- implementation: `ecebc49dff41eeec33af62c2c85a75c5a0bd2922`;
- source-tree SHA-256: `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688`;
- registry SHA-256: `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a`;
- launch-manifest SHA-256: `cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659`;
- seal SHA-256: `ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85`;
- status: `CURRENT_FROZEN`.

The stale `raw_v1`/old launch identity remains `INVALID_SUPERSEDED` or
`BLOCKED`; it was not resumed. The V2 ForceOrder matrix SHA-256 is
`31802e1e09c6b1558cbb0a6938609fe36b15722bb4870ab0656e24ff09de77f6`; the
V3 identity is an append-only successor, not a silent rewrite.

## Registry and qualification

The six-primary registry was not changed by this repair:
`c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a` before
and after. The exact full command was run twice:

```text
python -m pytest -q tests ops/r3/tests -p no:cacheprovider
```

with `SOL_AUDIT_OUTCOME_BLIND=1`, source paths bound to this worktree, and the
runtime D-root deny hook enabled. Both canonical receipts report **435
passed, 4 skipped, 2 warnings**, exit code `0`, and zero runtime guard events:

- `campaigns/r3_prospective_context_v1/operations/SOL_AUDIT_WP4_FULL_PYTEST_RECEIPT_20260905_RUN1.json`
  SHA-256 `83c08df0e40ce6363e2592f34e1611eb81ad7acc449f6580f71f05f7212a46ae`;
- `campaigns/r3_prospective_context_v1/operations/SOL_AUDIT_WP4_FULL_PYTEST_RECEIPT_20260905_RUN2.json`
  SHA-256 `41100e0778215f54bf3e882a3dcdeb5f175fe64b6c947212fc8eb0ee861c2170`.

The four skips are explicit: the historical checkpoint reader under the
outcome-blind boundary, two optional R1-7 artifacts absent from this isolated
source worktree, and Windows symlink privilege. The run comparator reports
`normalized_equal=true`, `verifier_outputs_equal=true`, `exit_codes=[0,0]`,
and `status=PASS` (evidence SHA-256
`ce6e043b9800959f76eb4b1271cb4f425878323424d4c701efde816c6b3d47d9`).

The four contract verifiers (ForceOrder, registry, horizon, inventory) all
passed with metadata-only/root guards. The live metadata guard reports
`process_touched=false`, `raw_root_opened=false`,
`checkpoint_paths_checked=false`, `outcome_values_accessed=false`, holdout
`UNTOUCHED`, and outcomes `NOT_STARTED`.

## Receipt supersession and Git status

The previous `campaigns/r3_prospective_context_v1/full_pytest_receipt.json`
is preserved unchanged (SHA-256
`56c43a22840f609de1512044e89f60899dfc1d909efc934a2acf75f3e6632221`) and is
superseded only by the append-only metadata index
`SOL_AUDIT_WP4_RECEIPT_SUPERSESSION_20260905.json` (SHA-256
`c5a5122b593126025eae7c05bfe67b13e60f5a2d509c2ac4120bb5f51b84f07a`).

Scientific paths (`src`, `scripts`, `ops/r3`, tests, campaign contracts,
docs, and `pyproject.toml`) are clean on this branch. `.codexclaw` runtime
logs/evidence are not committed. No raw archives, Parquet, caches, or
outcome checkpoints were added.

This branch is ready for a human migration review only. It must not be merged
into the active v8 collector or used to start R3/R2B outcomes without a new
scientific identity and a separately approved V3 protocol.
