"""Deterministically generate the preregistered Fast Discovery V2 S0 registry."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from binance_research.fast_discovery_signals import S0_SIGNAL_SEMANTICS


def generate(output: Path) -> tuple[Path, str]:
    output.mkdir(parents=True, exist_ok=True)
    registry = output / "FEATURE_REGISTRY.csv"
    fields = ["feature_id", "kind", "equation", "polarity", "threshold", "state", "signal_values", "warmup", "gap_reset", "outcome_use"]
    with registry.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for feature_id, spec in S0_SIGNAL_SEMANTICS.items():
            directional = spec["kind"] == "directional"
            writer.writerow({"feature_id": feature_id, "kind": spec["kind"], "equation": spec["equation"], "polarity": spec["polarity"], "threshold": "sign-boundary" if directional else "NONE", "state": "state" if directional else "continuous-value", "signal_values": "+1/0/-1/NaN" if directional else "continuous/NaN", "warmup": "feature-defined; NaN preserved", "gap_reset": "segment-local", "outcome_use": "NO_OUTCOME_ACCESS"})
    digest = hashlib.sha256(registry.read_bytes()).hexdigest()
    manifest = {"registry": registry.name, "registry_sha256": digest, "feature_count": len(S0_SIGNAL_SEMANTICS), "protocol": "FAST_DISCOVERY_V2", "holdout": "UNTOUCHED"}
    (output / "REGISTRY_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return registry, digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("campaigns/fast_discovery_v2"))
    args = parser.parse_args()
    path, digest = generate(args.output)
    print(json.dumps({"registry": str(path), "registry_sha256": digest, "feature_count": len(S0_SIGNAL_SEMANTICS)}, sort_keys=True))
