# Post-boundary R3 executor runbook (prepared, not activated)

This runbook is intentionally time-gated at `2026-09-01T00:00:00Z`. Before
that boundary the executor may only return
`R3_BLOCKED_SEPTEMBER_ROSTER`; it must not acquire August data, build a
September ranking, write `rosters/2026-09.json`, create a launch seal, or start
scientific collection.

After the boundary, execute the steps in order: verify Binance-calibrated time;
acquire and checksum-complete August UM 1d archives; build and hash the
September ranking; freeze and replay the September roster; run engineering
shadow qualification; verify clock/WS/source/storage gates; create a new launch
manifest pinned to all current contract identities; verify a fresh empty
`scientific_raw_v1` root; then activate the scientific collector. Any failed
gate maps to the explicit `R3_BLOCKED_*` states in the goal objective. The old
blocked `R3_LAUNCH_MANIFEST.json` is never edited into authority.

Prepared implementation: `scripts/prepare_r3_post_boundary_launch.py`.
It returns a plan with `execute: false` and performs no network or filesystem
mutation beyond checking the requested root.
