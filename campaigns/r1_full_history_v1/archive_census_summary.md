# R1.5 archive census summary

The census used paginated Binance Vision ListObjectsV2 metadata, not current
exchange-info, and completed successfully with 4,686 Spot/UM kline listing pages
(Spot root: 3,699 pages; UM root: 987 pages). It found 3,682 Spot symbols with
15m monthly kline objects and 986 UM symbols.

| Market | Historical symbols | Policy-eligible | 15m objects | Listed compressed bytes |
|---|---:|---:|---:|---:|
| Spot | 3,682 | 670 | 111,490 | 10,344,555,699 |
| UM | 986 | 832 | 22,641 | 2,448,154,026 |

Eligible candidate totals are 46,801 symbol-month objects and 5,273,148,503
compressed bytes. The complete object census is retained outside Git under
`data/census/r1_full_history_v1/`; the 4,668-row symbol census and small probe
manifests are tracked in this campaign directory.

Dataset probes found monthly fundingRate (920 symbol prefixes),
premiumIndexKlines (916), markPriceKlines (971), indexPriceKlines (915),
bookTicker (315), and aggTrades (974). The tested monthly roots for funding,
metrics, bookDepth, and liquidationSnapshot were not daily/object roots; empty
roots are recorded rather than treated as unavailable by assumption.
