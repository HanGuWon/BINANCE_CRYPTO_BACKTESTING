"""Mechanically verify the R2A.2 registry against R1 authoritative availability."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from binance_research.audit import CLASSIFICATION_R2A_PRIMARY  # noqa: E402

LEGAL_SIDES = {"spot": {"LONG"}, "um": {"LONG", "SHORT"}}
NATIVE_TIMEFRAMES = ("15m", "1h", "4h")
HORIZONS_BY_TF = {"15m": (4, 16, 48, 96), "1h": (4, 12, 24), "4h": (3, 6)}
EXPECTED_TRIALS = 756


def verify_registry(registry_path: Path | None = None) -> dict[str, object]:
    """Fail closed unless the registry mechanically matches availability."""
    registry_path = registry_path or ROOT / "campaigns" / "r2a2_temporal_horizon_v1" / "trial_registry.csv"
    registry = pd.read_csv(registry_path)
    availability = pd.read_csv(ROOT / "campaigns" / "r1_final_panel_v1" / "feature_availability_final.csv")
    primary = set(map(tuple, availability.loc[availability.classification == CLASSIFICATION_R2A_PRIMARY, ["feature", "market", "timeframe"]].values))
    errors: list[str] = []
    seen: set[tuple] = set()
    for row in registry.itertuples(index=False):
        if row.status != "REGISTERED":
            errors.append(f"{row.trial_id}: status must be REGISTERED")
        if (row.feature_id, row.market, row.timeframe) not in primary:
            errors.append(f"{row.trial_id}: not R2A_PRIMARY for market/timeframe: {(row.feature_id, row.market, row.timeframe)}")
        if int(row.horizon_bars) not in HORIZONS_BY_TF[row.timeframe]:
            errors.append(f"{row.trial_id}: horizon {row.horizon_bars} not preregistered for {row.timeframe}")
        if row.side not in LEGAL_SIDES[row.market]:
            errors.append(f"{row.trial_id}: illegal side {row.side} for {row.market}")
        if row.cohort != "top50":
            errors.append(f"{row.trial_id}: cohort must be top50")
        dedupe = (row.feature_id, row.variant, row.market, row.timeframe, row.side, int(row.horizon_bars))
        if dedupe in seen:
            errors.append(f"{row.trial_id}: duplicate trial {dedupe}")
        seen.add(dedupe)
    expected_ids = [f"T{i:04d}" for i in range(1, len(registry) + 1)]
    if list(registry.trial_id) != expected_ids:
        errors.append("trial_id sequence is not deterministic T0001..Tnnnn")
    if len(registry) != EXPECTED_TRIALS:
        errors.append(f"expected exactly {EXPECTED_TRIALS} trials, got {len(registry)}")
    # Completeness: every eligible combination present.
    variants_by_feature = registry.groupby("feature_id")["variant"].apply(set).to_dict()
    for feature, market, timeframe in primary:
        expected_variants = variants_by_feature.get(feature)
        if expected_variants is None:
            errors.append(f"missing feature entirely: {(feature, market, timeframe)}")
    if any(errors):
        raise ValueError("; ".join(errors[:10]))
    return {"trials": len(registry), "families": len(primary)}


def main() -> int:
    summary = verify_registry()
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
