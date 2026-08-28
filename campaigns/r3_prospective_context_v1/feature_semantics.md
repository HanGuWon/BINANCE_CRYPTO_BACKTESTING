# R3 feature semantics (frozen before outcomes)

All timestamps are UTC. Every feature is state/context, not a standalone
entry signal. Values are NaN when required source observations are missing or
outside a continuity segment; NaN is never imputed from future data.

1. `EXECUTION_QUALITY_CONTEXT`: `spread_bps = 10^4*(ask-bid)/mid` and
   `microprice_displacement = (microprice-mid)/mid`, where
   `microprice=(ask*bid_qty+bid*ask_qty)/(bid_qty+ask_qty)`. Both are continuous
   trailing state variables; no outcome-derived threshold.
2. `PRICE_OI_QUADRANT`: `price_sign=sign(close_t-close_{t-1})`,
   `oi_sign=sign(OI_t-OI_{t-1})`; state is the ordered pair in
   `{(+,+),(+,-),(-,+),(-,-)}`. Zero or missing components produce `NaN`.
3. `LIQUIDATION_CONTINUATION`: `L_t` is signed liquidation notional in the
   preceding complete event bucket, positive for forced sell orders and
   negative for forced buy orders. The context is continuous `L_t`.
4. `LIQUIDATION_REVERSION`: same causal `L_t` input as (3), with the response
   sign predeclared opposite to the impulse; it is a distinct hypothesis, not
   a post-outcome polarity switch.
5. `CROWDING_STRESS_MODIFIER`: fixed context tuple
   `(funding_rate_t, premium_t)` with no standalone entry and no new polarity;
   missing either component yields `NaN` for the modifier.
6. `BTC_BREADTH_CONCORDANCE`: at each decision time,
   `C_t = mean(sign(r_symbol)*sign(r_BTC))` over the frozen selected universe;
   symbols without a valid return are excluded from the denominator.

Warmup requires all stated lags/events. A gap or restart starts a new segment
and invalidates warmup until the requirements are rebuilt. State values are
attached only when `source_available_time < decision_time`.
