"""Real pre-holdout optimized-vs-slow parity qualification for R2B."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from r2b_historical_runner import (
    REQUIRED_TRADE_FIELDS, STEP, derive_execution_segments, execute_frame, load_funding, load_registry,
    prepare_symbol,
)
from r2b_signals import FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def slow_execute(panel: pd.DataFrame, trial: dict[str, object], validation_start: pd.Timestamp, validation_end: pd.Timestamp, funding: pd.DataFrame) -> pd.DataFrame:
    feature = FEATURE_COLUMNS[str(trial["feature_id"])]
    variant = str(trial["signal_variant"])
    side = str(trial["side"])
    direction = 1.0 if side == "LONG" else -1.0
    required = 1.0 if side == "LONG" else -1.0
    horizon = int(trial["horizon_bars"])
    rows = []
    segment_column = "execution_segment_id" if "execution_segment_id" in panel else "segment_id"
    for _, segment in panel.groupby(segment_column, sort=False):
        positions = segment.index.to_list()
        next_available = -1
        values = panel.loc[positions, feature].tolist() if feature in panel else [math.nan] * len(positions)
        for local, pos in enumerate(positions):
            decision_time = panel.at[pos, "timestamp"]
            if decision_time < validation_start or decision_time >= validation_end or local <= next_available:
                continue
            try:
                value = float(values[local])
            except (TypeError, ValueError):
                value = math.nan
            if not math.isfinite(value) or value == 0:
                continue
            raw = (1.0 if value > 0 else -1.0) if variant == "PRESSURE_CONTINUATION" else (-1.0 if value > 0 else 1.0)
            if raw != required or local + horizon + 1 >= len(positions):
                continue
            entry_pos, exit_pos = positions[local + 1], positions[local + horizon + 1]
            entry_open, exit_open = panel.at[entry_pos, "open"], panel.at[exit_pos, "open"]
            if not np.isfinite(entry_open) or not np.isfinite(exit_open) or float(entry_open) <= 0:
                continue
            entry_time, exit_time = panel.at[entry_pos, "timestamp"], panel.at[exit_pos, "timestamp"]
            cashflow = 0.0
            for event in funding.itertuples(index=False):
                if event.timestamp > entry_time and event.timestamp <= exit_time:
                    cashflow += -direction * float(event.funding_rate)
            gross = direction * (float(exit_open) / float(entry_open) - 1.0)
            rows.append({
                "decision_time": decision_time, "symbol": str(panel.at[pos, "symbol"]), "side": side,
                "signal_variant": variant, "signal_value": raw, "source_open_time": panel.at[pos, "source_open_time"],
                "source_available_time": panel.at[pos, "source_available_time"], "entry_time": entry_time,
                "exit_time": exit_time, "gross_return": gross, "funding_cashflow": cashflow,
                "net_return": gross - 0.002 + cashflow,
            })
            next_available = local + horizon + 1
    return pd.DataFrame(rows, columns=REQUIRED_TRADE_FIELDS)


def _adversarial_fixtures() -> list[dict[str, object]]:
    ts = pd.to_datetime(["2020-10-31 23:45Z", "2020-12-01 00:00Z", "2020-12-01 00:15Z", "2020-12-01 00:30Z"])
    base = pd.DataFrame({"timestamp": ts, "segment_id": [0, 0, 0, 0], "symbol": ["IOTAUSDT"] * 4, "open": [100.0, 101.0, 102.0, 103.0], "premium": [1.0, -1.0, -1.0, -1.0], "source_open_time": ts, "source_available_time": ts - pd.Timedelta(minutes=1)})
    price_gap = base.copy(); price_gap.loc[1, "open"] = np.nan
    segment_gap = base.copy(); segment_gap.loc[2:, "segment_id"] = 1
    return [{"name": "membership_gap", "panel": base}, {"name": "original_segment_gap", "panel": segment_gap}, {"name": "missing_execution_price", "panel": price_gap}]


def _canon(frame: pd.DataFrame) -> list[tuple[object, ...]]:
    if frame.empty:
        return []
    out = frame.copy()
    for col in ("decision_time", "source_open_time", "source_available_time", "entry_time", "exit_time"):
        out[col] = pd.to_datetime(out[col], utc=True).astype("int64")
    for col in ("signal_value", "gross_return", "funding_cashflow", "net_return"):
        out[col] = out[col].astype(float).round(15)
    return [tuple(row) for row in out[list(REQUIRED_TRADE_FIELDS)].sort_values(["decision_time", "side"]).itertuples(index=False, name=None)]


def run_realdata_qualification() -> dict[str, object]:
    trials, folds = load_registry()
    # F02 is the first deterministic block with complete BTCUSDT UM history
    # in the repaired root; F01 predates the archive's causal start.
    # Use a deterministic pre-holdout slice that contains both observed
    # positive and negative BTC funding events (September 2020).
    fold_by_tf = {tf: next(f for f in folds if f["timeframe"] == tf and f["fold_id"] == "F02") for tf in STEP}
    compared = 0
    matrix = []
    adversarial = []
    fixture_trial = {"timeframe": "15m", "side": "LONG", "horizon_bars": 1, "feature_id": "derivatives.premium", "signal_variant": "PRESSURE_CONTINUATION"}
    for fixture in _adversarial_fixtures():
        panel = derive_execution_segments(fixture["panel"], "15m")
        fast = execute_frame(panel, fixture_trial, pd.Timestamp("2020-10-01", tz="UTC"), pd.Timestamp("2021-01-01", tz="UTC"), pd.DataFrame(columns=["timestamp", "funding_rate"]))
        slow = slow_execute(panel, fixture_trial, pd.Timestamp("2020-10-01", tz="UTC"), pd.Timestamp("2021-01-01", tz="UTC"), pd.DataFrame(columns=["timestamp", "funding_rate"]))
        if _canon(fast) != _canon(slow) or not fast.empty:
            raise AssertionError(f"adversarial continuity failure: {fixture['name']}")
        adversarial.append({"name": fixture["name"], "execution_segments": int(panel.execution_segment_id.nunique()), "records": len(fast)})
    actual_funding_signs = set()
    for tf, fold in fold_by_tf.items():
        start = pd.Timestamp("2020-08-01T00:00:00Z")
        validation_start = pd.Timestamp("2020-09-14T00:00:00Z")
        validation_end = pd.Timestamp("2020-09-20T00:00:00Z")
        panel = prepare_symbol("BTCUSDT", tf, start, validation_end)
        if panel.empty:
            raise RuntimeError(f"missing real panel for {tf}")
        # Keep parity deliberately small while retaining warmup, a gap-aware
        # history window, and every registered horizon for the timeframe.
        panel = panel[(panel.timestamp >= validation_start - STEP[tf] * 260) & (panel.timestamp < validation_start + STEP[tf] * 320)].reset_index(drop=True)
        if len(panel) > 120:
            gap_at = len(panel) // 2
            panel = panel.drop(index=gap_at).reset_index(drop=True)
            panel.loc[gap_at:, "segment_id"] = panel.loc[gap_at:, "segment_id"].astype(int) + 1
            panel = derive_execution_segments(panel, tf)
        funding = load_funding("BTCUSDT")
        funding = funding[(funding.timestamp >= panel.timestamp.min()) & (funding.timestamp <= panel.timestamp.max())].reset_index(drop=True)
        in_slice = funding[(funding.timestamp >= validation_start) & (funding.timestamp < validation_end)]
        actual_funding_signs.update(np.sign(in_slice.funding_rate.astype(float)).tolist())
        tf_trials = [t for t in trials if t["timeframe"] == tf]
        for trial in tf_trials:
            funding_cases = {"actual": funding, "none": funding.iloc[0:0].copy()}
            if not in_slice.empty:
                anchor = in_slice.iloc[0].timestamp
                funding_cases["positive_synthetic"] = pd.DataFrame({"timestamp": [anchor], "funding_rate": [0.001]})
                funding_cases["negative_synthetic"] = pd.DataFrame({"timestamp": [anchor], "funding_rate": [-0.001]})
            for funding_case, funding_input in funding_cases.items():
                fast = execute_frame(panel, trial, validation_start, validation_end, funding_input)
                slow = slow_execute(panel, trial, validation_start, validation_end, funding_input)
                if _canon(fast) != _canon(slow):
                    raise AssertionError(f"real-data parity mismatch {tf}/{trial['trial_id']}/{funding_case}")
                compared += len(fast)
        matrix.append({"timeframe": tf, "symbol": "BTCUSDT", "sides": ["LONG", "SHORT"], "horizons": sorted({int(t["horizon_bars"]) for t in tf_trials}), "trials": len(tf_trials), "gap_segments_observed": bool(panel.segment_id.nunique() > 1)})
    return {"status": "PASS", "mode": "REAL_PRE_HOLDOUT_REFERENCE", "symbol": "BTCUSDT", "matrix": matrix, "adversarial_fixtures": adversarial, "records_compared": compared, "actual_funding_signs": sorted(actual_funding_signs), "synthetic_funding_cases": ["positive_synthetic", "negative_synthetic", "none"], "final_holdout_status": "UNTOUCHED", "outcome_run_started": False}


if __name__ == "__main__":
    print(json.dumps(run_realdata_qualification(), indent=2, sort_keys=True, default=str))
