"""Deterministic post-run R2B aggregation (no holdout access)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from r2b_historical_runner import _launch_identity, load_registry


def hac_t(values: pd.Series) -> float:
    x = pd.to_numeric(values, errors="coerce").dropna().to_numpy(float)
    n = len(x)
    if n < 3:
        return float("nan")
    lags = int(math.floor(4 * (n / 100) ** (2 / 9)))
    centered = x - x.mean()
    gamma = [float(np.dot(centered[k:], centered[: n - k])) / n for k in range(lags + 1)]
    variance = gamma[0] + 2 * sum((1 - k / (lags + 1)) * gamma[k] for k in range(1, lags + 1))
    return float(x.mean() / math.sqrt(variance / n)) if variance > 0 else float("nan")


def month_bootstrap(values: pd.DataFrame, samples: int = 1000, seed: int = 1729) -> tuple[float, float]:
    if values.empty:
        return (float("nan"), float("nan"))
    monthly = values.groupby("month", sort=True).net_return.mean()
    if len(monthly) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    draws = rng.choice(monthly.to_numpy(float), size=(samples, len(monthly)), replace=True).mean(axis=1)
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def benjamini_hochberg(pvalues: list[float], q: float = 0.05) -> list[float]:
    n = len(pvalues)
    order = np.argsort(np.nan_to_num(pvalues, nan=1.0))
    adjusted = np.full(n, np.nan)
    running = 1.0
    for rank, index in reversed(list(enumerate(order, start=1))):
        p = pvalues[index]
        if not np.isfinite(p):
            continue
        running = min(running, p * n / rank)
        adjusted[index] = running
    return adjusted.tolist()


def aggregate(root: Path) -> dict[str, object]:
    manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("unit_count") != 576 or manifest.get("final_holdout_status") != "UNTOUCHED":
        raise RuntimeError("aggregation requires a sealed 576-unit pre-holdout manifest")
    trials, folds = load_registry()
    fold_ids = sorted(set(str(row["fold_id"]) for row in folds))
    by_trial: dict[str, list[dict[str, object]]] = {}
    for trial in trials:
        trial_id = str(trial["trial_id"])
        fold_stats = []
        all_trades = []
        for fold_id in fold_ids:
            unit = next(item for item in manifest["units"] if item["trial_id"] == trial_id and item["fold_id"] == fold_id)
            trades = pd.read_parquet(root / "trades" / f"{unit['unit_id']}.parquet")
            if len(trades):
                trades["month"] = pd.to_datetime(trades["decision_time"], utc=True).dt.strftime("%Y-%m")
                all_trades.append(trades[["decision_time", "net_return", "month"]])
            fold_stats.append({"fold_id": fold_id, "status": unit["status"], "executed_trades": int(unit["executed_trades"]), "mean_net_return": float(trades.net_return.mean()) if len(trades) else float("nan"), "hac_t_stat": hac_t(trades.net_return) if len(trades) else float("nan")})
        combined = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame(columns=["decision_time", "net_return", "month"])
        # Decision-time portfolio: equal weight simultaneous active signals.
        portfolio = combined.groupby("decision_time", sort=True).net_return.mean().reset_index() if len(combined) else combined
        t = hac_t(portfolio.net_return) if len(portfolio) else float("nan")
        p = float(math.erfc(abs(t) / math.sqrt(2))) if np.isfinite(t) else float("nan")
        low, high = month_bootstrap(combined)
        by_trial[trial_id] = [{"trial_id": trial_id, "feature_id": trial["feature_id"], "signal_variant": trial["signal_variant"], "timeframe": trial["timeframe"], "side": trial["side"], "horizon_bars": int(trial["horizon_bars"]), "valid_folds": int(sum(s["status"] == "VALID" for s in fold_stats)), "folds": fold_stats, "aggregate_mean_net_return": float(portfolio.net_return.mean()) if len(portfolio) else float("nan"), "aggregate_hac_t_stat": t, "aggregate_p_value": p, "bootstrap_ci_low": low, "bootstrap_ci_high": high}]
    rows = [item[0] for item in by_trial.values()]
    adjusted = benjamini_hochberg([float(row["aggregate_p_value"]) for row in rows])
    for row, value in zip(rows, adjusted):
        row["bh_fdr_q"] = value
        row["bh_significant_q05"] = bool(np.isfinite(value) and value <= 0.05)
    rows.sort(key=lambda row: row["trial_id"])
    return {"status": "PASS", "campaign_id": "r2b_restricted_derivatives_v1", "unit_count": 576, "bootstrap_samples": 1000, "bootstrap_seed": 1729, "bh_q": 0.05, "family_size": 72, "implementation_commit": manifest["implementation_commit"], "source_tree_sha256": manifest["source_tree_sha256"], "final_holdout_status": "UNTOUCHED", "trials": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "family_size": result["family_size"], "unit_count": result["unit_count"], "final_holdout_status": result["final_holdout_status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
