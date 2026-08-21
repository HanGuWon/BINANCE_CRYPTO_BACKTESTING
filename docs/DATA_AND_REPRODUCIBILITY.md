# Data and Reproducibility Policy

1. Source code, configuration, tests, and reviewed research documentation are
   version controlled.
2. Raw Binance data is immutable in the local/object-store acquisition layer but
   is not committed to Git.
3. Each acquired official archive retains its source URL, published checksum,
   computed checksum, timestamp coverage, row count, and integrity result in a
   manifest.
4. Generated research artifacts are reproducible outputs and are normally not
   version controlled.
5. Important conclusions should be summarized in reviewed Markdown and reference
   the code commit SHA, config hash, dataset hash/manifest, and experiment ID.
6. A survivor-only current universe must not silently replace lifecycle-aware
   historical coverage.
7. Missing derivatives history must never be fabricated or backfilled from an
   unrelated venue.
