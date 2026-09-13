# WP14-WP15 — Frozen S1 role grammar

Status: IMPLEMENTED_AND_TARGETED_VERIFIED (development-only; no historical outcome run)

The prior S1 arithmetic mean of three unlike-scaled values is superseded for all future execution. The frozen grammar is:

`TRIGGER AND REGIME_FILTER AND PARTICIPATION`

The trigger retains its native numeric value. A finite, non-zero regime filter is required. For a discrete trigger in `{-1,+1}`, the regime sign must agree with the trigger; continuous triggers require only a finite non-zero regime state. `rvol20` participation requires `>= 1.0`. Ratio participation is finite and not equal to `1.0`; for a discrete trigger it must be on the same side of `1.0` as the trigger. Any missing, non-finite, neutral trigger, or failed role condition yields explicit `0.0`; no NaN is converted into a signal.

S1 eligibility is role-aware: the primary trigger must be present as an `S0_SURVIVOR`/`SURVIVOR`; regime and participation components need finite historical coverage but do not need standalone S0 alpha status. The registry remains a fixed four-row, three-component theory-driven set with no Cartesian expansion.

The earlier structural screen receipts remain immutable and are not reinterpreted. Their `trade_rows=0` and `interpretation=NOT_PERFORMED` status is preserved; this grammar applies to any subsequent development campaign only.

Verification: `PYTHONPATH=src; python -m pytest -q tests/test_fast_discovery_s1_roles.py tests/test_fast_discovery.py tests/test_fast_discovery_qualification.py` -> 16 passed; complete Fast Discovery targeted family -> 50 passed. Final holdout remains `UNTOUCHED`; no R2B/R3 outcomes accessed.
