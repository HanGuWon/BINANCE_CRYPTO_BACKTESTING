# WP27 — Provenance mismatch fail-closed verification

Added `verify_source_identity` to reject dirty scientific source trees and any manifest whose implementation commit or computed source-tree SHA differs from the live checkout. Optional expected identities are independently checked; no trusted constant is silently accepted. Synthetic tests cover commit mismatch and dirty-source refusal.

Verification: 17 focused Fast Discovery tests passed. No historical R2B/R3 outcomes or final-holdout observations were accessed.
