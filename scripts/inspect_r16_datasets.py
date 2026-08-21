"""Bounded schema and coverage inspection for present UM Vision datasets."""

from __future__ import annotations

import argparse
import io
import re
import zipfile
from pathlib import Path

import pandas as pd

from binance_research.data import BinanceArchiveClient, sha256_bytes


DAY_RE = re.compile(r"-(\d{4})-(\d{2})-(\d{2})\.zip$")


def inspect_symbol(client: BinanceArchiveClient, dataset: str, symbol: str = "BTCUSDT") -> dict[str, object]:
    prefix = f"data/futures/um/daily/{dataset}/{symbol}/"
    _, objects, pages = client.list_objects_v2(prefix)
    zips = [obj for obj in objects if obj.key.endswith(".zip")]
    if not zips:
        return {"dataset": dataset, "symbol": symbol, "status": "EMPTY_OR_UNLISTED_AT_THE_PROBED_PATH", "pages": pages}
    sample = zips[0]
    payload = client._fetch(f"https://data.binance.vision/{sample.key}")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        member = next(name for name in archive.namelist() if not name.endswith("/"))
        raw = archive.read(member)
    table = pd.read_csv(io.BytesIO(raw), header=None)
    return {
        "dataset": dataset,
        "symbol": symbol,
        "status": "PRESENT",
        "pages": pages,
        "object_count": len(zips),
        "first_verified_object": zips[0].key,
        "last_verified_object": zips[-1].key,
        "first_object_last_modified": zips[0].last_modified,
        "last_object_last_modified": zips[-1].last_modified,
        "sample_rows": len(table),
        "sample_columns": table.shape[1],
        "sample_header_or_first_row": "|".join(str(value) for value in table.iloc[0].tolist()),
        "sample_sha256": sha256_bytes(payload),
        "timestamp_semantics": "first column is dataset timestamp; schema requires source-specific verification",
        "sampling_frequency": "daily archive object; row frequency inspected from sample",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1/dataset_semantics.csv"))
    args = parser.parse_args()
    client = BinanceArchiveClient(Path("data/raw"), timeout=90, max_retries=3)
    rows = [inspect_symbol(client, dataset) for dataset in ("metrics", "bookTicker", "bookDepth")]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output, index=False)
    print(pd.DataFrame(rows).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
