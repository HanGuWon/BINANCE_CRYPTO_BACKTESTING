"""Generate the amended Fast Discovery V2 registry with causal context rows."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from binance_research.fast_discovery_signals import S0_SIGNAL_SEMANTICS


CONTEXT_ROWS = [
    {"feature_id": "relative_strength_24h", "kind": "continuous", "equation": "symbol_return_24h - BTC_return_24h; trailing within symbol segment", "polarity": "none", "threshold": "NONE", "state": "continuous-value", "signal_values": "continuous/NaN", "warmup": "lookback-defined; NaN preserved", "gap_reset": "segment-local", "outcome_use": "NO_OUTCOME_ACCESS"},
    {"feature_id": "relative_strength_rank", "kind": "continuous", "equation": "percentile rank of relative_strength_24h among selected Top50 at same market/time", "polarity": "none", "threshold": "NONE", "state": "continuous-value", "signal_values": "continuous/NaN", "warmup": "lookback-defined; NaN preserved", "gap_reset": "segment-local", "outcome_use": "NO_OUTCOME_ACCESS"},
]


def generate(output: Path) -> tuple[Path, str]:
    output.mkdir(parents=True, exist_ok=True)
    path = output / "FEATURE_REGISTRY_V2.csv"
    fields = ["feature_id", "kind", "equation", "polarity", "threshold", "state", "signal_values", "warmup", "gap_reset", "outcome_use"]
    rows = []
    for feature_id, spec in S0_SIGNAL_SEMANTICS.items():
        directional = spec["kind"] == "directional"
        rows.append({"feature_id": feature_id, "kind": spec["kind"], "equation": spec["equation"], "polarity": spec["polarity"], "threshold": "sign-boundary" if directional else "NONE", "state": "state" if directional else "continuous-value", "signal_values": "+1/0/-1/NaN" if directional else "continuous/NaN", "warmup": "feature-defined; NaN preserved", "gap_reset": "segment-local", "outcome_use": "NO_OUTCOME_ACCESS"})
    rows.extend(CONTEXT_ROWS)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"registry": path.name, "registry_sha256": digest, "feature_count": len(rows), "supersedes": "FEATURE_REGISTRY.csv", "reason": "WP12 causal relative-strength context amendment", "holdout": "UNTOUCHED"}
    (output / "REGISTRY_MANIFEST_V2.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path, digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("campaigns/fast_discovery_v2"))
    args = parser.parse_args()
    path, digest = generate(args.output)
    print(json.dumps({"registry": str(path), "registry_sha256": digest, "feature_count": 11}, sort_keys=True))
