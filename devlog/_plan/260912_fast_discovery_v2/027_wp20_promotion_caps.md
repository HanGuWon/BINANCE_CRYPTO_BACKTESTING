# WP20 — Bounded promotion counts

The campaign policy now freezes promotion caps before any outcome use: S0 maximum 12 survivors, S1 maximum 6 survivors, and S2 maximum 3 finalists. `_apply_cap` uses a stable descending metric/ascending identifier order and marks excess candidates `*_CAP_EXCLUDED`; it never pads an empty or undersized family. The policy receipt records these caps alongside the fixed four-row S1 registry.

Verification: synthetic cap test and Fast Discovery campaign/role tests passed (14 passed). No historical R2B/R3 outcomes or final-holdout observations were accessed.
