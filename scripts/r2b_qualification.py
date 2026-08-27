"""Fail-closed R2B qualification contract owner.

R2B remains pre-outcome while premium signal semantics are undefined.  This
module validates the restricted UM-only matrix and deliberately refuses to
execute or report qualification until every registry row has reviewed signal
semantics.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "r2b_restricted_derivatives_v1"
HORIZONS = {"15m": {4, 16, 48, 96}, "1h": {4, 12, 24}, "4h": {3, 6}}
FEATURES = {"derivatives.premium", "derivatives.premium_zscore"}


def validate_um_matrix(registry_path: Path = CAMPAIGN / "trial_registry.csv") -> dict[str, object]:
    registry = pd.read_csv(registry_path)
    errors: list[str] = []
    if len(registry) != 36:
        errors.append(f"expected 36 metadata rows, found {len(registry)}")
    if set(registry.market) != {"um"}:
        errors.append("R2B qualification is UM-only; Spot rows are forbidden")
    if set(registry.feature_id) != FEATURES:
        errors.append("registry must contain exactly the two restricted premium features")
    if set(registry.timeframe) != set(HORIZONS):
        errors.append("registry must cover 15m, 1h, and 4h")
    for timeframe, horizons in HORIZONS.items():
        subset = registry[registry.timeframe.eq(timeframe)]
        if set(subset.side) != {"LONG", "SHORT"}:
            errors.append(f"{timeframe}: both UM sides are required")
        if set(subset.horizon_bars.astype(int)) != horizons:
            errors.append(f"{timeframe}: horizon set mismatch")
    return {
        "valid": not errors,
        "errors": errors,
        "rows": int(len(registry)),
        "market": "um",
        "timeframes": sorted(set(registry.timeframe)),
        "sides": sorted(set(registry.side)),
    }


def qualification_gate(registry_path: Path = CAMPAIGN / "trial_registry.csv") -> dict[str, object]:
    matrix = validate_um_matrix(registry_path)
    if not matrix["valid"]:
        return {"status": "INVALID_CONTRACT", "matrix": matrix}
    registry = pd.read_csv(registry_path)
    undefined = registry[registry.signal_rule.astype(str).str.startswith("UNDEFINED")]
    if len(undefined) or set(registry.status) != {"BLOCKED_IMPLEMENTATION"}:
        return {
            "status": "BLOCKED_SIGNAL_SEMANTICS",
            "reason": "No reviewed directional semantics; no optimized/reference execution is permitted.",
            "matrix": matrix,
            "undefined_rows": int(len(undefined)),
            "outcome_run_started": False,
            "final_holdout_status": "UNTOUCHED",
        }
    return {"status": "READY_FOR_QUALIFICATION", "matrix": matrix}


if __name__ == "__main__":
    import json
    import sys

    result = qualification_gate()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "READY_FOR_QUALIFICATION" else 2)
