# R3 v6 real-time burn-in and post-boundary executor roadmap

This docs-first roadmap is locked before implementation. Scope is limited to
re-verifying the sealed August state, documenting the distinction between the
v5 injected-boundary qualification and a true wall-clock burn-in, running the
real-time engineering-shadow collector before the 2026-09-01 boundary, and
preparing (but not executing) a time-gated September launch executor.

Out of scope: September ranking/roster generation, scientific collection,
historical outcomes, returns/PnL/Sharpe/hit-rate analysis, final-holdout access,
R2B2, and modifications to existing v3/v4/v5 evidence roots.

Implementation units:

* 010: sealed-state re-verification and append-only v5 clarification.
* 020: real wall-clock v6 run, scheduler/WS/gap/storage verification, and
  D-backed evidence receipt.
* 030: post-boundary executor safety, fresh scientific-root guard, tests, and
  canonical pytest receipt.

Each unit must leave a durable receipt, preserve outcome-blind evidence mode,
and stop safely if the August boundary would be crossed.

Roadmap review note (2026-08-31): the implementation units were re-read at
the B phase against the existing R3 collector, timing, manifest, and test
surfaces. No September artifact or scientific root is to be created by these
units before the boundary.
