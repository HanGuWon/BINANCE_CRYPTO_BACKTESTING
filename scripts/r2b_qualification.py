"""Synthetic, outcome-blind qualification for the frozen R2B signal family.

The qualification deliberately does not load the repaired historical root. A
vectorized implementation is compared with a separately written slow
reference over the complete UM registry matrix and constructed funding/gap
fixtures. This is a correctness gate, not a performance experiment.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from r2b_signals import FEATURE_COLUMNS, SIGNAL_VARIANTS, signal_from_frame, side_accepts_signal

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "r2b_restricted_derivatives_v1"
HORIZONS = {"15m": {4, 16, 48, 96}, "1h": {4, 12, 24}, "4h": {3, 6}}
FEATURES = set(FEATURE_COLUMNS)
REQUIRED_FIELDS = (
    "decision_time", "symbol", "side", "signal_variant", "signal_value",
    "source_open_time", "source_available_time", "entry_time", "exit_time",
    "gross_return", "funding_cashflow", "net_return",
)
STEP = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}


def validate_um_matrix(registry_path: Path = CAMPAIGN / "trial_registry.csv") -> dict[str, object]:
    registry = pd.read_csv(registry_path)
    errors: list[str] = []
    if len(registry) != 72:
        errors.append(f"expected 72 preregistered rows, found {len(registry)}")
    if set(registry.market) != {"um"}:
        errors.append("R2B qualification is UM-only; Spot rows are forbidden")
    if set(registry.feature_id) != FEATURES:
        errors.append("registry must contain exactly the two restricted premium features")
    if set(registry.signal_variant) != set(SIGNAL_VARIANTS):
        errors.append("registry must contain both frozen signal variants")
    if set(registry.timeframe) != set(HORIZONS):
        errors.append("registry must cover 15m, 1h, and 4h")
    for timeframe, horizons in HORIZONS.items():
        subset = registry[registry.timeframe.eq(timeframe)]
        if set(subset.side) != {"LONG", "SHORT"}:
            errors.append(f"{timeframe}: both UM sides are required")
        if set(subset.horizon_bars.astype(int)) != horizons:
            errors.append(f"{timeframe}: horizon set mismatch")
        for feature in FEATURES:
            for variant in SIGNAL_VARIANTS:
                selected = subset[(subset.feature_id == feature) & (subset.signal_variant == variant)]
                if set(selected.horizon_bars.astype(int)) != horizons or set(selected.side) != {"LONG", "SHORT"}:
                    errors.append(f"{timeframe}/{feature}/{variant}: incomplete matrix")
    return {
        "valid": not errors, "errors": errors, "rows": int(len(registry)),
        "market": "um", "timeframes": sorted(set(registry.timeframe)),
        "sides": sorted(set(registry.side)), "variants": sorted(set(registry.signal_variant)),
    }


def qualification_gate(registry_path: Path = CAMPAIGN / "trial_registry.csv") -> dict[str, object]:
    matrix = validate_um_matrix(registry_path)
    if not matrix["valid"]:
        return {"status": "INVALID_CONTRACT", "matrix": matrix}
    registry = pd.read_csv(registry_path)
    undefined = registry[registry.signal_rule.astype(str).str.startswith("UNDEFINED")]
    if len(undefined) or set(registry.status) != {"PREREGISTERED_PREOUTCOME"}:
        return {
            "status": "BLOCKED_SIGNAL_SEMANTICS",
            "reason": "reviewed frozen semantics are required before qualification",
            "matrix": matrix, "undefined_rows": int(len(undefined)),
            "outcome_run_started": False, "final_holdout_status": "UNTOUCHED",
        }
    return {"status": "READY_FOR_QUALIFICATION", "matrix": matrix}


def _synthetic_panel(timeframe: str, *, missing: bool = False) -> pd.DataFrame:
    """Construct a deterministic two-segment UM panel with causal metadata."""
    step = STEP[timeframe]
    count = 220
    start = pd.Timestamp("2023-01-01T00:00:00Z")
    timestamps = [start + step * i for i in range(count)]
    gap_at = 110
    timestamps[gap_at:] = [timestamps[gap_at - 1] + step * 3 + step * (i - gap_at) for i in range(gap_at, count)]
    idx = np.arange(count, dtype=float)
    opens = 100.0 + 0.04 * idx + 0.8 * np.sin(idx / 7.0)
    premium = np.where((idx.astype(int) % 11) == 0, 0.0, np.where((idx.astype(int) % 2) == 0, 0.002, -0.002))
    zscore = np.where((idx.astype(int) % 13) == 0, np.nan, np.where((idx.astype(int) % 3) == 0, 1.5, -1.5))
    segment = np.where(idx < gap_at, 0, 1)
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps, utc=True),
        "source_open_time": pd.to_datetime(timestamps, utc=True),
        "source_available_time": pd.to_datetime(timestamps, utc=True) + step - pd.Timedelta(microseconds=1),
        "symbol": "SYNTHUSDT", "market": "um", "timeframe": timeframe,
        "open": opens, "premium": premium, "premium_zscore90": zscore,
        "segment_id": segment.astype(int), "universe_month": "2023-01",
        "row_class": "RESEARCH_ELIGIBLE",
    })
    if missing:
        frame.loc[[0, 7, 17], ["premium", "premium_zscore90"]] = np.nan
    return frame


def _funding_fixture(panel: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode not in {"positive", "negative", "none"}:
        raise ValueError(mode)
    if mode == "none":
        return pd.DataFrame({"timestamp": pd.Series([], dtype="datetime64[ns, UTC]"), "funding_rate": pd.Series([], dtype=float)})
    step = STEP[str(panel.timeframe.iloc[0])]
    stamps = [panel.timestamp.iloc[2] + step * 2, panel.timestamp.iloc[20] + step * 2, panel.timestamp.iloc[130] + step]
    rate = 0.001 if mode == "positive" else -0.001
    return pd.DataFrame({"timestamp": pd.to_datetime(stamps, utc=True), "funding_rate": [rate, rate / 2, rate]})


def _optimized_execute(panel: pd.DataFrame, feature: str, variant: str, side: str, horizon: int, funding: pd.DataFrame) -> pd.DataFrame:
    signals = signal_from_frame(panel, feature, variant, segment_column="segment_id")
    rows: list[dict[str, object]] = []
    direction = 1.0 if side == "LONG" else -1.0
    for _, segment in panel.groupby("segment_id", sort=False):
        positions = segment.index.to_list()
        for local_decision, absolute_decision in enumerate(positions):
            raw = float(signals.iloc[absolute_decision]) if pd.notna(signals.iloc[absolute_decision]) else math.nan
            if not side_accepts_signal(raw, side) or local_decision + horizon + 1 >= len(positions):
                continue
            entry_pos, exit_pos = positions[local_decision + 1], positions[local_decision + horizon + 1]
            entry_ts, exit_ts = panel.loc[entry_pos, "timestamp"], panel.loc[exit_pos, "timestamp"]
            crossed = funding[(funding.timestamp > entry_ts) & (funding.timestamp <= exit_ts)]
            funding_cashflow = -direction * float(crossed.funding_rate.sum())
            gross = direction * (float(panel.loc[exit_pos, "open"]) / float(panel.loc[entry_pos, "open"]) - 1.0)
            rows.append({
                "decision_time": panel.loc[absolute_decision, "timestamp"], "symbol": panel.loc[absolute_decision, "symbol"],
                "side": side, "signal_variant": variant, "signal_value": raw,
                "source_open_time": panel.loc[absolute_decision, "source_open_time"],
                "source_available_time": panel.loc[absolute_decision, "source_available_time"],
                "entry_time": entry_ts, "exit_time": exit_ts, "gross_return": gross,
                "funding_cashflow": funding_cashflow, "net_return": gross - 0.002 + funding_cashflow,
            })
    return pd.DataFrame(rows, columns=REQUIRED_FIELDS)


def _reference_signal(panel: pd.DataFrame, feature: str, variant: str) -> pd.Series:
    """Slow scalar reference; intentionally does not call the optimized mapper."""
    source = FEATURE_COLUMNS[feature]
    if source not in panel:
        return pd.Series(np.nan, index=panel.index, dtype=float)
    output: list[float] = []
    for value in panel[source].tolist():
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = math.nan
        if not math.isfinite(value):
            output.append(math.nan)
        elif value == 0.0:
            output.append(0.0)
        elif variant == "PRESSURE_CONTINUATION":
            output.append(1.0 if value > 0 else -1.0)
        else:
            output.append(-1.0 if value > 0 else 1.0)
    return pd.Series(output, index=panel.index, dtype=float)


def _reference_execute(panel: pd.DataFrame, feature: str, variant: str, side: str, horizon: int, funding: pd.DataFrame) -> pd.DataFrame:
    signals = _reference_signal(panel, feature, variant)
    rows: list[dict[str, object]] = []
    direction = 1.0 if side == "LONG" else -1.0
    required = 1.0 if side == "LONG" else -1.0
    for _, segment in panel.groupby("segment_id", sort=False):
        positions = segment.index.to_list()
        for local_decision, absolute_decision in enumerate(positions):
            raw = signals.iloc[absolute_decision]
            if not math.isfinite(raw) or raw != required or local_decision + horizon + 1 >= len(positions):
                continue
            entry_pos, exit_pos = positions[local_decision + 1], positions[local_decision + horizon + 1]
            entry_ts, exit_ts = panel.loc[entry_pos, "timestamp"], panel.loc[exit_pos, "timestamp"]
            cashflow = 0.0
            for event in funding.itertuples(index=False):
                if event.timestamp > entry_ts and event.timestamp <= exit_ts:
                    cashflow += -direction * float(event.funding_rate)
            gross = direction * (float(panel.loc[exit_pos, "open"]) / float(panel.loc[entry_pos, "open"]) - 1.0)
            rows.append({
                "decision_time": panel.loc[absolute_decision, "timestamp"], "symbol": panel.loc[absolute_decision, "symbol"],
                "side": side, "signal_variant": variant, "signal_value": float(raw),
                "source_open_time": panel.loc[absolute_decision, "source_open_time"],
                "source_available_time": panel.loc[absolute_decision, "source_available_time"],
                "entry_time": entry_ts, "exit_time": exit_ts, "gross_return": gross,
                "funding_cashflow": cashflow, "net_return": gross - 0.002 + cashflow,
            })
    return pd.DataFrame(rows, columns=REQUIRED_FIELDS)


def _canonical_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    values = frame.copy()
    for column in ("decision_time", "source_open_time", "source_available_time", "entry_time", "exit_time"):
        values[column] = pd.to_datetime(values[column], utc=True).astype("int64")
    for column in ("signal_value", "gross_return", "funding_cashflow", "net_return"):
        values[column] = values[column].astype(float).round(15)
    values = values.sort_values(["decision_time", "side", "signal_variant"]).reset_index(drop=True)
    return values[list(REQUIRED_FIELDS)].to_dict("records")


def run_qualification() -> dict[str, object]:
    gate = qualification_gate()
    if gate["status"] != "READY_FOR_QUALIFICATION":
        return {"status": gate["status"], "gate": gate, "outcome_run_started": False}
    compared = 0
    scenarios = []
    for timeframe in ("15m", "1h", "4h"):
        for missing in (False, True):
            panel = _synthetic_panel(timeframe, missing=missing)
            for funding_mode in ("positive", "negative", "none"):
                funding = _funding_fixture(panel, funding_mode)
                for feature in sorted(FEATURES):
                    for variant in SIGNAL_VARIANTS:
                        for side in ("LONG", "SHORT"):
                            for horizon in sorted(HORIZONS[timeframe]):
                                fast = _optimized_execute(panel, feature, variant, side, horizon, funding)
                                slow = _reference_execute(panel, feature, variant, side, horizon, funding)
                                fast_records, slow_records = _canonical_records(fast), _canonical_records(slow)
                                if fast_records != slow_records:
                                    raise AssertionError(f"optimized/reference mismatch: {timeframe}/{feature}/{variant}/{side}/{horizon}/{funding_mode}/missing={missing}")
                                compared += len(fast_records)
                scenarios.append({"timeframe": timeframe, "missing_premium": missing, "funding": funding_mode, "gap_segment": True})
    return {
        "status": "PASS", "mode": "SYNTHETIC_REFERENCE_ONLY", "market": "um",
        "spot_control_status": "OUT_OF_SCOPE_ENGINE_CONTROL_ONLY", "scenarios": scenarios,
        "matrix": {"timeframes": ["15m", "1h", "4h"], "sides": ["LONG", "SHORT"], "features": sorted(FEATURES), "variants": list(SIGNAL_VARIANTS), "horizons": {k: sorted(v) for k, v in HORIZONS.items()}},
        "records_compared": compared, "required_fields": list(REQUIRED_FIELDS),
        "outcome_run_started": False, "final_holdout_status": "UNTOUCHED",
    }


def write_receipt(result: dict[str, object], path: Path = CAMPAIGN / "qualification_receipt.json") -> dict[str, object]:
    payload = dict(result)
    payload["receipt_sha256"] = None
    encoded = json.dumps(payload, sort_keys=True, indent=2, default=str).encode("utf-8")
    payload["receipt_sha256"] = hashlib.sha256(encoded).hexdigest()
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = run_qualification()
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    if result["status"] == "PASS":
        write_receipt(result)
        raise SystemExit(0)
    raise SystemExit(2)
