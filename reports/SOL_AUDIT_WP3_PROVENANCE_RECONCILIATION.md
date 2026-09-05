# SOL audit — wp3 provenance reconciliation

Read window: 2026-09-05 (KST), metadata-only, on isolated branch
`codex/sol-audit-repair-v1`. This report does not open outcome, return,
checkpoint-trade, or final-holdout content. The historical v8 collector identity
is not changed.

## Identity disposition

| record | implementation | source tree | registry | root | disposition |
| --- | --- | --- | --- | --- | --- |
| active sealed v8 | `ecebc49dff41eeec33af62c2c85a75c5a0bd2922` | `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688` | `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a` | `D:/BINANCE_CRYPTO_BACKTESTING_DATA/r3_prospective_context_v1/scientific_raw_v8` | `CURRENT_FROZEN` |
| short V2 amendment/manifest | `ecebc49dff41eeec33af62c2c85a75c5a0bd2922` | `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688` | `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a` | `D:/BINANCE_CRYPTO_BACKTESTING_DATA/r3_prospective_context_v1/scientific_raw_v8` | `HISTORICAL_EVIDENCE/SUPERSEDED_BY_ADVERSARIAL_V2` |
| old R3 launch manifest | `da6869c43303cb21c89a76b031f71f21abc06f14` | `134268865234f9cef6c6fc3f47a682a88184bfe78b6ad7b972675f3487597a51` | `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a` | `D:/BINANCE_CRYPTO_BACKTESTING_DATA/r3_prospective_context_v1/raw_v1` | `INVALID_SUPERSEDED/BLOCKED` |
| isolated ForceOrder V3 repair | `0f0bfa9d3bb860fc09262f3bee92aaca734ed8da` | not a v8 identity | not a v8 identity | not a v8 identity | `HARNESS_REPAIR_ONLY` |
| isolated SOL core repair | `820f88f3626276796304ccbbe1983e6c02cb6710` | not a v8 identity | not a v8 identity | not a v8 identity | `HARNESS_REPAIR_ONLY` |
| isolated verifier-fixture repair | `ea933604fd97eee3503f901af634785c7c16c3c7` | not a v8 identity | not a v8 identity | not a v8 identity | `HARNESS_REPAIR_ONLY` |
| canonical state-index snapshot | `2c39febfd7350d0bbcb12ed7185fcb52933b5324` | not applicable | not applicable | not applicable | `HISTORICAL_SNAPSHOT` |

The short amendment (`8f12263c107e8b1fb2596c72f5c3e0c741a17339a42f95aab67df86b87738c38`)
and short reproducibility manifest (`ee840ad17dfaf246991f758d6420fd790f8bfcfaa0279ef4d2626ed5d93543a7`)
remain byte-for-byte preserved. The old launch manifest remains preserved and is
not resumed. The historical canonical-state index remains a snapshot and is not
rewritten.

## Live-reference corrections

| path | old SHA-256 | new SHA-256 | reason |
| --- | --- | --- | --- |
| `campaigns/r3_prospective_context_v1/campaign_spec.toml` | `0b08e6818d76dde38a08a69b86d241ea6339fe33e4cdf037e9ae51f2df1480e4` | `74c614ae98758256934c0b5fbc16967e038c8b787f92e9f78d11c35f68bed9fa` | live amendment, horizon-map, and adversarial-manifest references were stale |
| `campaigns/r3_prospective_context_v1/R3_PROTOCOL.md` | `8e96f3ab855f4680f6125e883f0cabc7429c893de6ab251322a5a88274c6af29` | `62aacb71c9561cbe54ff6c5ce1e472b7007ec44e7518a56420769fa79b20e118` | live protocol now names adversarial V2 and preserves short V2 as historical |
| `campaigns/r3_prospective_context_v1/multiple_testing_plan.md` | `829e8802c24cbbda5bfae000d48e90bc1caed4225c5c7380b70e2a674a7bf9a6` | `bee7c53431e0416f29559c0be8a3674ed804e58e16ac49c45275444054ee5073` | authoritative amendment reference |
| `campaigns/r3_prospective_context_v1/metrics_contract.md` | `50f1463eca25060b46c5bdd76f9922cd9ea0ec38d448b4e8cee8599fcf1d5f3f` | `e507e670e8a04b092e4a86ace899df972d4fbf0e4f5b0a1b1004eac541fe3ef4` | authoritative amendment reference |
| `campaigns/r3_prospective_context_v1/promotion_policy.md` | `4313730a95b9a48cf994c3db22def2817c55f7f69ed96389852e0bb6e02e6636` | `95c717e5035466cc5ddf394854281af97fb56b09b33849f51dbaea6fb818e1b6` | authoritative amendment reference |

Authoritative bytes and hashes are taken from the repository paths
`R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL.md`
(`ac788de08e77a5eb87b7b5a6619ada104668df3dc00f6908491ee2e1afa79672`),
`R3_EVALUATION_HORIZON_MAP_V1.json`
(`7cd935a33ac7ed47d1b9c7e037d5033b3add694934730eca5ebadda48fbb98e5`), and
`R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL_REPRODUCIBILITY_MANIFEST.json`
(`0cb2400f2ada8cc35882563d49af14f8e33e4148f21cc128ce02c8127849a104`).

## Classification and guards

* Documentation-reference corrections are `MERGE_SAFE_NONSCIENTIFIC`.
* Immutable output, membership-label, and repository-root portability changes
  are `FUTURE_HARNESS_REPAIR`.
* No R3 scientific identity is changed; any future semantic/identity change is
  `R3_NEW_SCIENTIFIC_IDENTITY_REQUIRED`.
* `outcome_values_accessed=false`; `final_holdout_status=UNTOUCHED`;
  `r2b2_status=NOT_STARTED`; `merge_action=NONE`.

The append-only index at
`campaigns/r3_prospective_context_v1/operations/SOL_AUDIT_WP3_PROVENANCE_INDEX_20260905.json`
is the machine-readable source for this report. A later correction must create
a new date-named index; neither this index nor any stale historical artifact may
be rewritten.
