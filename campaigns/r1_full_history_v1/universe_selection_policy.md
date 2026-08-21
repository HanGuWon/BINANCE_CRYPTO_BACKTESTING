# R1.5 historical instrument and universe policy

The archive itself, not current exchange-info, defines historical existence.
For Spot, only USDT-quoted ordinary instruments are candidates; obvious
UP/DOWN/BULL/BEAR leveraged suffixes are excluded with an explicit reason.
For USD-M, only USDT perpetual-style symbols are candidates; dated delivery
symbols matching the `_YYMMDD` suffix are excluded. Ambiguous products remain
visible in the eligibility census and are not silently promoted.

For a future monthly cohort M, a candidate must have archive observations before
the start of M and usable completed quote-volume data from M-1. Rank by the sum
of M-1 quote volume, freeze membership for M, and retain independent Top-20,
Top-50, and Top-100 diagnostics. R1.5 deliberately stops before this broad
download because the census shows the candidate acquisition is not safely
materializable within the current disk margin.
