# Implementation Plan

1. Establish an isolated Python research package with no account or order surface.
2. Build immutable official-archive acquisition, checksum verification, UTC schema
   normalization, integrity checks, lifecycle discovery, and a read-only API client.
3. Implement a typed causal feature catalog and the preregistered core 22 features.
4. Implement predictive event studies and a next-bar canonical-rule backtester with
   gross/net accounting and explicit fees, spread, slippage, latency, and funding.
5. Add chronological split/walk-forward, regimes, redundancy, multiple-testing
   diagnostics, experiment registry, report artifacts, and forward-only collection.
6. Prove mathematical behavior, temporal alignment, no-lookahead, execution costs,
   MFE/MAE, lifecycle handling, and deterministic replay in automated tests.
7. V2 verification: keep one canonical definition per public path; use complete
   bar timelines for risk; preserve execution scope, funding fail-closed rules,
   point-in-time provenance, archive cadence/date validation, API-key fail-soft
   collection, development-only walk-forward selection, and explicit final
   holdout access.
