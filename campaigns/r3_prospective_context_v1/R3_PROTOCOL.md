# R3 prospective context v1 protocol

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
grids. The 72-row R2B registry is not reused as an R3 registry.

All observations are retained raw and append-only. Derived materialization is
separate and uses `source_available_time < next_executable_open_time`, where
native 15-minute premium-kline availability is the kline close and any derived
1-hour/4-hour bucket availability is the maximum constituent close. Exact
boundary equality is rejected. For the September roster, historical taxonomy,
actually discovered August objects, complete eligible prior-month symbols, and
the September Top50 roster are distinct sets; taxonomy membership alone never
creates an August expected object. Monthly and listed-daily source modes are
recorded separately, partial prior-month coverage is excluded per symbol, and
discovered-object integrity failures block the campaign.
Continuity gaps reset state and are never silently bridged. A minimum evidence
window will be fixed from event counts, dependence blocks, and confidence
precision before prospective outcome analysis; returns cannot choose its end.
