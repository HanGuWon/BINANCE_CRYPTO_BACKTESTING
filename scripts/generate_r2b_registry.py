"""Generate the deterministic pre-outcome R2B hypothesis registry."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "r2b_restricted_derivatives_v1"
OUT = CAMPAIGN / "trial_registry.csv"

FEATURES = (("derivatives.premium", "RAW_PREMIUM"), ("derivatives.premium_zscore", "PREMIUM_ZSCORE90"))
VARIANTS = (("PRESSURE_CONTINUATION", "SIGN_SAME_DIRECTION"), ("CROWDING_REVERSION", "SIGN_OPPOSITE_DIRECTION"))
HORIZONS = {"15m": (4, 16, 48, 96), "1h": (4, 12, 24), "4h": (3, 6)}
SIDES = ("LONG", "SHORT")

def rows() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    trial_no = 1
    for feature_id, _feature_label in FEATURES:
        for variant, rule in VARIANTS:
            for timeframe in ("15m", "1h", "4h"):
                for side in SIDES:
                    for horizon in HORIZONS[timeframe]:
                        out.append({
                            "trial_id": f"R2B{trial_no:04d}",
                            "feature_id": feature_id,
                            "signal_variant": variant,
                            "market": "um",
                            "timeframe": timeframe,
                            "side": side,
                            "cohort": "top50",
                            "horizon_bars": horizon,
                            "signal_rule": rule,
                            "status": "PREREGISTERED_PREOUTCOME",
                        })
                        trial_no += 1
    assert len(out) == 72
    return out

def main() -> None:
    fieldnames = ["trial_id", "feature_id", "signal_variant", "market", "timeframe", "side", "cohort", "horizon_bars", "signal_rule", "status"]
    generated = rows()
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(generated)
    print(f"wrote {len(generated)} rows to {OUT}")

if __name__ == "__main__":
    main()
