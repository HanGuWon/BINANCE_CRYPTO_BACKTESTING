# R3 Launch Erratum 005 — hypothesis/source matrix correction

Date: 2026-08-30 KST

The prior dependency matrix incorrectly mapped H01 to klines, H02 to premium
index klines, and H06 to open interest. The corrected pre-outcome mapping now
matches the frozen six-row registry: H01 uses book-ticker spread/microprice,
H02 uses completed price plus OI changes, H03/H04 use continuous forceOrder,
H05 pairs premium funding with completed premium-index close, and H06 uses
completed roster-member and BTCUSDT klines for breadth concordance.

The registry rows and SHA256 are unchanged. The collection contract now states
that depth, aggregate trades, OI history, and taker ratio are diagnostic-only.
Old sealed receipts are preserved; this erratum supersedes only the incorrect
source-mapping interpretation.
