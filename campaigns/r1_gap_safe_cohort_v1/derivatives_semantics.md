# R1.6 derivative semantics

Funding execution uses the verified event ledger. A position crosses only the
actual event timestamps in its holding interval; no synthetic eight-hour grid
is created. Positive funding is a cash outflow for longs and an inflow for
shorts.

derivatives.funding_zscore is the trailing z-score over the last 90 funding
events, backward-as-of the latest causally known event to completed bars.

derivatives.premium_zscore uses the close of Binance UM premiumIndexKlines,
with a trailing 90-bar gap-safe z-score at the matching study timeframe where
available. Premium gaps are explicit and never interpolated.

UM daily metrics are retained as an investigated source, but sum_open_interest
is not silently substituted for openInterestHist. Daily bookTicker has bid/ask
prices and quantities but restricted 2023–2024 coverage; bookDepth lacks the
exact frozen top-book quantity semantics.
