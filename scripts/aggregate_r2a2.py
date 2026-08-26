"""Aggregate corrected R2A.2 pre-holdout checkpoints into reproducible evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from r2a_engine import HOLDOUT_BOUNDARY_BY_TF, _hac_t_stat  # noqa: E402

CAMPAIGN = ROOT / "campaigns" / "r2a2_temporal_horizon_v1"
SEED = 1729


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def p_value(t: float, n: int) -> float:
    return float(2 * sps.t.sf(abs(t), max(n - 1, 1))) if np.isfinite(t) and n > 1 else np.nan


def aggregate_series(trades: pd.DataFrame) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    return trades.groupby("decision_time", sort=True)["net_return"].mean().astype(float)


def stats_row(trades: pd.DataFrame) -> dict[str, float]:
    series = aggregate_series(trades)
    net = trades["net_return"].astype(float) if not trades.empty else pd.Series(dtype=float)
    t = float(_hac_t_stat(series)) if len(series) > 1 else np.nan
    return {
        "trades": int(len(trades)), "symbols_traded": int(trades["symbol"].nunique()) if not trades.empty else 0,
        "aggregate_observations": int(len(series)),
        "aggregate_mean_net_return": float(series.mean()) if len(series) else np.nan,
        "mean_net_return": float(net.mean()) if len(net) else np.nan,
        "median_net_return": float(net.median()) if len(net) else np.nan,
        "aggregate_hac_t": t, "p_value": p_value(t, len(series)),
        "gross_return": float((1 + trades["gross_return"].astype(float)).prod() - 1) if not trades.empty else np.nan,
        "net_return": float((1 + net).prod() - 1) if len(net) else np.nan,
        "funding_cashflow": float(trades["funding_cashflow"].astype(float).sum()) if not trades.empty else 0.0,
    }


def bh(p: pd.Series) -> pd.Series:
    vals = p.to_numpy(float)
    order = np.argsort(np.where(np.isfinite(vals), vals, 2.0))
    out = np.full(len(vals), np.nan)
    running = 1.0
    for rank in range(len(vals) - 1, -1, -1):
        i = order[rank]
        if np.isfinite(vals[i]):
            running = min(running, vals[i] * len(vals) / (rank + 1))
            out[i] = min(running, 1.0)
    return pd.Series(out, index=p.index)


def bootstrap_fold_ci(fold_means: list[float]) -> tuple[float, float]:
    if len(fold_means) < 2:
        return np.nan, np.nan
    rng = np.random.default_rng(SEED)
    x = np.asarray(fold_means, float)
    draws = rng.choice(x, size=(2000, len(x)), replace=True).mean(axis=1)
    return float(np.quantile(draws, .025)), float(np.quantile(draws, .975))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a2/checkpoints_v9")
    args = ap.parse_args()
    root = Path(args.root)
    registry = pd.read_csv(CAMPAIGN / "trial_registry.csv")
    folds = pd.read_csv(CAMPAIGN / "fold_registry.csv")
    fold_rows: list[dict] = []
    trial_series: dict[str, list[pd.Series]] = {}
    trial_fold_means: dict[str, list[float]] = {}
    yearly_rows: list[dict] = []
    concentration_rows: list[dict] = []
    cohort_rows: list[dict] = []
    universe = pd.read_csv(CAMPAIGN.parent / "r1_final_panel_v1" / "universe_monthly.csv")
    def as_bool(value: object) -> bool:
        return str(value).strip().lower() in {"1", "true", "t", "yes"}
    # Build the cohort map without relying on pandas boolean-string coercion.
    cohort_map = {(str(r.market), str(r.universe_month), str(r.symbol), cohort): as_bool(getattr(r, "selected_" + cohort))
                  for r in universe.itertuples(index=False) for cohort in ("top20", "top50", "top100")}
    for trial in registry.itertuples(index=False):
        trial_series[trial.trial_id] = []
        trial_fold_means[trial.trial_id] = []
        for fold in folds.itertuples(index=False):
            path = root / f"{trial.trial_id}_{fold.fold_id}_trades.parquet"
            if not path.exists():
                raise FileNotFoundError(path)
            trades = pd.read_parquet(path)
            if not trades.empty:
                stamps = pd.to_datetime(trades["decision_time"], utc=True)
                boundary = HOLDOUT_BOUNDARY_BY_TF[trial.timeframe]
                if not bool((stamps < boundary).all()):
                    raise RuntimeError(f"holdout contamination in {path.name}")
            s = aggregate_series(trades)
            trial_series[trial.trial_id].append(s)
            row = {"trial_id": trial.trial_id, "fold_id": fold.fold_id, "feature_id": trial.feature_id, "variant": trial.variant, "market": trial.market, "timeframe": trial.timeframe, "side": trial.side, "horizon_bars": int(trial.horizon_bars), **stats_row(trades)}
            fold_rows.append(row)
            if len(s):
                trial_fold_means[trial.trial_id].append(float(s.mean()))
                years = pd.to_datetime(s.index, utc=True).year
                for year, vals in s.groupby(years):
                    yearly_rows.append({"trial_id": trial.trial_id, "fold_id": fold.fold_id, "year": int(year), "aggregate_observations": len(vals), "mean_net_return": float(vals.mean()), "hac_t": float(_hac_t_stat(vals)) if len(vals) > 1 else np.nan})
            if not trades.empty:
                contrib = trades.groupby("symbol")["net_return"].sum().sort_values(ascending=False)
                total = float(contrib.abs().sum())
                concentration_rows.append({"trial_id": trial.trial_id, "fold_id": fold.fold_id, "symbols_traded": len(contrib), "top_symbol": str(contrib.index[0]), "top_symbol_share_abs": float(abs(contrib.iloc[0]) / total) if total else np.nan})
            for cohort in ("top20", "top50", "top100"):
                if trades.empty:
                    subset = trades
                else:
                    mask = [cohort_map.get((trial.market, str(mon), str(sym), cohort), False) for mon, sym in zip(trades.universe_month, trades.symbol)]
                    subset = trades.loc[mask]
                cs = aggregate_series(subset)
                cohort_rows.append({"trial_id": trial.trial_id, "fold_id": fold.fold_id, "cohort": cohort, "trades": len(subset), "aggregate_observations": len(cs), "mean_net_return": float(cs.mean()) if len(cs) else np.nan, "hac_t": float(_hac_t_stat(cs)) if len(cs) > 1 else np.nan})

    fold_df = pd.DataFrame(fold_rows)
    horizon_rows = []
    for trial in registry.itertuples(index=False):
        ss = [s for s in trial_series[trial.trial_id] if len(s)]
        combined = pd.concat(ss).sort_index() if ss else pd.Series(dtype=float)
        t = float(_hac_t_stat(combined)) if len(combined) > 1 else np.nan
        means = trial_fold_means[trial.trial_id]
        lo, hi = bootstrap_fold_ci(means)
        horizon_rows.append({"trial_id": trial.trial_id, "feature_id": trial.feature_id, "variant": trial.variant, "market": trial.market, "timeframe": trial.timeframe, "side": trial.side, "horizon_bars": int(trial.horizon_bars), "valid_fold_count": len(means), "positive_fold_fraction": float(np.mean(np.asarray(means) > 0)) if means else np.nan, "aggregate_observations": len(combined), "aggregate_mean_net_return": float(combined.mean()) if len(combined) else np.nan, "aggregate_hac_t": t, "p_value": p_value(t, len(combined)), "bootstrap_ci_low": lo, "bootstrap_ci_high": hi})
    horizon = pd.DataFrame(horizon_rows)
    horizon["fdr_q_value"] = bh(horizon["p_value"])
    horizon["bonferroni_p"] = np.minimum(horizon["p_value"] * len(horizon), 1.0)
    horizon["temporal_replication"] = np.select([(horizon.valid_fold_count >= 4) & (horizon.positive_fold_fraction >= .75) & (horizon.fdr_q_value <= .05) & (horizon.aggregate_hac_t.abs() >= 3), horizon.valid_fold_count >= 2], ["TEMPORAL_REPLICATION", "NO_REPLICATION"], default="INSUFFICIENT_FOLDS")
    multiple = horizon[["trial_id", "feature_id", "variant", "market", "timeframe", "side", "horizon_bars", "aggregate_hac_t", "p_value", "fdr_q_value", "bonferroni_p"]].copy()
    out = CAMPAIGN
    fold_df.to_csv(out / "fold_results.csv", index=False)
    horizon.to_csv(out / "horizon_results.csv", index=False)
    horizon[["trial_id", "feature_id", "variant", "market", "timeframe", "side", "valid_fold_count", "positive_fold_fraction", "aggregate_hac_t", "fdr_q_value", "temporal_replication"]].to_csv(out / "temporal_replication.csv", index=False)
    multiple.to_csv(out / "multiple_testing.csv", index=False)
    pd.DataFrame([{**r, "seed": SEED, "blocks": "fold", "samples": 2000} for r in [{"trial_id": t.trial_id, "ci95_low": horizon.loc[horizon.trial_id == t.trial_id, "bootstrap_ci_low"].iloc[0], "ci95_high": horizon.loc[horizon.trial_id == t.trial_id, "bootstrap_ci_high"].iloc[0]} for t in registry.itertuples(index=False)]]).to_csv(out / "bootstrap_results.csv", index=False)
    pd.DataFrame(cohort_rows).to_csv(out / "cohort_diagnostics.csv", index=False)
    pd.DataFrame(yearly_rows).to_csv(out / "yearly_diagnostics.csv", index=False)
    pd.DataFrame(concentration_rows).to_csv(out / "symbol_concentration.csv", index=False)
    mfe = pd.DataFrame({"trial_id": registry.trial_id, "mfe": np.nan, "mae": np.nan, "time_to_mfe": np.nan, "time_to_mae": np.nan, "reason": "checkpoint schema has no intratrade path; not silently inferred"})
    mfe.to_csv(out / "mfe_mae_diagnostics.csv", index=False)
    proof = {"checkpoint_root": str(root), "holdout_boundaries": {k: v.isoformat() for k, v in HOLDOUT_BOUNDARY_BY_TF.items()}, "checked_files": int(len(fold_df)), "status": "PASS", "method": "all decision_time values asserted strictly before timeframe boundary"}
    (out / "holdout_guard_proof.json").write_text(json.dumps(proof, indent=2))
    expected_units = int(len(registry) * len(folds))
    manifest = {"checkpoint_root": str(root), "registry_sha256": sha256(CAMPAIGN / "trial_registry.csv"), "units": int(len(fold_df)), "expected_units": expected_units, "failed_units": int(max(expected_units - len(fold_df), 0)), "aggregate_script": sha256(Path(__file__))}
    (out / "aggregate_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"units": len(fold_df), "trials": len(horizon), "fdr_survivors": int((horizon.fdr_q_value <= .05).sum()), "replications": int((horizon.temporal_replication == "TEMPORAL_REPLICATION").sum())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
