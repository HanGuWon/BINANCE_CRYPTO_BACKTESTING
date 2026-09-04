# R3 prospective context v1 protocol — V2 evaluation contract

R3 asks whether historically unavailable market-state observations add causal
context or gates to simple price-direction observations. It is a prospective
data-collection and later evaluation protocol, not a retrospective search for
profitability. No outcome analysis, return ranking, threshold tuning, or
final-holdout access is permitted before a separately approved evaluation
phase.

Ranking identity has two distinct domains. `ranking_semantic_sha256` is a
canonical hash over normalized UM candidate/rank fields and is used for raw to
ranking parity. Raw manifest, ranking artifact, and roster hashes are
provenance identities and must change when input bytes change. A roster-hash
mismatch therefore records different provenance, not different ranking
semantics.

The authoritative primary Binance UM streams are closed 15-minute klines,
premium-index klines, premium index, open interest, book-ticker, and continuous
liquidation force-order events. Depth, aggregate trades, open-interest history,
and taker ratio are diagnostic-only. Liquidation force-order events are
collected through the public market stream.
Top-trader ratio endpoints, private APIs, balances, positions, and orders are
excluded from R3 v1.

The frozen primary family has six structural hypotheses: execution-quality
context, price×OI quadrant, liquidation continuation, liquidation reversal,
crowding×stress modifier, and BTC/breadth concordance. There are no parameter
grids. The 72-row R2B registry is not reused as an R3 registry. The V2
evaluation amendment freezes exactly one primary horizon,
`R3_HORIZON_15M_NEXT_NATIVE_BAR_V1` (`15m`, one bar, no alternatives).

All observations are retained raw and append-only. Derived materialization is
separate and uses `source_available_time < next_executable_open_time`, where
native 15-minute premium-kline availability is the kline close and any derived
1-hour/4-hour bucket availability is the maximum constituent close. Exact
boundary equality is rejected. For the September roster, historical taxonomy,
actually discovered August objects, complete eligible prior-month symbols, and
the September Top50 roster are distinct sets; taxonomy membership alone never
creates an August expected object. Monthly and listed-daily source modes are
recorded separately, partial prior-month coverage is excluded per symbol, and
discovered-object integrity failures block the campaign. Native premium-index
15-minute availability is the native kline close; a derived 1-hour/4-hour
bucket is available at the maximum close of all complete constituent bars.
Discovered-object integrity failures block the campaign. Continuity, restart,
source-unavailable, rollover, and missing-cycle gaps reset state, remain
preserved metadata, and map to every intersected UTC six-hour block; affected
blocks are ineligible once and are never imputed or backfilled. A minimum
evidence window will be fixed from event counts, dependence blocks, and
confidence precision before prospective outcome analysis; returns cannot choose
its end.

The outcome-blind unlock contract is frozen in
`R3_EVALUATION_AMENDMENT_V2.md`, with the immutable horizon artifact
`R3_EVALUATION_HORIZON_V1.json`. The exact point-in-time rule is
`source_available_time < next_executable_open_time`; equality is rejected.
V2 fixes UTC six-hour dependence blocks, Holm correction across exactly six
hypotheses, explicit timestamped gap/block accounting, evidence minima, and a
verified roster-month gate. The current state is
`R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES` because minima are not met;
`evaluation_human_authorized` remains false. Satisfying metadata minima never
launches evaluation, and no alternate horizon, threshold, subgroup, or response
value may be invented or searched.
