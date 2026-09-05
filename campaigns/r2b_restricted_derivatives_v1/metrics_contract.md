# R2B metrics contract (pre-outcome freeze)

The eventual outcome executor must report, per trial × fold, the exact
decision/source and cashflow fields: `decision_time`, `symbol`, `side`,
`signal_variant`, `signal_value`, `source_open_time`,
`source_available_time`, `entry_time`, `exit_time`, `gross_return`,
`funding_cashflow`, and `net_return`. The optimized executor must match a slow
reference implementation at every field/value on UM fixtures before any R2B
outcome run. Spot fixtures are out of scope for this restricted-feature family;
any shared-engine Spot test must be labelled `ENGINE CONTROL ONLY` and cannot
satisfy R2B qualification.

`signal_variant` is reported with every trial. Missing premium observations are
not zero signals and must not be imputed. Any
trial with no eligible finite observations is reported with an explicit reason;
it is not silently removed from the registry.
