# R1.5 panel schema

Raw objects remain under ignored `data/raw/<market>/...`; metadata manifests
retain URL, object size, S3 LastModified, ETag, download time, published and
computed SHA-256, row counts, timestamps, and quality flags. Full-history anchor
Parquet is under ignored `data/processed/r1_full_history/`, partitioned by
market, symbol, timeframe, and year, with UTC timestamps and provenance.

The canonical 15m source is resampled to 1h/4h only within contiguous source
runs. Complete target buckets are retained; partial or gap-crossing buckets are
dropped and recorded as quality issues. Funding is event-timestamped and never
converted to an invented hourly zero series. Premium-index values may be
negative and use a signed-series validator rather than OHLC non-negativity.
