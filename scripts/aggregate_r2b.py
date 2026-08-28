"""Contract-conforming deterministic aggregation for corrected R2B checkpoints."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

from r2b_historical_runner import REQUIRED_TRADE_FIELDS, load_registry

ROOT = Path(__file__).resolve().parents[1]
SEED = 1729
BOOTSTRAP_SAMPLES = 1000
MINIMUM_TRADES_PER_FOLD = 30


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def source_tree_sha256() -> str:
    digest = hashlib.sha256()
    paths = []
    for directory in ("scripts", "src", "tests", "configs"):
        base = ROOT / directory
        if base.exists():
            paths.extend(p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    for path in sorted(paths, key=lambda p: p.relative_to(ROOT).as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def aggregate_series(trades: pd.DataFrame) -> pd.Series:
    """Equal-weight simultaneous eligible signals at each decision time."""
    if trades.empty:
        return pd.Series(dtype=float)
    decision = pd.to_datetime(trades["decision_time"], utc=True)
    return trades.assign(_decision=decision).groupby("_decision", sort=True)["net_return"].mean().astype(float)


def hac_t(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(float)
    n = len(values)
    if n < 3:
        return float("nan")
    lags = int(math.floor(4 * (n / 100) ** (2 / 9)))
    centered = values - values.mean()
    gamma = [float(np.dot(centered[k:], centered[: n - k])) / n for k in range(lags + 1)]
    variance = gamma[0] + 2 * sum((1 - k / (lags + 1)) * gamma[k] for k in range(1, lags + 1))
    return float(values.mean() / math.sqrt(variance / n)) if variance > 0 else float("nan")


def p_value(t_stat: float, observations: int) -> float:
    return float(2 * sps.t.sf(abs(t_stat), max(observations - 1, 1))) if np.isfinite(t_stat) and observations > 1 else float("nan")


def calendar_block_bootstrap(series: pd.Series) -> np.ndarray:
    if series.empty:
        return np.full(BOOTSTRAP_SAMPLES, np.nan)
    index = pd.to_datetime(series.index, utc=True)
    labels = pd.Index(index.strftime("%Y-%m"))
    blocks = sorted(labels.unique())
    values = [series.to_numpy(float)[labels == block] for block in blocks]
    rng = np.random.default_rng(SEED)
    draws = np.full(BOOTSTRAP_SAMPLES, np.nan)
    for draw in range(BOOTSTRAP_SAMPLES):
        chosen = rng.integers(0, len(values), size=len(values))
        pooled = np.concatenate([values[i] for i in chosen])
        if len(pooled):
            draws[draw] = float(pooled.mean())
    return draws


def concentration(trades: pd.DataFrame) -> dict[str, object]:
    if trades.empty:
        return {"symbols_traded": 0, "top_symbol": "", "top_symbol_share_abs": float("nan")}
    contribution = trades.groupby("symbol")["net_return"].sum().astype(float)
    total_abs = float(contribution.abs().sum())
    top = str(contribution.abs().idxmax())
    share = float(abs(contribution.loc[top]) / total_abs) if total_abs else float("nan")
    return {"symbols_traded": int(len(contribution)), "top_symbol": top, "top_symbol_share_abs": share}


def bh(pvalues: pd.Series) -> pd.Series:
    values = pvalues.to_numpy(float)
    order = np.argsort(np.where(np.isfinite(values), values, 2.0), kind="stable")
    result = np.full(len(values), np.nan)
    running = 1.0
    for rank in range(len(values) - 1, -1, -1):
        index = order[rank]
        if np.isfinite(values[index]):
            running = min(running, values[index] * len(values) / (rank + 1))
            result[index] = min(running, 1.0)
    return pd.Series(result, index=pvalues.index)


def replication_grade(row: object) -> str:
    if int(row.valid_fold_count) < 4:
        return "INSUFFICIENT_FOLDS"
    values = [row.positive_fold_fraction, row.fdr_q_value, row.aggregate_hac_t, row.max_top_symbol_share_abs, row.worst_fold_aggregate_mean, row.best_fold_aggregate_mean]
    if not all(np.isfinite(float(value)) for value in values):
        return "INSUFFICIENT_EVIDENCE"
    catastrophic = float(row.worst_fold_aggregate_mean) < -2.0 * float(row.best_fold_aggregate_mean)
    passes = (float(row.positive_fold_fraction) >= 0.75, float(row.fdr_q_value) <= 0.05, abs(float(row.aggregate_hac_t)) >= 3.0, float(row.max_top_symbol_share_abs) <= 0.50, not catastrophic)
    return "TEMPORAL_REPLICATION" if all(passes) else "NO_REPLICATION"


def _assert_trade_schema(trades: pd.DataFrame, path: Path) -> None:
    if set(trades.columns) != set(REQUIRED_TRADE_FIELDS):
        raise RuntimeError(f"{path.name}: trade schema mismatch")
    if trades.empty:
        return
    cutoff = pd.Timestamp("2024-01-01T00:00:00Z")
    for column in ("decision_time", "source_open_time", "source_available_time", "entry_time", "exit_time"):
        if pd.to_datetime(trades[column], utc=True).ge(cutoff).any():
            raise RuntimeError(f"{path.name}: January 2024/holdout observation")


def aggregate(root: Path, out: Path) -> dict[str, object]:
    manifest_path = root / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("unit_count") != 576 or manifest.get("status_counts") != {"VALID": 576} or manifest.get("final_holdout_status") != "UNTOUCHED":
        raise RuntimeError("aggregation requires sealed corrected 576-unit VALID manifest")
    trials, folds = load_registry()
    fold_ids = sorted({str(row["fold_id"]) for row in folds})
    by_key = {(str(item["fold_id"]), str(item["trial_id"])): item for item in manifest["units"]}
    fold_rows: list[dict[str, object]] = []
    horizon_rows: list[dict[str, object]] = []
    bootstrap_rows: list[dict[str, object]] = []
    concentration_rows: list[dict[str, object]] = []
    yearly_rows: list[dict[str, object]] = []
    for trial in trials:
        trial_id = str(trial["trial_id"])
        valid_series: list[pd.Series] = []
        fold_means: list[float] = []
        symbol_net: dict[str, float] = {}
        for fold_id in fold_ids:
            unit = by_key[(fold_id, trial_id)]
            path = root / "trades" / f"{unit['unit_id']}.parquet"
            trades = pd.read_parquet(path)
            _assert_trade_schema(trades, path)
            series = aggregate_series(trades)
            valid = str(unit["status"]) == "VALID" and len(trades) >= MINIMUM_TRADES_PER_FOLD
            fold_rows.append({"trial_id": trial_id, "fold_id": fold_id, "feature_id": trial["feature_id"], "signal_variant": trial["signal_variant"], "timeframe": trial["timeframe"], "side": trial["side"], "horizon_bars": int(trial["horizon_bars"]), "valid_fold": valid, "trades": int(len(trades)), "aggregate_observations": int(len(series)), "aggregate_mean_net_return": float(series.mean()) if len(series) else float("nan"), "aggregate_hac_t": hac_t(series) if len(series) > 1 else float("nan")})
            concentration_rows.append({"trial_id": trial_id, "fold_id": fold_id, "scope": "fold_diagnostic", **concentration(trades)})
            if valid:
                valid_series.append(series)
                fold_means.append(float(series.mean()))
                for symbol, value in trades.groupby("symbol")["net_return"].sum().items():
                    symbol_net[str(symbol)] = symbol_net.get(str(symbol), 0.0) + float(value)
                if len(series):
                    years = pd.Series(series.index.year, index=series.index)
                    for year, values in series.groupby(years):
                        yearly_rows.append({"trial_id": trial_id, "fold_id": fold_id, "year": int(year), "aggregate_observations": int(len(values)), "aggregate_mean_net_return": float(values.mean()), "aggregate_hac_t": hac_t(values)})
        combined = pd.concat(valid_series).sort_index() if valid_series else pd.Series(dtype=float)
        aggregate_concentration = concentration(pd.DataFrame({"symbol": list(symbol_net), "net_return": list(symbol_net.values())}))
        concentration_rows.append({"trial_id": trial_id, "fold_id": "ALL_VALID", "scope": "aggregate_valid_gate", **aggregate_concentration})
        draws = calendar_block_bootstrap(combined)
        lo = float(np.nanquantile(draws, 0.025)) if np.isfinite(draws).any() else float("nan")
        hi = float(np.nanquantile(draws, 0.975)) if np.isfinite(draws).any() else float("nan")
        means = np.asarray(fold_means, dtype=float)
        t_stat = hac_t(combined) if len(combined) > 1 else float("nan")
        horizon_rows.append({"trial_id": trial_id, "feature_id": trial["feature_id"], "signal_variant": trial["signal_variant"], "timeframe": trial["timeframe"], "side": trial["side"], "horizon_bars": int(trial["horizon_bars"]), "valid_fold_count": int(len(means)), "positive_fold_fraction": float(np.mean(means > 0)) if len(means) else float("nan"), "aggregate_observations": int(len(combined)), "aggregate_mean_net_return": float(combined.mean()) if len(combined) else float("nan"), "aggregate_hac_t": t_stat, "p_value": p_value(t_stat, len(combined)), "bootstrap_ci_low": lo, "bootstrap_ci_high": hi, "best_fold_aggregate_mean": float(np.max(means)) if len(means) else float("nan"), "worst_fold_aggregate_mean": float(np.min(means)) if len(means) else float("nan"), "top_symbol": aggregate_concentration["top_symbol"], "max_top_symbol_share_abs": aggregate_concentration["top_symbol_share_abs"]})
        bootstrap_rows.append({"trial_id": trial_id, "seed": SEED, "blocks": "calendar_month", "preserve": "all symbols together", "samples": BOOTSTRAP_SAMPLES, "ci95_low": lo, "ci95_high": hi})
    horizon = pd.DataFrame(horizon_rows).sort_values("trial_id").reset_index(drop=True)
    horizon["fdr_q_value"] = bh(horizon["p_value"])
    horizon["catastrophic_reversal"] = [bool(np.isfinite(row.worst_fold_aggregate_mean) and np.isfinite(row.best_fold_aggregate_mean) and row.worst_fold_aggregate_mean < -2.0 * row.best_fold_aggregate_mean) for row in horizon.itertuples()]
    horizon["temporal_replication"] = [replication_grade(row) for row in horizon.itertuples()]
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(fold_rows).to_csv(out / "fold_results.csv", index=False)
    horizon.to_csv(out / "horizon_results.csv", index=False)
    horizon[["trial_id", "feature_id", "signal_variant", "timeframe", "side", "horizon_bars", "valid_fold_count", "positive_fold_fraction", "aggregate_hac_t", "fdr_q_value", "max_top_symbol_share_abs", "catastrophic_reversal", "temporal_replication"]].to_csv(out / "temporal_replication.csv", index=False)
    horizon[["trial_id", "feature_id", "signal_variant", "timeframe", "side", "horizon_bars", "aggregate_hac_t", "p_value", "fdr_q_value"]].to_csv(out / "multiple_testing.csv", index=False)
    pd.DataFrame(bootstrap_rows).to_csv(out / "bootstrap_results.csv", index=False)
    pd.DataFrame(concentration_rows).to_csv(out / "symbol_concentration.csv", index=False)
    pd.DataFrame(yearly_rows).to_csv(out / "yearly_diagnostics.csv", index=False)
    horizon[horizon.temporal_replication == "TEMPORAL_REPLICATION"].to_csv(out / "candidate_shortlist.csv", index=False)
    proof = {"checkpoint_root": str(root), "checked_units": 576, "final_holdout_status": "UNTOUCHED", "status": "PASS", "method": "equal-weight decision-time series; calendar-month blocks preserving all symbols together"}
    (out / "holdout_guard_proof.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_names = ["fold_results.csv", "horizon_results.csv", "temporal_replication.csv", "multiple_testing.csv", "bootstrap_results.csv", "symbol_concentration.csv", "yearly_diagnostics.csv", "candidate_shortlist.csv", "holdout_guard_proof.json"]
    aggregate_manifest = {"checkpoint_root": str(root), "outcome_manifest_sha256": sha256(manifest_path), "outcome_implementation_commit": manifest["implementation_commit"], "outcome_source_tree_sha256": manifest["source_tree_sha256"], "registry_sha256": manifest["registry_sha256"], "fold_registry_sha256": manifest["fold_registry_sha256"], "causal_root_tree_sha256": manifest["causal_root_tree_sha256"], "aggregate_implementation_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "aggregate_source_tree_sha256": source_tree_sha256(), "unit_count": 576, "family_size": 72, "bootstrap_samples": BOOTSTRAP_SAMPLES, "bootstrap_seed": SEED, "bh_q": 0.05, "status": "PASS", "final_holdout_status": "UNTOUCHED", "artifact_sha256": {name: sha256(out / name) for name in sorted(artifact_names)}}
    (out / "aggregate_manifest.json").write_text(json.dumps(aggregate_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "PASS", "family_size": 72, "unit_count": 576, "fdr_survivors": int((horizon.fdr_q_value <= 0.05).sum()), "positive_fold_gate_count": int((horizon.positive_fold_fraction >= 0.75).sum()), "hac_gate_count": int((horizon.aggregate_hac_t.abs() >= 3.0).sum()), "concentration_gate_count": int((horizon.max_top_symbol_share_abs <= 0.50).sum()), "catastrophic_reversal_pass_count": int((~horizon.catastrophic_reversal).sum()), "catastrophic_reversal_fail_count": int(horizon.catastrophic_reversal.sum()), "temporal_replication_count": int((horizon.temporal_replication == "TEMPORAL_REPLICATION").sum()), "bootstrap_samples": BOOTSTRAP_SAMPLES, "bootstrap_seed": SEED, "final_holdout_status": "UNTOUCHED"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(aggregate(args.root, args.out_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
