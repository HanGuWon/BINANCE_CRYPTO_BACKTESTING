# R3 p2 — source, liquidation, and clock conformance

The source matrix is frozen before any prospective scientific collection:
closed 15-minute UM klines, premium, open interest, book ticker, depth,
aggregate trades, and continuous force-order events are primary/context
inputs; OI-history and taker-ratio are diagnostic context only. A force-order
stream is event-driven and absence is not a sampled zero.

`r3_timing.py` provides midpoint server-clock calibration and an absolute UTC
epoch-grid scheduler. The primitives are synthetic-only in this phase; no
historical outcomes or live scientific collection are run.
