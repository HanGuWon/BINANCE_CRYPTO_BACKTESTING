"""Aggregate sealed, pre-holdout R2A.2 checkpoints reproducibly."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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
BOOTSTRAP_SAMPLES = 1000
MINIMUM_TRADES_PER_FOLD = 30
EXPECTED_OUTCOME_IMPLEMENTATION_SHA = "99a37ae161d3791fb9a5d040f7cb9772492a5ed4"
EXPECTED_OUTCOME_REGISTRY_SHA256 = "d80fa57832714d7073d1a769c1422eb384b798ed1a929632a58d1948e3b83f3d"
EXPECTED_OUTCOME_SOURCE_TREE_SHA256 = "07572aaae5b70f05958fe36c223b2569439547b2cf99efabc3001038cb4f2777"
REQUIRED_TRADE_FIELDS = {"decision_time", "symbol", "side", "signal_value", "entry_time", "exit_time", "gross_return", "funding_cashflow", "net_return"}
CANONICAL_CHECKPOINT_ROOT = Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a2/checkpoints_v10").resolve()
SCIENTIFIC_SOURCE_PATHS = ("scripts", "src", "tests", "configs", "campaigns/r2a2_temporal_horizon_v1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def aggregate_artifact_hashes(directory: Path, names: list[str]) -> dict[str, str]:
    """Hash a fixed artifact list in stable order for repeatability proofs."""
    return {name: sha256(directory / name) for name in sorted(names)}


def aggregation_source_state() -> tuple[str, bool]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1", "--untracked-files=all", "--", *SCIENTIFIC_SOURCE_PATHS], cwd=ROOT, text=True).strip()
    return commit, bool(status)


def p_value(t: float, n: int) -> float:
    return float(2 * sps.t.sf(abs(t), max(n - 1, 1))) if np.isfinite(t) and n > 1 else np.nan


def aggregate_series(trades: pd.DataFrame) -> pd.Series:
    """Equal-weight active signals at each decision timestamp."""
    if trades.empty:
        return pd.Series(dtype=float)
    return trades.assign(_decision_time=pd.to_datetime(trades["decision_time"], utc=True)).groupby("_decision_time", sort=True)["net_return"].mean().astype(float)


def calendar_block_bootstrap(series_or_trades: pd.Series | pd.DataFrame, *, samples: int = BOOTSTRAP_SAMPLES, seed: int = SEED) -> np.ndarray:
    """Bootstrap calendar-month blocks while preserving all symbols together."""
    if isinstance(series_or_trades, pd.DataFrame):
        series = aggregate_series(series_or_trades)
    else:
        series = series_or_trades.copy().astype(float)
        if len(series):
            series.index = pd.to_datetime(series.index, utc=True)
    if series.empty:
        return np.full(int(samples), np.nan)
    labels = pd.Index(series.index.strftime("%Y-%m"))
    blocks = sorted(labels.unique())
    values = [series.to_numpy(float)[labels == block] for block in blocks]
    rng = np.random.default_rng(seed)
    estimates = np.full(int(samples), np.nan)
    for draw in range(int(samples)):
        chosen = rng.integers(0, len(values), size=len(values))
        pooled = np.concatenate([values[index] for index in chosen])
        estimates[draw] = float(np.mean(pooled)) if len(pooled) else np.nan
    return estimates


def calendar_block_bootstrap_ci(series_or_trades: pd.Series | pd.DataFrame, *, samples: int = BOOTSTRAP_SAMPLES, seed: int = SEED) -> tuple[float, float]:
    draws = calendar_block_bootstrap(series_or_trades, samples=samples, seed=seed)
    return (float(np.nanquantile(draws, .025)), float(np.nanquantile(draws, .975))) if np.isfinite(draws).any() else (np.nan, np.nan)


def stats_row(trades: pd.DataFrame) -> dict[str, float]:
    series = aggregate_series(trades)
    net = trades["net_return"].astype(float) if not trades.empty else pd.Series(dtype=float)
    t = float(_hac_t_stat(series)) if len(series) > 1 else np.nan
    return {"trades": int(len(trades)), "symbols_traded": int(trades["symbol"].nunique()) if not trades.empty else 0, "aggregate_observations": int(len(series)), "aggregate_mean_net_return": float(series.mean()) if len(series) else np.nan, "aggregate_sum_net_return": float(series.sum()) if len(series) else np.nan, "mean_net_return": float(net.mean()) if len(net) else np.nan, "median_net_return": float(net.median()) if len(net) else np.nan, "aggregate_hac_t": t, "p_value": p_value(t, len(series)), "gross_return": float((1 + trades["gross_return"].astype(float)).prod() - 1) if not trades.empty else np.nan, "net_return": float((1 + net).prod() - 1) if len(net) else np.nan, "funding_cashflow": float(trades["funding_cashflow"].astype(float).sum()) if not trades.empty else 0.0}


def bh(p: pd.Series) -> pd.Series:
    """Benjamini-Hochberg q-values over the full frozen registry family."""
    vals = p.to_numpy(float)
    order = np.argsort(np.where(np.isfinite(vals), vals, 2.0), kind="stable")
    out = np.full(len(vals), np.nan)
    running = 1.0
    for rank in range(len(vals) - 1, -1, -1):
        index = order[rank]
        if np.isfinite(vals[index]):
            running = min(running, vals[index] * len(vals) / (rank + 1))
            out[index] = min(running, 1.0)
    return pd.Series(out, index=p.index)


def evaluate_temporal_replication(row: object) -> str:
    """Apply all frozen criteria and fail closed when evidence is missing."""
    valid = int(getattr(row, "valid_fold_count"))
    if valid < 4:
        return "INSUFFICIENT_FOLDS"
    fields = ("positive_fold_fraction", "fdr_q_value", "aggregate_hac_t", "max_top_symbol_share_abs", "worst_fold_aggregate_mean", "best_fold_aggregate_mean")
    values = {name: float(getattr(row, name)) for name in fields}
    if not all(np.isfinite(value) for value in values.values()):
        return "INSUFFICIENT_EVIDENCE"
    catastrophic = values["worst_fold_aggregate_mean"] < -2.0 * values["best_fold_aggregate_mean"]
    checks = (values["positive_fold_fraction"] >= .75, values["fdr_q_value"] <= .05, abs(values["aggregate_hac_t"]) >= 3.0, values["max_top_symbol_share_abs"] <= .5, not catastrophic)
    return "TEMPORAL_REPLICATION" if all(checks) else "NO_REPLICATION"


def aggregate_symbol_concentration(trades: pd.DataFrame) -> dict[str, object]:
    """Return aggregate valid-fold concentration used by the frozen gate."""
    if trades.empty:
        return {"symbols_traded": 0, "top_symbol": "", "top_symbol_share_abs": np.nan}
    contribution = trades.groupby("symbol")["net_return"].sum().astype(float)
    total_abs = float(contribution.abs().sum())
    if not total_abs:
        return {"symbols_traded": int(len(contribution)), "top_symbol": str(contribution.index[0]), "top_symbol_share_abs": np.nan}
    top = contribution.abs().idxmax()
    return {"symbols_traded": int(len(contribution)), "top_symbol": str(top), "top_symbol_share_abs": float(abs(contribution.loc[top]) / total_abs)}


def cohort_subset(trades: pd.DataFrame, market: str, cohort: str, cohort_map: dict[tuple[str, str, str, str], bool]) -> pd.DataFrame:
    if trades.empty:
        return trades
    mask = [cohort_map.get((market, str(month), str(symbol), cohort), False) for month, symbol in zip(trades.universe_month, trades.symbol)]
    return trades.loc[mask]


def add_cross_market_diagnostics(horizon: pd.DataFrame) -> pd.DataFrame:
    """Add deterministic Spot/UM, UM-side, and horizon-position diagnostics."""
    result = horizon.copy()
    result["horizon_decay_position"] = result.groupby(["feature_id", "variant", "market", "timeframe", "side"])["horizon_bars"].rank(method="dense", ascending=True).astype("Int64")
    consistency: list[str] = []
    asymmetry: list[float] = []
    for row in result.itertuples(index=False):
        peer = result[(result.feature_id == row.feature_id) & (result.variant == row.variant) & (result.timeframe == row.timeframe) & (result.horizon_bars == row.horizon_bars)]
        spot = peer[peer.market == "spot"].aggregate_mean_net_return
        um_long = peer[(peer.market == "um") & (peer.side == "LONG")].aggregate_mean_net_return
        um_short = peer[(peer.market == "um") & (peer.side == "SHORT")].aggregate_mean_net_return
        current = float(row.aggregate_mean_net_return)
        if row.market == "um" and len(spot) and np.isfinite(float(spot.iloc[0])) and np.isfinite(current):
            consistency.append("same_direction" if np.sign(float(spot.iloc[0])) == np.sign(current) else "opposite_direction")
        elif row.market == "spot" and len(um_long) and np.isfinite(float(um_long.iloc[0])) and np.isfinite(current):
            consistency.append("same_direction" if np.sign(float(um_long.iloc[0])) == np.sign(current) else "opposite_direction")
        else:
            consistency.append("not_comparable")
        asymmetry.append(float(um_long.iloc[0] - um_short.iloc[0]) if row.market == "um" and len(um_long) and len(um_short) and np.isfinite(float(um_long.iloc[0])) and np.isfinite(float(um_short.iloc[0])) else np.nan)
    result["spot_um_consistency_note"] = consistency
    result["um_long_short_mean_delta"] = asymmetry
    return result


def _as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "yes"}


def _assert_pre_holdout(trades: pd.DataFrame, timeframe: str, path: Path) -> None:
    if not REQUIRED_TRADE_FIELDS.issubset(trades.columns):
        raise RuntimeError(f"{path.name}: missing required trade fields")
    if trades.empty:
        return
    boundary = HOLDOUT_BOUNDARY_BY_TF[timeframe]
    for field in ("decision_time", "entry_time", "exit_time"):
        stamps = pd.to_datetime(trades[field], utc=True)
        if not bool((stamps < boundary).all()):
            raise RuntimeError(f"holdout contamination in {path.name} ({field})")


def checkpoint_path(root: Path, trial_id: str, fold_id: str) -> Path:
    path = (root / f"{trial_id}_{fold_id}_trades.parquet").resolve()
    if root.resolve() != CANONICAL_CHECKPOINT_ROOT or path.parent != CANONICAL_CHECKPOINT_ROOT or "final_holdout" in str(path).lower():
        raise RuntimeError(f"refusing non-canonical or holdout checkpoint path: {path}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a2/checkpoints_v10")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if root != CANONICAL_CHECKPOINT_ROOT:
        raise RuntimeError(f"refusing non-canonical/non-v10 checkpoint root: {root}")
    manifest_path = root / "run_manifest.json"
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    registry = pd.read_csv(CAMPAIGN / "trial_registry.csv")
    folds = pd.read_csv(CAMPAIGN / "fold_registry.csv")
    expected_units = {f"{t.trial_id}|{f.fold_id}" for t in registry.itertuples(index=False) for f in folds.itertuples(index=False)}
    completed = set(run_manifest.get("completed_units", []))
    if completed != expected_units or run_manifest.get("failed_units"):
        raise RuntimeError(f"sealed checkpoint required: completed={len(completed)}/{len(expected_units)} failed={len(run_manifest.get('failed_units', []))}")
    if run_manifest.get("implementation_sha") != EXPECTED_OUTCOME_IMPLEMENTATION_SHA or run_manifest.get("registry_sha256") != EXPECTED_OUTCOME_REGISTRY_SHA256 or run_manifest.get("source_tree_sha256") != EXPECTED_OUTCOME_SOURCE_TREE_SHA256 or run_manifest.get("source_dirty") is not False:
        raise RuntimeError("v10 outcome identity mismatch; refusing aggregation")
    if sha256(CAMPAIGN / "trial_registry.csv") != EXPECTED_OUTCOME_REGISTRY_SHA256:
        raise RuntimeError("current registry SHA differs from frozen outcome registry")
    aggregate_commit, aggregate_dirty = aggregation_source_state()
    if aggregate_dirty:
        raise RuntimeError("aggregation scientific source tree is dirty; commit before reading outcomes")
    universe = pd.read_csv(CAMPAIGN.parent / "r1_final_panel_v1" / "universe_monthly.csv")
    cohort_map = {(str(r.market), str(r.universe_month), str(r.symbol), cohort): _as_bool(getattr(r, "selected_" + cohort)) for r in universe.itertuples(index=False) for cohort in ("top20", "top50", "top100")}
    fold_rows: list[dict] = []
    horizon_rows: list[dict] = []
    bootstrap_rows: list[dict] = []
    cohort_rows: list[dict] = []
    yearly_rows: list[dict] = []
    concentration_rows: list[dict] = []
    trial_series: dict[str, list[pd.Series]] = {}
    trial_means: dict[str, list[float]] = {}
    trial_shares: dict[str, list[float]] = {}
    trial_symbol_net: dict[str, dict[str, float]] = {}
    for trial in registry.itertuples(index=False):
        trial_series[trial.trial_id], trial_means[trial.trial_id], trial_shares[trial.trial_id] = [], [], []
        trial_symbol_net[trial.trial_id] = {}
        for fold in folds.itertuples(index=False):
            path = checkpoint_path(root, str(trial.trial_id), str(fold.fold_id))
            if not path.exists():
                raise FileNotFoundError(path)
            trades = pd.read_parquet(path)
            _assert_pre_holdout(trades, str(trial.timeframe), path)
            series = aggregate_series(trades)
            valid = len(trades) >= MINIMUM_TRADES_PER_FOLD
            fold_rows.append({"trial_id": trial.trial_id, "fold_id": fold.fold_id, "feature_id": trial.feature_id, "variant": trial.variant, "market": trial.market, "timeframe": trial.timeframe, "side": trial.side, "horizon_bars": int(trial.horizon_bars), "valid_fold": bool(valid), **stats_row(trades)})
            if valid:
                trial_series[trial.trial_id].append(series)
                trial_means[trial.trial_id].append(float(series.mean()))
                for symbol, value in trades.groupby("symbol")["net_return"].sum().items():
                    trial_symbol_net[trial.trial_id][str(symbol)] = trial_symbol_net[trial.trial_id].get(str(symbol), 0.0) + float(value)
                years = pd.to_datetime(series.index, utc=True).year
                for year, values in series.groupby(years):
                    yearly_rows.append({"trial_id": trial.trial_id, "fold_id": fold.fold_id, "year": int(year), "aggregate_observations": int(len(values)), "mean_net_return": float(values.mean()), "hac_t": float(_hac_t_stat(values)) if len(values) > 1 else np.nan})
            fold_concentration = aggregate_symbol_concentration(trades)
            share = fold_concentration["top_symbol_share_abs"]
            trial_shares[trial.trial_id].append(share)
            concentration_rows.append({"trial_id": trial.trial_id, "fold_id": fold.fold_id, "scope": "fold_diagnostic", **fold_concentration})
            for cohort in ("top20", "top50", "top100"):
                if trades.empty:
                    subset = trades
                else:
                    subset = cohort_subset(trades, trial.market, cohort, cohort_map)
                cs = aggregate_series(subset)
                cs_mean = float(cs.mean()) if len(cs) else np.nan
                cs_std = float(cs.std(ddof=0)) if len(cs) else np.nan
                cohort_rows.append({"trial_id": trial.trial_id, "fold_id": fold.fold_id, "cohort": cohort, "trades": int(len(subset)), "aggregate_observations": int(len(cs)), "mean_net_return": cs_mean, "sharpe": float(cs_mean / cs_std) if np.isfinite(cs_std) and cs_std > 0 else np.nan, "hac_t": float(_hac_t_stat(cs)) if len(cs) > 1 else np.nan})
    for trial in registry.itertuples(index=False):
        parts = trial_series[trial.trial_id]
        combined = pd.concat(parts).sort_index() if parts else pd.Series(dtype=float)
        means = np.asarray(trial_means[trial.trial_id], dtype=float)
        lo, hi = calendar_block_bootstrap_ci(combined)
        shares = trial_shares[trial.trial_id]
        symbol_net = pd.Series(trial_symbol_net[trial.trial_id], dtype=float)
        aggregate_concentration = aggregate_symbol_concentration(pd.DataFrame({"symbol": symbol_net.index, "net_return": symbol_net.to_numpy()}))
        max_share = aggregate_concentration["top_symbol_share_abs"]
        concentration_rows.append({"trial_id": trial.trial_id, "fold_id": "ALL_VALID", "scope": "aggregate_valid_gate", **aggregate_concentration})
        t = float(_hac_t_stat(combined)) if len(combined) > 1 else np.nan
        horizon_rows.append({"trial_id": trial.trial_id, "feature_id": trial.feature_id, "variant": trial.variant, "market": trial.market, "timeframe": trial.timeframe, "side": trial.side, "horizon_bars": int(trial.horizon_bars), "valid_fold_count": int(len(means)), "positive_fold_fraction": float(np.mean(means > 0)) if len(means) else np.nan, "aggregate_observations": int(len(combined)), "aggregate_mean_net_return": float(combined.mean()) if len(combined) else np.nan, "aggregate_sum_net_return": float(combined.sum()) if len(combined) else np.nan, "aggregate_hac_t": t, "p_value": p_value(t, len(combined)), "bootstrap_ci_low": lo, "bootstrap_ci_high": hi, "best_fold_aggregate_mean": float(np.max(means)) if len(means) else np.nan, "worst_fold_aggregate_mean": float(np.min(means)) if len(means) else np.nan, "max_top_symbol_share_abs": max_share})
        bootstrap_rows.append({"trial_id": trial.trial_id, "seed": SEED, "blocks": "calendar_month", "preserve": "all symbols together", "samples": BOOTSTRAP_SAMPLES, "ci95_low": lo, "ci95_high": hi})
    horizon = pd.DataFrame(horizon_rows)
    horizon["fdr_q_value"] = bh(horizon["p_value"])
    horizon["bonferroni_p"] = np.minimum(horizon["p_value"] * len(horizon), 1.0)
    horizon["catastrophic_reversal"] = horizon.apply(lambda row: bool(np.isfinite(row.worst_fold_aggregate_mean) and np.isfinite(row.best_fold_aggregate_mean) and row.worst_fold_aggregate_mean < -2.0 * row.best_fold_aggregate_mean), axis=1)
    horizon["temporal_replication"] = [evaluate_temporal_replication(row) for row in horizon.itertuples(index=False)]
    horizon = add_cross_market_diagnostics(horizon)
    multiple = horizon[["trial_id", "feature_id", "variant", "market", "timeframe", "side", "horizon_bars", "aggregate_hac_t", "p_value", "fdr_q_value", "bonferroni_p"]].copy()
    out = CAMPAIGN
    pd.DataFrame(fold_rows).to_csv(out / "fold_results.csv", index=False)
    horizon.to_csv(out / "horizon_results.csv", index=False)
    horizon[["trial_id", "feature_id", "variant", "market", "timeframe", "side", "horizon_bars", "valid_fold_count", "positive_fold_fraction", "aggregate_hac_t", "fdr_q_value", "max_top_symbol_share_abs", "catastrophic_reversal", "temporal_replication"]].to_csv(out / "temporal_replication.csv", index=False)
    multiple.to_csv(out / "multiple_testing.csv", index=False)
    pd.DataFrame(bootstrap_rows).to_csv(out / "bootstrap_results.csv", index=False)
    pd.DataFrame(cohort_rows).to_csv(out / "cohort_diagnostics.csv", index=False)
    pd.DataFrame(yearly_rows).to_csv(out / "yearly_diagnostics.csv", index=False)
    pd.DataFrame(concentration_rows).to_csv(out / "symbol_concentration.csv", index=False)
    pd.DataFrame({"trial_id": registry.trial_id, "mfe": np.nan, "mae": np.nan, "time_to_mfe": np.nan, "time_to_mae": np.nan, "reason": "checkpoint schema has no intratrade path; diagnostic only; not silently inferred"}).to_csv(out / "mfe_mae_diagnostics.csv", index=False)
    shortlist_cols = ["trial_id", "feature_id", "variant", "market", "timeframe", "side", "horizon_bars", "valid_fold_count", "positive_fold_fraction", "aggregate_hac_t", "fdr_q_value", "max_top_symbol_share_abs", "catastrophic_reversal", "temporal_replication"]
    horizon.loc[horizon.temporal_replication == "TEMPORAL_REPLICATION", shortlist_cols].to_csv(out / "candidate_shortlist.csv", index=False)
    proof = {"checkpoint_root": str(root), "holdout_boundaries": {key: value.isoformat() for key, value in HOLDOUT_BOUNDARY_BY_TF.items()}, "checked_files": int(len(fold_rows)), "status": "PASS", "method": "decision_time, entry_time, and exit_time asserted strictly before each timeframe boundary; no holdout path opened", "final_holdout_status": "UNTOUCHED"}
    (out / "holdout_guard_proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    aggregate_manifest = {"checkpoint_root": str(root), "outcome_manifest_sha256": sha256(manifest_path), "outcome_implementation_sha": run_manifest.get("implementation_sha"), "outcome_registry_sha256": run_manifest.get("registry_sha256"), "outcome_source_tree_sha256": run_manifest.get("source_tree_sha256"), "outcome_source_dirty": run_manifest.get("source_dirty"), "registry_sha256": sha256(CAMPAIGN / "trial_registry.csv"), "units": int(len(fold_rows)), "expected_units": int(len(expected_units)), "failed_units": 0, "aggregate_implementation_sha": aggregate_commit, "aggregate_source_dirty": aggregate_dirty, "aggregate_script_sha256": sha256(Path(__file__))}
    artifact_names = ["fold_results.csv", "horizon_results.csv", "temporal_replication.csv", "multiple_testing.csv", "bootstrap_results.csv", "cohort_diagnostics.csv", "yearly_diagnostics.csv", "symbol_concentration.csv", "mfe_mae_diagnostics.csv", "candidate_shortlist.csv", "holdout_guard_proof.json"]
    aggregate_manifest["artifact_sha256"] = aggregate_artifact_hashes(out, artifact_names)
    (out / "aggregate_manifest.json").write_text(json.dumps(aggregate_manifest, indent=2), encoding="utf-8")
    print(json.dumps({"units": len(fold_rows), "trials": len(horizon), "fdr_survivors": int((horizon.fdr_q_value <= .05).sum()), "replications": int((horizon.temporal_replication == "TEMPORAL_REPLICATION").sum()), "bootstrap_samples": BOOTSTRAP_SAMPLES, "bootstrap_blocks": "calendar_month"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
