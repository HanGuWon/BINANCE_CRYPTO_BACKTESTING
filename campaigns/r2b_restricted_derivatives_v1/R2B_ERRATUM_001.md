# R2B Erratum 001 — premium acquisition provenance

Date: 2026-08-27 KST

The original R1.5 derivative acquisition was intentionally limited by a
hard-coded anchor loop to `BTCUSDT` and `ETHUSDT`. The R1.7 panel therefore
reported premium/premium-zscore coverage of roughly 3.45%–4.21% and correctly
classified the features `R2B_RESTRICTED`; this was an acquisition-completeness
defect, not evidence that Binance had no historical objects.

The R1 artifacts and their hashes are preserved unchanged. A separate R2B
manifest now acquires 5,647 pre-holdout 15m objects for the 189 UM Top-50
symbols that have a selected month through 2024-01. Every local object is
present and checksum-verified. A separate D-backed materialization contains
193 panel symbols (four have no pre-holdout premium archive) and derives 1h/4h
from complete contiguous 15m buckets. No R1 raw object, R1 panel, checkpoint,
or holdout file was modified.

The repaired root is availability-conditioned, not universally complete:
missingness remains explicit for symbols without an acquired archive, feature
warmup/zero variance, gap quarantine, and no eligible universe rows. These
causes are recorded in `premium_coverage_audit.csv` rather than silently
dropping rows.

