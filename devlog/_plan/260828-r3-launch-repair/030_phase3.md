# R3 p3 — prospective collector operations and provenance receipts

Implement a public-data-only runner that loads an explicit symbol list, polls
the eight R3 REST streams, persists append-only envelopes, and records a
hash-linked manifest plus health receipt. A filesystem lock prevents concurrent
writers; restart and graceful stop leave prior files untouched. The runner has
no order/account methods and computes no returns, PnL, signals, or rankings.

Verification: `python -m pytest -q tests/test_r3_operations.py`.
