# R2B restricted-derivatives v1 — pre-outcome freeze report

Date: 2026-08-28 KST  
Branch: `research/r2b-restricted-derivatives-v1`  
State: `R2B_READY_FOR_PREOUTCOME_FREEZE`

## Provenance and causal data

The premium coverage audit now requires the R2B-specific
`premium_archive_manifest.csv`, and fails closed for wrong dataset, market,
interval, checksum/integrity status, R1 anchor manifests, or panel symbol
conflicts. The authoritative lineage is 189 symbols and 5,647 verified
`premiumIndexKlines` archives (0 integrity failures). The stale BTC/ETH-only
R1 audit is preserved with an explicit supersession note.

The canonical causal root is
`D:/BINANCE_CRYPTO_BACKTESTING_DATA/processed/r2b_restricted_derivatives_v1_repaired_v2_causal3`:
1,467 partitions, 8,357,398 rows, tree SHA256
`6eef4e59225cb45c2833452a883249b11f03469298c1ecfb3837c5f4aaa27a7d`, and
causal verifier `PASS`. The verifier enforces
`source_available_time < next_executable_open_time`, native 15m close time,
and maximum constituent close for complete 1h/4h buckets; exact-boundary
observations are rejected. No holdout row or cross-segment state is admitted.

## Outcome-blind semantics

The review in `R2B_PREMIUM_SEMANTICS_REVIEW_2026-08-27.md` used Binance's
[Premium Index Kline documentation](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data),
[funding documentation](https://www.binance.com/en/support/faq/detail/360033525031),
and peer-reviewed/working-paper evidence on futures price discovery,
derivatives microstructure, and convergence. Both pressure continuation (H1)
and crowding/convergence reversion (H2) remain economically plausible, so both
are preregistered rather than selected from performance.

For raw `premium` or segment-local `premium_zscore90`, with variant `v`:

```text
PRESSURE_CONTINUATION: +1 if x > 0, -1 if x < 0, 0 if x == 0
CROWDING_REVERSION:    -1 if x > 0, +1 if x < 0, 0 if x == 0
NaN/missing/warmup:     NO_SIGNAL (NaN; never imputed to zero)
```

LONG execution accepts only `signal == +1`; SHORT accepts only `signal == -1`.
There is no threshold grid or crossing detector. The resulting family is 72 UM
rows (two features × two variants × three timeframes × two sides × fixed
horizons). The old blocked 36-row registry SHA is preserved as superseded;
the canonical registry SHA is
`3c61d923fe2cf88714c8cd2592264800ef2880db894dd2a21170fdf4fcc85302`.

## Implementation and qualification

Frozen signal code is in `scripts/r2b_signals.py`; registry integrity is checked
by `scripts/verify_r2b_registry.py`. The implementation commit is
`7e791f707bef6905fccfb2eb4f2927cf06dc1192` and the scoped scientific source
tree SHA is
`d67214c63e722e67cf8af7c4af63ed08afc33e07b3e6ab06fc9399aa76d5c0df`.

`scripts/r2b_qualification.py` compares an optimized mapper/executor with an
independently written slow reference on synthetic fixtures only: UM 15m/1h/4h,
LONG/SHORT, every registered horizon, both variants, positive/negative/no
funding, missing premium, z-score warmup, gap segments, next-open timing, and
opposite-sign rejection. It compared 33,420 records field-for-field across
`decision_time`, symbol/side/variant/signal, source and execution timestamps,
gross return, funding cashflow, and net return. The canonical payload SHA256 is
`90995f4b4e76948c83e0cb62044264bb5bc093f17dfc9ce899baf78decceae3f`, the
result identity is `4d50f019220d949d727465b2780c8b01eefe7a18cfab79c4d0d33c376d8fe027`,
and the serialized receipt file SHA256 is
`3a6d60eb6f79a47e7883c3fccc9ac330d3af9aef7fc4225e190b2bbd7e661898`.
No historical R2B outcome was started.

The canonical full pytest receipt records the actual command `python -m pytest
-q`, exit code 0, `169 passed, 1 warning`; scoped scientific status is clean.
The final holdout remains `UNTOUCHED`. Historical R2B outcomes remain
prohibited even in this ready pre-outcome state.
