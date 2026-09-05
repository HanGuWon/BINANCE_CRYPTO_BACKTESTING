"""Fail-closed verifier for the frozen deterministic R2B registry."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from generate_r2b_registry import rows

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "campaigns" / "r2b_restricted_derivatives_v1" / "trial_registry.csv"


def sha256_file(path: Path = REGISTRY) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path: Path = REGISTRY) -> dict[str, object]:
    frame = pd.read_csv(path)
    expected = pd.DataFrame(rows(), columns=frame.columns)
    if not frame.equals(expected):
        raise ValueError("registry differs from deterministic generate_r2b_registry.rows() output")
    required = {"derivatives.premium", "derivatives.premium_zscore"}
    if set(frame.feature_id) != required or set(frame.signal_variant) != {"PRESSURE_CONTINUATION", "CROWDING_REVERSION"}:
        raise ValueError("registry feature/variant family mismatch")
    if set(frame.market) != {"um"} or len(frame) != 72:
        raise ValueError("registry must contain exactly 72 UM rows")
    return {"status": "PASS", "rows": len(frame), "sha256": sha256_file(path), "path": str(path.resolve())}


if __name__ == "__main__":
    print(verify())
