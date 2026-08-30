# R3 Launch Erratum 006 — Native 1d Forward-Ranking Parity Block

Date: 2026-08-30 KST

The adversarial p4 qualification now reconstructs monthly UM rankings from
the D-backed native 1d archives, using the canonical R16 archive summarizer,
complete-month gate, and liquidity selector. It does not read returns, PnL,
the final holdout, or any R2B outcome artifact.

The qualification is **BLOCKED** at the raw-input gate. The current July 2026
archive set contains at least one duplicate-timestamp object
(`UMAUSDT-1d-2026-07.zip`), so the wrapper correctly refuses to rank it. A
prior run that excluded incomplete objects produced the same 50 selected
symbols but a different roster identity (`d4764c9e...` versus the committed
`ec2609bb...`); exact parity is therefore not claimed. The generated raw
manifest contained 752 complete rows and had SHA256
`c1f4a52d61efd091c32a782a6fd65ceb2c7b1ec10ddfbf5b9795d0a6922a68aa`.

The earlier `R3_FORWARD_RANKING_PARITY_RECEIPT.json` remains historical. This
erratum supersedes any implicit PASS interpretation until the authoritative
raw archive set is repaired or a provenance-equivalent source is supplied.
