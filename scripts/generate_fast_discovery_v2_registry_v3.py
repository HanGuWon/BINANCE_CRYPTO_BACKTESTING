"""Generate Fast Discovery V2 registry amendment with BTC/breadth context."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

REGIME_ROWS = [
    {"feature_id": "btc_regime", "kind": "context", "equation": "sign(close / trailing EMA200 - 1) with fixed +/-0.005 bands; NaN during warmup", "polarity": "none", "threshold": "fixed 0.005 context band", "state": "context-state", "signal_values": "+1/0/-1/NaN", "warmup": "EMA200; NaN preserved", "gap_reset": "benchmark-contiguous", "outcome_use": "NO_OUTCOME_ACCESS"},
    {"feature_id": "top50_breadth", "kind": "context", "equation": "mean(selected Top50 close > trailing EMA50) at same market/time", "polarity": "none", "threshold": "NONE", "state": "context-value", "signal_values": "continuous/NaN", "warmup": "EMA50 per segment; NaN preserved", "gap_reset": "segment-local", "outcome_use": "NO_OUTCOME_ACCESS"},
]


def generate(output: Path) -> tuple[Path, str]:
    source = output / "FEATURE_REGISTRY_V2.csv"
    target = output / "FEATURE_REGISTRY_V3.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    rows.extend(REGIME_ROWS)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {"registry": target.name, "registry_sha256": digest, "feature_count": len(rows), "supersedes": "FEATURE_REGISTRY_V2.csv", "reason": "WP13 BTC regime and selected-Top50 breadth context amendment", "holdout": "UNTOUCHED"}
    (output / "REGISTRY_MANIFEST_V3.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target, digest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=Path("campaigns/fast_discovery_v2")); args = parser.parse_args(); path, digest = generate(args.output); print(json.dumps({"registry": str(path), "registry_sha256": digest, "feature_count": 13}, sort_keys=True))
