"""R2A campaign runner: checkpointed, holdout-guarded, preregistration-locked.

Executes exactly the frozen trial registry over train+validation partitions.
Checkpoints live on the D: data drive; resumed runs never recompute completed
trials with different settings (registry SHA is pinned in the manifest).
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
    HOLDOUT_BOUNDARY_BY_TF,
    SPLIT_FIRST_VALIDATION,
    SPLIT_LAST_TRAIN,
    SPLIT_LAST_VALIDATION,
    assert_no_holdout,
    evaluate_trial,
    load_panel_pre_holdout,
    run_single_trial,
)
from verify_r2a_registry import HORIZON_BARS_24H  # noqa: E402

CAMPAIGN = ROOT / "campaigns" / "r2a_standalone_evidence_v1"
DATA_ROOT = Path("data/processed/r1_gap_safe_cohort")
CHECKPOINT_ROOT = Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a/checkpoints")
MARKETS = ("spot", "um")
TIMEFRAMES = ("15m", "1h", "4h")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _load_universe_top50(market: str) -> set[tuple[str, str, str]]:
    universe = pd.read_csv(CAMPAIGN.parent / "r1_final_panel_v1" / "universe_monthly.csv", usecols=["market", "universe_month", "symbol", "selected_top50"])
    selected = universe[(universe.market == market) & universe.selected_top50.astype(bool)]
    return {(row.market, str(row.universe_month), row.symbol) for row in selected.itertuples(index=False)}


def _split_partitions(frame: pd.DataFrame, timeframe: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    stamps = frame["timestamp"]
    train = frame[stamps < SPLIT_FIRST_VALIDATION[timeframe]].copy()
    validation = frame[
        (stamps >= SPLIT_FIRST_VALIDATION[timeframe]) & (stamps <= SPLIT_LAST_VALIDATION[timeframe])
    ].copy()
    return train, validation


def main() -> int:
    started = time.time()
    CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)
    registry_path = CAMPAIGN / "trial_registry.csv"
    registry = pd.read_csv(registry_path)
    registry_sha = _sha256_file(registry_path)
    freeze_sha = _git_sha("rev-parse", "HEAD")
    manifest_path = CHECKPOINT_ROOT / "run_manifest.json"
    state: dict = {}
    if manifest_path.exists():
        state = json.loads(manifest_path.read_text())
        if state.get("registry_sha256") != registry_sha:
            raise RuntimeError("checkpoint registry mismatch; refusing resume with changed settings")
    else:
        state = {"registry_sha256": registry_sha, "freeze_commit": freeze_sha, "completed": [], "failed": []}
        manifest_path.write_text(json.dumps(state, indent=2))
    completed = set(state.get("completed", []))
    print(f"frozen registry sha256={registry_sha[:16]} commit={freeze_sha[:12]} completed={len(completed)}/{len(registry)}", flush=True)
    panels: dict[tuple[str, str], pd.DataFrame] = {}
    universes = {market: _load_universe_top50(market) for market in MARKETS}
    results: list[pd.DataFrame] = []
    for _, trial in registry.iterrows():
        trial_id = trial.trial_id
        if trial_id in completed:
            continue
        key = (trial.market, trial.timeframe)
        if key not in panels:
            print(f"loading panel {key}", flush=True)
            panel = load_panel_pre_holdout(DATA_ROOT, trial.market, trial.timeframe, columns=None)
            assert_no_holdout(panel, timeframe=trial.timeframe, context=f"panel {key}")
            panels[key] = panel
        panel = panels[key]
        try:
            evidence, trades = run_single_trial(trial.to_dict(), panel, universe_top50=universes[trial.market])
            record = {"trial_id": trial_id, **trial.to_dict(), **evidence}
            results.append(pd.DataFrame([record]))
            trades_out = CHECKPOINT_ROOT / f"{trial_id}_trades.parquet"
            trades.to_parquet(trades_out, index=False)
            state["completed"].append(trial_id)
        except Exception as exc:  # checkpoint the failure and continue; report at end
            state.setdefault("failed", []).append({"trial_id": trial_id, "error": repr(exc)})
            print(f"{trial_id} FAILED {exc!r}", flush=True)
        manifest_path.write_text(json.dumps(state, indent=2))
        if len(state["completed"]) % 25 == 0:
            print(f"progress {len(state['completed'])}/{len(registry)}", flush=True)
    if results:
        combined = pd.concat(results, ignore_index=True)
        out = CAMPAIGN / "trial_results_partial.csv"
        existing = pd.read_csv(out) if out.exists() else None
        merged = pd.concat([existing, combined], ignore_index=True).drop_duplicates("trial_id", keep="last") if existing is not None else combined
        merged.sort_values("trial_id").to_csv(out, index=False)
    elapsed = time.time() - started
    print(f"done elapsed={elapsed:.0f}s completed={len(set(state['completed']))} failed={len(state.get('failed', []))}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
