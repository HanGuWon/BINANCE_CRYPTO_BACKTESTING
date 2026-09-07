# R2B Premium Index semantics review (outcome-blind)

Date: 2026-08-27 KST  
Status: `PRE-OUTCOME REVIEW COMPLETE — TWO-VARIANT FAMILY REQUIRED`

## Scope and exclusion boundary

This review evaluates only the economic meaning of Binance USDⓈ-M Premium
Index observations. It does not inspect R2B returns, checkpoints, holdout
files, or any repository artifact containing historical predictive performance.
The exclusion list in `semantics_design_exclusion_list.md` is binding. The
review is therefore an ex-ante protocol decision, not a performance-driven
polarity choice.

## Evidence hierarchy

### Primary exchange documentation

* Binance, *Premium Index Kline Data* (USDⓈ-M Futures REST API):
  <https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data>.
  The endpoint defines a historical Premium Index kline series, with interval
  and open/close-time fields. It is an observation of the futures-versus-index
  pricing mechanism, not a documented LONG/SHORT trading rule.
* Binance Futures documentation, *Introduction to Funding Rate*:
  <https://www.binance.com/en/support/faq/detail/360033525031>.
  Binance describes funding as a periodic transfer intended to keep the
  perpetual contract price close to the underlying/index; this supports a
  convergence mechanism but does not establish the sign of a short-horizon
  return response.

### Peer-reviewed and research literature

* Fassas, A., Papadamou, S., & Koulis, T. (2020). *Price discovery in bitcoin
  futures*. Research in International Business and Finance, 52, 101166.
  DOI: <https://doi.org/10.1016/j.ribaf.2019.101116>.
  The paper supports derivatives as a venue that can contribute to price
  discovery, making same-direction pressure a plausible mechanism. It does not
  prove that every positive premium predicts a positive next return.
* Alexander, C., Heck, D. F., & Kaeck, A. (2020). *Price discovery and
  microstructure in ether spot and derivative markets*. International Review
  of Financial Analysis, 71, 101506. DOI:
  <https://doi.org/10.1016/j.irfa.2020.101506>.
  The study provides independent evidence that derivatives can lead information
  incorporation in crypto markets; lead/lag and horizon dependence remain
  empirical questions.
* He, Z., Manela, A., Ross, S., & von Wachter, J. (working paper).
  *Fundamentals of Perpetual Futures*. SSRN 4301150. DOI:
  <https://doi.org/10.2139/ssrn.4301150>.
  The model describes funding, arbitrage, and index-linked convergence forces.
  It motivates a crowding/dislocation interpretation for extreme deviations,
  while not identifying a universal contrarian execution horizon.
* Barucci, E., et al. (2023). *Market impact and efficiency in cryptoassets
  markets*. Journal of Risk and Financial Management, 16(2), 95. DOI:
  <https://doi.org/10.1007/s42521-023-00095-9>.
  The evidence is consistent with time-scale- and liquidity-dependent
  continuation and reversal effects; it does not justify selecting one polarity
  for all symbols and horizons ex ante.

## Competing hypotheses

### H1 — `PRESSURE_CONTINUATION`

Premium is interpreted as derivatives-side demand/price pressure relative to the
index. For a raw premium value `p`:

```text
sig_pressure(p) = +1  if p > 0
                  -1  if p < 0
                   0  if p = 0
             NaN -> no signal (0 only at the execution gate, never by coercion)
```

This is a directional-pressure hypothesis, not an assertion that funding or
arbitrage cannot later reverse the move.

### H2 — `CROWDING_REVERSION`

Premium is interpreted as a leveraged-position crowding/dislocation measure that
is expected to compress toward the index. For a raw premium value `p`:

```text
sig_reversion(p) = -1  if p > 0
                   +1  if p < 0
                    0  if p = 0
              NaN -> no signal (0 only at the execution gate, never by coercion)
```

The sign is intentionally the opposite of H1. This is a separate scientific
hypothesis and counts toward the multiple-testing family.

## Raw premium versus `premium_zscore90`

Raw premium has a natural zero boundary: positive values are a premium and
negative values a discount. The standardized feature instead measures a
symbol's displacement from its own rolling history. The cited sources justify
studying both mechanisms but do not provide an outcome-independent universal
binary threshold such as `|z| >= 1` or `|z| >= 2`. Accordingly, this freeze uses
the sign of the z-score with the same two polarity variants, without a threshold
grid; zero remains no signal and NaN/warmup remains no signal. The raw and
standardized inputs are not conflated.

## Ex-ante decision

The literature supports both derivatives-led price discovery and
funding/arbitrage-driven convergence. It does not uniquely identify whether a
15-minute observation should be traded in the same direction or against the
premium, nor does it establish a universal z-score threshold. Choosing one
polarity from historical R2B performance would violate the outcome-blind gate.

Therefore the smallest defensible pre-outcome family is two explicitly named
variants, each applied separately to `premium` and `premium_zscore90` over the
existing UM timeframe/side/horizon dimensions. The prior blocked 36-row
registry is superseded by a deterministic 72-row preregistered family after
the formal amendment is committed. Spot remains an engine control only.

## Limitations

Exchange documentation defines the measurement and funding mechanism, not a
predictive sign. The literature is heterogeneous in asset, venue, liquidity,
and horizon, and therefore cannot establish a universal polarity. This note
freezes hypotheses for a controlled pre-outcome qualification; it is not
evidence that either variant will produce positive returns.

## AI-assisted research disclosure

This note was prepared with AI-assisted source discovery and synthesis. Source
titles, identifiers, and links were checked against official documentation or
Crossref metadata before inclusion.

## Verification record

On 2026-08-27 KST, Crossref metadata queries were rerun for the four cited
research works; the DOI/title pairs recorded above matched the returned
records. Binance endpoint URLs were checked as official Binance documentation
targets. No repository performance, checkpoint, or holdout path was opened
during this review.
