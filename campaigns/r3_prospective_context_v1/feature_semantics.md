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
3. `LIQUIDATION_CONTINUATION`: `observed_forceorder_pressure_t` is the sum of
   observed forceOrder events only; it is not complete market liquidation
   notional. For an event `e`,
   `p_e = sign_e * last_filled_quantity_e * average_fill_price_e`, with
   `sign_e=+1` for forced `SELL` and `sign_e=-1` for forced `BUY`.
   The retained observable includes market, symbol, exchange event time,
   order/trade time, side, original/last/accumulated quantities, order/average
   prices, position side, subtype, and canonical raw-payload SHA. Its states
   are `OBSERVED_FORCEORDER_EVENT`, `NO_FORCEORDER_EVENT_OBSERVED`,
   `FORCEORDER_STREAM_GAP`, `FORCEORDER_RESTART_GAP`, and
   `FORCEORDER_STREAM_UNAVAILABLE`; silence is never imputed as zero.
4. `LIQUIDATION_REVERSION`: the same `observed_forceorder_pressure_t` input
   as (3), with the response sign predeclared opposite to the impulse; it is a
   distinct hypothesis, not a post-outcome polarity switch.
5. `CROWDING_STRESS_MODIFIER`: fixed context tuple
   `(funding_rate_t, premium_t)` with no standalone entry and no new polarity.
   `funding_rate_t` is exactly `lastFundingRate` from `/fapi/v1/premiumIndex`;
   `premium_t` is the close of the most recent fully completed row from
   `/fapi/v1/premiumIndexKlines?interval=15m`. Mark price is never substituted.
   Both values must be available before the next executable open; missing either
   component yields `NaN` for the modifier.
6. `BTC_BREADTH_CONCORDANCE`: at each decision time,
   `C_t = mean(sign(r_symbol)*sign(r_BTC))` over the frozen selected universe;
   symbols without a valid return are excluded from the denominator.

Warmup requires all stated lags/events. A gap or restart starts a new segment
and invalidates warmup until the requirements are rebuilt. State values are
attached only when `source_available_time < decision_time`.
