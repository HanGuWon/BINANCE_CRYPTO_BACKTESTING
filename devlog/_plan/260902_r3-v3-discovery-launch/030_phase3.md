# 030 — Phase 3 (r3-v3-discovery-launch)

> DIFFLEVEL-ROADMAP-01: write this doc to full diff-level precision (exact paths,
> NEW/MODIFY/DELETE, before/after diffs) BEFORE P -> A. An empty scaffold does not
> satisfy the rule; the A-phase reviewer FAILS outline-only phase docs.

## MODIFY / NEW / DELETE map

No scientific source changes after parity. Use only
`D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v3`
and `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\engineering_shadow_september_launch_v3`.
Run the existing explicit production command; it writes stage receipts,
`august_source`, frozen September ranking and `campaigns/r3_prospective_context_v1/rosters/2026-09.json`,
shadow evidence, launch manifest/seal, and keeps the scientific root fresh.
Conflicting non-empty roots/roster fail closed; no overwrite or mid-launch patch.

## TESTS

Existing `tests/test_r3_production_wiring.py`, `tests/test_r3_forward_ranking.py`,
and `tests/test_r3_universe.py`; operational checks inspect only metadata/health,
not returns or performance.

## Verification (C)

After parity PASS, freeze branch/HEAD/source-tree/registry/contract hashes and
run `python scripts/prepare_r3_post_boundary_launch.py --execute-production
--control-root "D:\\BINANCE_CRYPTO_BACKTESTING_DATA\\r3_prospective_context_v1\\launch_control\\2026-09-production-v3"
--raw-root "D:\\BINANCE_CRYPTO_BACKTESTING_DATA\\raw"
--shadow-root "D:\\BINANCE_CRYPTO_BACKTESTING_DATA\\r3_prospective_context_v1\\engineering_shadow_september_launch_v3"`.
Require calibrated Binance UM time >= `2026-09-01T00:00Z`, exact Top50, shadow
PASS, manifest and fsynced seal. Any blocker stops without retrying with another
root unless a new versioned identity is explicitly created.
