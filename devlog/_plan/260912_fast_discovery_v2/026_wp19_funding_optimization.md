# WP19 — Exact funding event optimization

Added the opt-in `crossed_funding_events_fast` path using sorted event timestamps, `searchsorted`, and cumulative sums. It preserves the slow reference inclusion rule exactly: funding events strictly after entry and at or before exit; positive funding is paid by LONG and received by SHORT; NaN rates count as crossed events but contribute zero; no-event intervals return zero. The slow `crossed_funding_events` implementation remains the qualification oracle.

Synthetic parity covers boundary events, positive and negative rates, both sides, multiple events, NaN rates, and no-event windows. Verification: 14 tests passed (including existing R1.6 semantics). No historical R2B/R3 outcomes or holdout observations were accessed.
