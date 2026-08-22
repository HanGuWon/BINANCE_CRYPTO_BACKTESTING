# R1.6 gap policy

The declared source interval is explicit. Timestamps must be unique,
increasing, and on the declared grid. A delta equal to the interval stays in
the same segment; an aligned larger delta starts a new segment_id; a
shorter or off-grid delta is an integrity error.

Every panel row retains segment_id, segment_start, segment_end, gap_before,
gap_size_bars, and source_coverage_status. Rolling, EWM, and cumulative
features are computed independently per segment. Missing candles are never
interpolated or filled from future values.
