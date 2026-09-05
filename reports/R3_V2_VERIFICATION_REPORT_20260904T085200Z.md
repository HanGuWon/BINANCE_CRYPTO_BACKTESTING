# R3 V2 outcome-blind verification — 2026-09-04

This report records the final governance/metadata verification for the V2
evaluation amendment. No R3 outcome, return, label, final-holdout, R2B2, or
performance value was read.

| Field | Verified value |
|---|---|
| branch | `research/r2b-restricted-derivatives-v1` |
| HEAD / origin | `555d51ef3d71682ef2331eb18a987c8af0d7a72c` / same |
| ahead / behind | `0 0` |
| frozen implementation | `ecebc49dff41eeec33af62c2c85a75c5a0bd2922` |
| scientific source-tree SHA256 | `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688` |
| registry SHA256 | `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a` |
| V1 amendment SHA256 | `27276b4d3b66d25c987fadbac531df3cfd741dbd43625406fdc342e89c2f1c39` |
| V1 disposition | `SUPERSEDED_PREREGISTRATION_BLOCKED_NOT_INVALID_OUTCOME_EVIDENCE` |
| V2 amendment SHA256 | `8f12263c107e8b1fb2596c72f5c3e0c741a17339a42f95aab67df86b87738c38` |
| V2 reproducibility manifest SHA256 | `ee840ad17dfaf246991f758d6420fd790f8bfcfaa0279ef4d2626ed5d93543a7` |
| horizon key / interval / bars | `R3_HORIZON_15M_NEXT_NATIVE_BAR_V1` / `15m` / `1` |
| alternative horizons | `[]` |
| horizon SHA256 | `f5935e6d17e78a21cb575ad65ac6a3523234414d12d657cf13267d30e745342e` |
| source-availability rule | native close or derived maximum constituent close `<` next executable open; equality rejected |
| response interval | symbolic `[T_exec, T_exec + 15m]` |
| mark-price substitution | forbidden |
| causal root | `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8` |
| launch manifest / seal | `cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659` / `ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85` |
| latest inventory | `R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_V2_20260904T084622Z.json` |
| observed cycles | `124` |
| raw / eligible UTC 6h blocks | `9` / `2` |
| explicit gap records | `25`; restart gaps are preserved and block-mapped |
| gap policy | no imputation/backfill; multiple gaps in one block exclude once; spanning gaps exclude both blocks |
| strict-boundary rejects | `0` |
| completeness | PASS; duplicate cycles `0`; missing-cycle counter explicitly accounted; no imputation |
| verified roster months | `1` (`2026-09`); minimum `2` not yet met |
| calendar days | `3` / required `30` |
| H01 / H02 | `50` / `50` (each below `5000`) |
| H03 / H04 | `9194` / `9194` (each above `1000`) |
| H05 / H06 | `50` / `100` (each below `5000`) |
| Holm / bootstrap / NW | six hypotheses, alpha `.05`; wild cluster `10000`, seed `1729`; NW lag `0` |
| focused qualification receipt | `R3_V2_FOCUSED_PYTEST_RECEIPT_20260904T084741Z.json` |
| focused test result | `27 passed in 0.83s`, exit `0` |
| exact-v8 watch receipt | `R3_V2_LIVE_WATCH_20260904T084556Z.json` |
| live writer / lock / duplicates | `1` / alive / `[]` |
| live chain / seal / outcomes | `true` / `true` / `false` |
| watchdog state | `YELLOW` solely for recorded restart/missing-cycle history; collector remains active |
| scientific source status | `clean` (`git status --porcelain -- scripts src tests configs` empty) |
| canonical full pytest | existing immutable `331 passed, 1 warning`; no full suite rerun because this V2 verification scope is focused and scientific source is unchanged |
| external semantics evidence | not applicable to this governance-only V2 verification; frozen scientific implementation and signal semantics were not changed |
| outcome status | `NOT_STARTED` |
| final holdout | `UNTOUCHED` |
| R2B2 | `NOT_STARTED` |
| final state | `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES` |

The registry, implementation, root, and horizon identities are unchanged. The
collection remains below readiness minima, so evaluation is not authorized and
the collector must continue under the sealed v8 contract.
