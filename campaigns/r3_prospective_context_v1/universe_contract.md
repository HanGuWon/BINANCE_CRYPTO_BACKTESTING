# R3 universe contract

Reuse the existing causal monthly UM Top50 universe when its point-in-time
ranking is operationally available. Membership is frozen for each observation
month and recorded with effective start/end timestamps. A symbol leaving and
re-entering creates a new continuity segment. No future return, signal result,
or profitability measure may alter membership.

The executable contract is `build_causal_monthly_roster`: for effective month
`M`, the source must contain exactly 50 USD-M rows selected for `M`, ranked from
the complete prior month `M - 1` (`coverage_ratio == 1.0` and
`ELIGIBLE_COMPLETE_PRIOR_MONTH`). The source bytes and resulting roster are
SHA256-pinned. `replay_roster_artifact` recomputes the identity and rejects
tampering, wrong-month inputs, non-UM rows, partial coverage, or a missing
prior-month ranking. A missing next-month roster enters
`UNIVERSE_ROLLOVER_GAP`; collection must remain suspended until a matching
immutable roster is available.
