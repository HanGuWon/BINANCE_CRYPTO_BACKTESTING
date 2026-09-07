"""R2A.2 campaign runner: fold-aware, horizon-aware, checkpointed.

Reuses the corrected R2A engine (next-open execution, correct funding sign,
holdout-guarded loader). Checkpoints live on D: keyed by
trial_id/fold_id; resumed runs never recompute completed units with different
settings (registry SHA pinned in run_manifest.json).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from r2a_engine import (  # noqa: E402
    assert_no_holdout,
    load_panel_pre_holdout,
)
from r2a2_folds import split_for_fold  # noqa: E402

CAMPAIGN = ROOT / "campaigns" / "r2a2_temporal_horizon_v1"
DATA_ROOT = Path("data/processed/r1_gap_safe_cohort")
CHECKPOINT_ROOT = Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a2/checkpoints")
MARKETS = ("spot", "um")
TIMEFRAMES = ("15m", "1h", "4h")
COSTS = {"spot": {"fee": 10.0 / 10_000, "slip": 2 * 5.0 / 10_000}, "um": {"fee": 5.0 / 10_000, "slip": 2 * 5.0 / 10_000}}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _load_universe_top50(market: str) -> set[tuple[str, str, str]]:
    universe = pd.read_csv(ROOT / "campaigns" / "r1_final_panel_v1" / "universe_monthly.csv", usecols=["market", "universe_month", "symbol", "selected_top50"])
    selected = universe[(universe.market == market) & universe.selected_top50.astype(bool)]
    return {(row.market, str(row.universe_month), row.symbol) for row in selected.itertuples(index=False)}


def execute_trial_fold(trial: dict, panel_fold: pd.DataFrame, universe_top50: set[tuple[str, str, str]], funding_cache: dict) -> pd.DataFrame:
    """Execute one trial on ONE FOLD's pre-holdout panel (non-overlapping)."""
    from r2a_engine import compute_signal, _funding_events
    assert_no_holdout(panel_fold, timeframe=trial["timeframe"], context=trial["trial_id"])
    market, timeframe, side = trial["market"], trial["timeframe"], trial["side"]
    direction_base = 1 if side == "LONG" else -1
    costs = COSTS[market]
    fee = costs["fee"] * 2 if False else costs["fee"]
    slip_total = costs["slip"]
    fee_total = 2 * costs["fee"]
    records = []
    next_available = 0
    n = len(panel_fold)
    opens = panel_fold["open"].astype(float).to_numpy()
    stamps = pd.to_datetime(panel_fold["timestamp"], utc=True)
    # compute_signal resets its own index; guard against any length mismatch.
    signal = compute_signal(panel_fold.reset_index(drop=True), trial["feature_id"], trial["variant"], market)
    if len(signal) != n:
        raise ValueError(f"signal length {len(signal)} != panel rows {n} for {trial['trial_id']}")
    eligible = (panel_fold["row_class"] == "RESEARCH_ELIGIBLE").to_numpy()
    months = panel_fold["universe_month"].to_numpy()
    symbols = panel_fold["symbol"].iloc[0] if "symbol" in panel_fold else None
    for decision in range(n):
        raw = float(signal.iloc[decision]) if np.isfinite(float(signal.iloc[decision])) else 0.0
        month_key = str(months[decision])
        symbol_key = str(panel_fold["symbol"].iloc[decision]) if "symbol" in panel_fold else "UNKNOWN"
        if raw == 0.0 or not eligible[decision] or decision < next_available:
            continue
        if (market, month_key, symbol_key) not in universe_top50:
            continue
        entry_index = decision + 1  # canonical next-open; no embargo latency
        exit_index = entry_index + int(trial["horizon_bars"])
        if exit_index >= n or not np.isfinite(opens[entry_index]) or opens[entry_index] <= 0:
            continue
        gross = direction_base * (opens[exit_index] / opens[entry_index] - 1)
        funding_cashflow = 0.0
        if market == "um":
            if symbol_key not in funding_cache:
                funding_cache[symbol_key] = _funding_events(symbol_key)
            events = funding_cache[symbol_key]
            if events is not None and len(events):
                crossed = events[(events.timestamp > stamps.iloc[entry_index]) & (events.timestamp <= stamps.iloc[exit_index])]
                funding_cashflow = -direction_base * float(crossed.funding_rate.sum())
        net = gross - fee_total - slip_total + funding_cashflow
        records.append({
            "trial_id": trial["trial_id"], "fold_id": trial.get("fold_id", ""),
            "market": market, "timeframe": timeframe, "side": side, "symbol": symbol_key,
            "universe_month": month_key,
            "decision_time": stamps.iloc[decision].isoformat(),
            "entry_time": stamps.iloc[entry_index].isoformat(),
            "exit_time": stamps.iloc[exit_index].isoformat(),
            "gross_return": gross, "net_return": net, "funding_cashflow": funding_cashflow,
        })
        next_available = exit_index  # non-overlap per symbol
    return pd.DataFrame.from_records(records)


def main() -> int:
    started = time.time()
    CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)
    registry = pd.read_csv(CAMPAIGN / "trial_registry.csv")
    folds = pd.read_csv(CAMPAIGN / "fold_registry.csv")
    registry_sha = _sha256_file(CAMPAIGN / "trial_registry.csv")
    freeze_sha = _git("rev-parse", "HEAD")
    manifest_path = CHECKPOINT_ROOT / "run_manifest.json"
    state = {}
    if manifest_path.exists():
        state = json.loads(manifest_path.read_text())
        if state.get("registry_sha256") != registry_sha:
            raise RuntimeError("checkpoint registry mismatch; refusing resume with changed settings")
    else:
        state = {"registry_sha256": registry_sha, "freeze_commit": freeze_sha, "completed_units": [], "failed_units": []}
        manifest_path.write_text(json.dumps(state, indent=2))
    completed = set(state.get("completed_units", []))
    print(f"R2A.2 frozen sha256={registry_sha[:16]} commit={freeze_sha[:12]} done={len(completed)}/{len(registry)*len(folds)}", flush=True)
    panels = {}
    universes = {m: _load_universe_top50(m) for m in MARKETS}
    total_units = len(registry) * len(folds)
    done_count = 0
    for _, trial_row in registry.iterrows():
        for _, fold_row in folds.iterrows():
            unit = f"{trial_row.trial_id}|{fold_row.fold_id}"
            if unit in completed:
                done_count += 1
                continue
            key = (trial_row.market, trial_row.timeframe)
            try:
                if key not in panels:
                    print(f"loading panel {key}", flush=True)
                    panels[key] = load_panel_pre_holdout(DATA_ROOT, trial_row.market, trial_row.timeframe, columns=None)
                panel = panels[key]
                trial = trial_row.to_dict() | {"fold_id": fold_row.fold_id}
                train, validation_panel = split_for_fold(
                    panel.assign(timestamp=pd.to_datetime(panel.timestamp, utc=True)),
                    timeframe=trial_row.timeframe,
                    horizon_bars=int(trial_row.horizon_bars),
                    fold_id=fold_row.fold_id,
                )
                # Training is loaded but NOT used for signals here (signals are
                # purely trailing formulas); the split exists to guarantee that
                # no validation execution window overlaps training labels.
                trades = execute_trial_fold(trial, validation_panel, universes[trial_row.market], {})
                out = CHECKPOINT_ROOT / f"{trial_row.trial_id}_{fold_row.fold_id}_trades.parquet"
                trades.to_parquet(out, index=False)
                state["completed_units"].append(unit)
            except Exception as exc:
                state.setdefault("failed_units", []).append({"unit": unit, "error": repr(exc)})
                print(f"{unit} FAILED {exc!r}", flush=True)
            manifest_path.write_text(json.dumps(state, indent=2))
            done_count += 1
            if done_count % 250 == 0:
                print(f"progress {done_count}/{total_units}", flush=True)
    print(f"done elapsed={time.time()-started:.0f}s completed={len(set(state['completed_units']))}/{total_units} failed={len(state.get('failed_units', []))}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
