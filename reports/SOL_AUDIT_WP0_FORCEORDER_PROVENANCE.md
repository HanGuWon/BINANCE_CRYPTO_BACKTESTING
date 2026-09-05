# SOL audit — WP0 ForceOrder and provenance report

**Read window:** 2026-09-05 (KST), metadata-only; the append-only collector was
not stopped, restarted, or edited. **Worktree:** `codex/sol-audit-repair-v1`,
baseline `9e532aeea014547283776b1728b2222ae1622fad`. **Boundary:** no outcome,
return, checkpoint-trade, or final-holdout content was opened.

## Decision

The current V2 ForceOrder contract is materially defective. Its validator treats
`ps` as the position-side enum `{BOTH,LONG,SHORT}` while Binance's current
all-market liquidation stream defines `ps` as the pair symbol and `st` as the
symbol type (`1=UM`, `2=CM`). The V2 files remain immutable historical records.
The corrected parser, matrix, and verifier must be versioned as V3 and classified
`R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED`; no V3 launch or outcome run is authorized
by this report.

## Frozen V2 evidence

| artifact | SHA-256 | disposition |
| --- | --- | --- |
| `campaigns/r3_prospective_context_v1/R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL.md` | `ac788de08e77a5eb87b7b5a6619ada104668df3dc00f6908491ee2e1afa79672` | preserve/frozen |
| `campaigns/r3_prospective_context_v1/R3_SOURCE_DEPENDENCY_MATRIX_V2_FORCEORDER.json` | `31802e1e09c6b1558cbb0a6938609fe36b15722bb4870ab0656e24ff09de77f6` | preserve/superseded only by a future V3 |
| `campaigns/r3_prospective_context_v1/R3_SOURCE_DEPENDENCY_MATRIX.json` | `cedb4b0e8c41db89dbe38987f425f27fa0fe6b8d80a675880b870f767bb5ca58` | immutable V1 predecessor |
| `campaigns/r3_prospective_context_v1/trial_registry.csv` | `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a` | six-primary registry |
| `campaigns/r3_prospective_context_v1/R3_EVALUATION_HORIZON_MAP_V1.json` | `7cd935a33ac7ed47d1b9c7e037d5033b3add694934730eca5ebadda48fbb98e5` | six H01–H06 horizon map |
| `campaigns/r3_prospective_context_v1/R3_EVALUATION_AMENDMENT_V2_REPRODUCIBILITY_MANIFEST.json` | `ee840ad17dfaf246991f758d6420fd790f8bfcfaa0279ef4d2626ed5d93543a7` | preserve |

Existing read-only gates all passed: registry verifier exit `0` (six primary
hypotheses), horizon verifier exit `0` (strict six-key map, holdout untouched),
inventory verifier exit `0` (V2 matrix, metadata-only, one scoped gap), and
operations verifier exit `0` (`R3_OPS_C_CHECK=PASS`, seven targeted checks).
The existing V2 ForceOrder test modules passed `20` tests. Explicit collection
of `tests ops/r3/tests -p no:cacheprovider` exited `0` with `396 tests collected`;
this collection is not a qualification of the future V3 parser.

## Official schema evidence

The [Binance USDⓈ-M WebSocket market-stream documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market)
states that, after CM migration, the all-market ForceOrder stream is a merged
UM+CM stream and appends `st` (`1=UM`, `2=CM`) and `ps` (pair symbol). Its field
table identifies `o.o` as Order Type, `o.X` as Order Status, `o.T` as Order
Trade Time, and the example places `ps`/`st` at the top level. The [Binance
COIN-M market-stream documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-coin-m-futures/api/ws-streams/~)
provides the corresponding CM symbol-type contract. These are primary sources;
no repository performance artifact was used.

Current V2 code (`ops/r3/r3_forceorder_identity.py`) instead allowlists
`ps={BOTH,LONG,SHORT}`, reads `o.ps` as `position_side`, and canonicalizes only
UM. This is the direct source of the observed `ps_ENUM_INVALID` classification.

## Live v8 metadata guard

The active process remained untouched:

- root: `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8`;
- lock: `control\collector.lock`, PID `160284`, alive at the read window;
- latest health receipt observed: PID `160284`, `scientifically_eligible=true`,
  `status=CYCLE_COMPLETE`, `gap_count=32`, `restart_count=32`;
- latest manifest-chain metadata: `manifest_id=20260905T020032Z`,
  `manifest_sha256=ba90f4452edaa53283a76b4ec1d4b1ab0b4e7e5b319bfb572c224f37dfd46b14`,
  `previous_manifest_sha256=fa07d141ea50ed31406ca229fcb3ac2558f329a9fb6ed9062333b571c980681f`,
  `total_rows=115159`, `total_bytes=193234793`;
- frozen v8 identity recorded by the existing firewall receipt:
  implementation `ecebc49dff41eeec33af62c2c85a75c5a0bd2922`, source tree
  `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688`, registry
  `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a`, launch
  manifest `cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659`,
  seal `SEALED`, `outcomes_accessed=false`;
- active v8 scientific state remains `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`;
  R3 outcomes are not started and the final holdout is untouched.

## Metadata-only raw census

The scan read only `raw_v1/*/liquidation.jsonl` schema fields. It did not read
prices as outcomes, returns, checkpoints, or holdout content.

| measure | observed |
| --- | ---: |
| liquidation JSONL files | 748 |
| lines/events | 51,236 |
| `e=forceOrder` | 51,236 |
| UM (`st=1`) | 50,864 |
| CM (`st=2`) | 372 |
| streams other than `liquidation` | 0 |
| malformed JSON/envelopes | 0 |
| UM distinct `ps` values | 718 |
| CM distinct `ps` values | 18 |
| order-key shapes | one: `S|T|X|ap|f|l|o|p|ps|q|s|st|z` |
| top-level/nested location | all persisted as nested `o.ps`/`o.st` |
| contradictory top-level/nested values | 0 |

The envelope symbol differs from pair symbol for 75 UM dated-contract records
and all 372 CM records; these are expected contract/pair relationships, not
malformed rows. For example, `BTCUSDT_260925` has pair `BTCUSDT`, and
`AAVEUSD_PERP` has pair `AAVEUSD`.

### A–E classification

Overall classification is **E — mixed**:

- **A (validator/normalizer defect):** all 50,864 UM records carry a pair-valued
  `ps` and therefore cannot satisfy the V2 position-side enum, even though they
  are the accepted UM scientific population.
- **Out-of-scope policy population (not malformed):** 372 CM records are valid
  post-migration records but are outside the V2 UM-only scientific contract;
  they must be routed and explicitly rejected from UM analysis, not silently
  counted as UM.
- **C is the upstream schema context, not a data-integrity failure:** Binance's
  post-CM-migration merged stream adds `ps`/`st`; the repository's persisted
  nested representation is a storage shape that V3 must normalize explicitly.
- **B and D:** no collector corruption or malformed source rows were observed
  in this census (`malformed=0`, no contradictory fields). The collector's
  position-side interpretation is nevertheless part of the V2 semantic defect
  and is repaired only in the versioned V3 adapter.

## Stale/abandoned identity table

| root/receipt | exact implementation | status/disposition |
| --- | --- | --- |
| V1 matrix `R3_SOURCE_DEPENDENCY_MATRIX.json` | predecessor contract, SHA above | immutable predecessor; V2 supersedes it |
| `R3_LAUNCH_MANIFEST_SUPERSEDED_READY_002.json` | `da6869c43303cb21c89a76b031f71f21abc06f14`, source tree `134268865234f9cef6c6fc3f47a682a88184bfe78b6ad7b972675f3487597a51` | historical ready artifact; not active v8 |
| current `R3_LAUNCH_MANIFEST.json` | same `da6869c...` identity; status `R3_BLOCKED_ROSTER_PROVENANCE` | blocked/stale launch root; preserve, do not resume |
| active v8 firewall identity | `ecebc49dff41eeec33af62c2c85a75c5a0bd2922` and source tree `b138931f...` | canonical active v8; untouched and sealed |

The V3 plan records a new supersession index/receipt; no immutable V2 bytes or
old receipt is edited in place.

## wp0 closeout

The independent plan review concluded `VERDICT: PASS` after the roadmap was
amended to require a versioned V3 parser, exact official field mapping, a
parser→collector→inventory verifier chain, pre-scan acquisition-manifest
validation, deterministic hashes, immutable collision behavior, and a
metadata-only pytest allowlist. wp1 is the next phase. It must preserve the V2
module/API, implement the new V3 adapter and matrix, harden the R2B acquisition
manifest audit before scanning, and commit before any SOL core repairs.

**No-outcome attestation:** this report and its commands did not open historical
performance, returns, checkpoint trades, or final-holdout rows. The active v8
collector and raw root were read only for process/lock/manifest/schema metadata.
