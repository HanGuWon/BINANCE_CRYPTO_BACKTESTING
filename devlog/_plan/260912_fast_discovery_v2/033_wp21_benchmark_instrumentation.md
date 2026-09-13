# WP21 — Phase-level benchmark instrumentation

The development-screen runner now records actual wall-clock seconds for source discovery, causal panel/cohort assembly, feature computation, S0 scoring, cache reuse, and total execution. S1 scoring and S2 replay are explicitly marked `NOT_RUN` with zero duration because this runner is S0-only. Receipts also record rows scored, symbols/months loaded, and cache hits/misses; scientific result CSVs remain deterministic and timing is confined to the receipt.

Synthetic runner verification passed (12 tests including benchmark fields). Existing v3 roots remain immutable; any re-run will use a new versioned root.
