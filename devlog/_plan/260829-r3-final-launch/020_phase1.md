# R3 p1 — roster provenance and causal monthly replay

The prior engineering pilot used BTCUSDT/ETHUSDT and a synthetic roster
identifier. That identifier is not reproducible from the repository's
authoritative causal universe and is retained only as historical pilot
metadata; it is not a scientific roster.

The canonical roster builder now consumes the immutable
`campaigns/r1_final_panel_v1/universe_monthly.csv` ranking artifact. For an
effective month `M`, it accepts only UM rows selected in `M` whose complete
prior volume month is exactly `M - 1`, with coverage ratio 1.0 and
`ELIGIBLE_COMPLETE_PRIOR_MONTH`. The input bytes are SHA256-pinned and the
result is canonicalized in `rosters/YYYY-MM.json` with a deterministic roster
SHA256. Replaying the artifact re-runs the identity calculation and fails
closed on tampering.

The August 2026 artifact is therefore an ex-ante 50-symbol roster derived from
the completed July 2026 ranking, not a claim that the two-symbol engineering
pilot used that roster. September rollover remains suspended until a completed
August ranking is available; no outcome data is consulted.
