# R1 processed panel schema

Processed data is ignored by git and written under
`data/processed/r1/market=<market>/symbol=<symbol>/timeframe=<timeframe>/year=<year>/`.
Each Parquet partition is UTC and includes `timestamp`, `market`, `symbol`,
`timeframe`, the canonical Binance kline fields, and `provenance`. `timestamp`
is the bar open time; only complete 15-minute buckets are canonical. One-hour
and four-hour rows are strict OHLCV/taker aggregations of complete 15-minute
rows. The source archive URL and SHA-256 are in `archive_manifest.csv`.

External observations are joined with a backward-only as-of join and persist
`source_time`, `source_age`, and a coverage class. Missing history is never
represented as zero or interpolated.
