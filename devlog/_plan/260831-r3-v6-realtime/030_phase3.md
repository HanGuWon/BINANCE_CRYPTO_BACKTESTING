# Phase 3 — post-boundary executor and final verification

Prepare a time-gated executor that rejects all pre-boundary calls and, only
after 2026-09-01T00:00:00Z, can verify August completeness/checksums, build a
September roster, run engineering-shadow qualification, pin launch identities,
and activate a fresh scientific root. Add negative tests for boundary,
freshness, evidence isolation, and structural primary-source-unavailable
handling. Do not execute any post-boundary action during this phase.

Run targeted R3 tests and `python -m pytest -q`; save the canonical receipt
with implementation/source hashes and scientific-source status. Final state
before the boundary is
`R3_REALTIME_BURNIN_VERIFIED_WAITING_FOR_AUGUST_CLOSE` unless a concrete runtime
defect requires an explicit blocker.
