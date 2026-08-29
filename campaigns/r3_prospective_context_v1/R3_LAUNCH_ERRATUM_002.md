# R3 launch erratum 002 — final conformance block

Date: 2026-08-29 KST

The previous `R3_READY_FOR_PROSPECTIVE_LAUNCH` manifest is superseded by this
erratum. Independent review found that the pilot identity is not yet a valid
scientific launch identity:

1. the pilot roster SHA is not reproducible from the authoritative universe;
2. the long-run collector does not verify the launch manifest;
3. it does not load or verify a frozen roster;
4. arbitrary symbol lists can be supplied;
5. forceOrder WebSocket is not integrated into the long-run process;
6. REST cycles drift because they sleep after work instead of using absolute
   quarter-hour boundaries;
7. storage projection is not Top50-scaled from measured stream evidence;
8. pilot latency and gap summaries are empty;
9. the collector clock is not calibrated to Binance server time;
10. collection and feature contracts retain stale pre-repair wording.

Operational status is therefore `R3_BLOCKED_FINAL_LAUNCH_CONFORMANCE`.
The existing `raw_v1` remains immutable engineering evidence only and must not
be mixed into a future scientific root. No historical outcomes, final holdout,
R2B2, private APIs, orders, or strategy metrics were accessed.
