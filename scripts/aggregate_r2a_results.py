"""Aggregate R2A evidence into the required final artifacts.

Validation partition is PRIMARY; train partition is descriptive only. All
trades were produced from pre-holdout panels (guard enforced at load and
execution); boundaries are re-asserted here before any statistic is computed.
"""

from __future__ import annotations

import math
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from r2a_engine import (  # noqa: E402

    HOLDOUT_BOUNDARY_BY_TF,
    SPLIT_FIRST_VALIDATION,
    SPLIT_LAST_VALIDATION,
    _hac_t_stat,
)
from verify_r2a_registry import HORIZON_BARS_24H  # noqa: E402

CAMPAIGN = ROOT / "campaigns" / "r2a_standalone_evidence_v1"
CHECKPOINT_ROOT = Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a/checkpoints")
SEED = 1729
FDR_ALPHA = 0.05
PPY = {"15m": 4 * 365 * 24, "1h": 365 * 24, "4h": 6 * 365}


def month_block_bootstrap_ci(frame: pd.DataFrame) -> tuple[float, float]:
    """Calendar-month block bootstrap on per-trade net returns."""
    if len(frame) < 30:
        return (float("nan"), float("nan"))
    values = frame["net_return"].to_numpy(dtype=float)
    month_index = np.asarray(pd.to_datetime(frame["decision_time"], utc=True).dt.strftime("%Y-%m"))
    unique_blocks = sorted(set(month_index.tolist()))
    block_arrays = [values[month_index == block] for block in unique_blocks]
    rng = np.random.default_rng(SEED)
    estimates = np.empty(1000)
    for sample in range(1000):
        chosen = rng.choice(len(unique_blocks), size=len(unique_blocks), replace=True)
        parts = [block_arrays[i] for i in chosen]
        pooled = np.concatenate(parts)
        estimates[sample] = pooled.mean() if len(pooled) else np.nan
    alpha = 0.025
    return (float(np.nanquantile(estimates, alpha)), float(np.nanquantile(estimates, 1 - alpha)))


def _max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return np.nan
    equity = (1 + values.astype(float)).cumprod()
    return float((equity / equity.cummax() - 1).min())


def partition_stats(trades: pd.DataFrame, timeframe: str, observations: int) -> dict[str, object]:
    n = len(trades)
    holding = HORIZON_BARS_24H[timeframe]
    out: dict[str, object] = {
        "observations": int(observations), "signals": n, "executed_trades": n,
        "signal_frequency": float(n / observations) if observations else np.nan,
        "exposure": float(min(1.0, n * holding / observations)) if observations else np.nan,
        "turnover": float(2 * n),
    }
    if n == 0:
        keys = ("gross_return", "net_return", "hit_rate", "mean_net_return", "median_net_return", "sharpe", "sortino", "max_drawdown", "calmar", "hac_t_stat", "bootstrap_ci_low", "bootstrap_ci_high")
        out.update({k: np.nan for k in keys})
        return out
    net = trades["net_return"].astype(float)
    gross = trades["gross_return"].astype(float)
    mean_net = float(net.mean())
    downside = float(math.sqrt(float(np.mean(np.minimum(net.to_numpy(), 0.0) ** 2))))
    mdd = _max_drawdown(net)
    ppy = PPY[timeframe]
    ci_low, ci_high = month_block_bootstrap_ci(trades)
    out.update({
        "gross_return": float((1 + gross).prod() - 1),
        "net_return": float((1 + net).prod() - 1),
        "hit_rate": float((net > 0).mean()),
        "mean_net_return": mean_net,
        "median_net_return": float(net.median()),
        "sharpe": float(np.sqrt(ppy) * mean_net / net.std(ddof=0)) if net.std(ddof=0) > 0 else np.nan,
        "sortino": float(np.sqrt(ppy) * mean_net / downside) if downside > 0 else np.nan,
        "max_drawdown": mdd,
        "calmar": float(mean_net * ppy / abs(mdd)) if mdd < 0 else np.nan,
        "hac_t_stat": _hac_t_stat(net),
        "bootstrap_ci_low": ci_low,
        "bootstrap_ci_high": ci_high,
    })
    return out


def main() -> int:
    registry = pd.read_csv(CAMPAIGN / "trial_registry.csv")
    results = pd.read_csv(CAMPAIGN / "trial_results_partial.csv").set_index("trial_id")
    assert len(results) == len(registry) == 252, "incomplete results"

    validation_rows, train_rows, hac_rows, boot_rows = [], [], [], []
    wf_rows, yearly_rows, concentration_rows = [], [], []

    for trial in registry.itertuples(index=False):
        trades = pd.read_parquet(CHECKPOINT_ROOT / f"{trial.trial_id}_trades.parquet")
        observations = int(results.loc[trial.trial_id, "observations"])
        base = {"trial_id": trial.trial_id, "feature_id": trial.feature_id, "market": trial.market, "timeframe": trial.timeframe, "side": trial.side}
        if trades.empty:
            empty = partition_stats(trades, trial.timeframe, observations)
            validation_rows.append({**base, **empty})
            train_rows.append({**base, **empty})
            hac_rows.append({**base, "hac_lags": "newey_west_automatic", "hac_t_stat": np.nan, "p_value_two_sided": np.nan, "n_trades": 0})
            boot_rows.append({**base, "seed": SEED, "blocks": "calendar_month", "samples": 1000, "ci95_low": np.nan, "ci95_high": np.nan})
            wf_rows.append({**base, "fold_count": 0, "positive_fold_fraction": np.nan})
            yearly_rows.append({"trial_id": trial.trial_id, "year": "", "trades": 0, "sharpe": np.nan})
            concentration_rows.append({"trial_id": trial.trial_id, "symbols_traded": 0, "top_symbol": "", "top_symbol_net_contribution": np.nan, "top_symbol_share": np.nan, "concentration_flag": False})
            continue
        stamps = pd.to_datetime(trades["decision_time"], utc=True)
        boundary = HOLDOUT_BOUNDARY_BY_TF[trial.timeframe]
        assert bool((stamps < boundary).all()), f"{trial.trial_id}: holdout contamination"
        first_val = SPLIT_FIRST_VALIDATION[trial.timeframe]
        last_val = SPLIT_LAST_VALIDATION[trial.timeframe]
        valid_part = trades[(stamps >= first_val) & (stamps <= last_val)]
        train_part = trades[stamps < first_val]
        vstats = partition_stats(valid_part, trial.timeframe, observations)
        tstats = partition_stats(train_part, trial.timeframe, observations)
        validation_rows.append({**base, **vstats})
        train_rows.append({**base, **tstats})
        hac_t = vstats["hac_t_stat"]
        hac_p = float(2 * sps.t.sf(abs(hac_t), df=max(len(valid_part) - 1, 1))) if np.isfinite(hac_t) and len(valid_part) > 1 else float("nan")
        hac_rows.append({**base, "hac_lags": "newey_west_automatic", "hac_t_stat": hac_t, "p_value_two_sided": hac_p, "n_trades": len(valid_part)})
        boot_rows.append({**base, "seed": SEED, "blocks": "calendar_month", "samples": 1000, "ci95_low": vstats["bootstrap_ci_low"], "ci95_high": vstats["bootstrap_ci_high"]})

        fold_sharpes = []
        if not valid_part.empty:
            month_str = pd.to_datetime(valid_part["decision_time"]).dt.strftime("%Y-%m")
            months_sorted = sorted(set(month_str))
            for i in range(1, len(months_sorted)):
                fold_months = set(months_sorted[max(0, i - 2):i + 1][-2:])
                fold = valid_part[month_str.isin(fold_months)]
                if len(fold) >= 10:
                    sd = float(fold["net_return"].astype(float).std(ddof=0))
                    mean_r = float(fold["net_return"].astype(float).mean())
                    fold_sharpes.append(float(np.sqrt(PPY[trial.timeframe]) * mean_r / sd) if sd > 0 else np.nan)
        finite_sharpes = [s for s in fold_sharpes if np.isfinite(s)]
        pos_frac = float(np.mean([s > 0 for s in finite_sharpes])) if finite_sharpes else np.nan
        wf_rows.append({**base, "fold_count": len(finite_sharpes), "positive_fold_fraction": pos_frac})

        if not valid_part.empty:
            years = pd.to_datetime(valid_part["decision_time"]).dt.year
            for year, group in valid_part.groupby(years):
                net = group["net_return"].astype(float)
                sharpe = float(np.sqrt(PPY[trial.timeframe]) * net.mean() / net.std(ddof=0)) if net.std(ddof=0) > 0 else np.nan
                yearly_rows.append({"trial_id": trial.trial_id, "year": int(year), "trades": len(group), "sharpe": sharpe})
            contrib = valid_part.groupby("symbol")["net_return"].sum().sort_values(ascending=False)
            total = float(contrib.sum())
            top_share = float(contrib.iloc[0] / total) if total != 0 else np.nan
            concentration_rows.append({"trial_id": trial.trial_id, "symbols_traded": int(contrib.shape[0]), "top_symbol": contrib.index[0], "top_symbol_net_contribution": float(contrib.iloc[0]), "top_symbol_share": top_share, "concentration_flag": bool(top_share > 0.5) if np.isfinite(top_share) else False})
        else:
            yearly_rows.append({"trial_id": trial.trial_id, "year": "", "trades": 0, "sharpe": np.nan})
            concentration_rows.append({"trial_id": trial.trial_id, "symbols_traded": 0, "top_symbol": "", "top_symbol_net_contribution": np.nan, "top_symbol_share": np.nan, "concentration_flag": False})


    validation = pd.DataFrame(validation_rows)
    train_desc = pd.DataFrame(train_rows)
    hac = pd.DataFrame(hac_rows)
    boot = pd.DataFrame(boot_rows)
    wf = pd.DataFrame(wf_rows)
    yearly = pd.DataFrame(yearly_rows)
    concentration = pd.DataFrame(concentration_rows)

    # Cohort diagnostics (validation, primary top50 as executed).
    universe = pd.read_csv(ROOT / "campaigns" / "r1_final_panel_v1" / "universe_monthly.csv", usecols=["market", "universe_month", "symbol", "selected_top20", "selected_top50", "selected_top100"])
    cohort_diag_rows = []
    for trial in registry.itertuples(index=False):
        trades = pd.read_parquet(CHECKPOINT_ROOT / (str(trial.trial_id) + "_trades.parquet"))
        if trades.empty:
            for cohort in ("top20", "top50", "top100"):
                cohort_diag_rows.append({"trial_id": trial.trial_id, "cohort": cohort, "trades": 0, "mean_net_return": np.nan, "sharpe": np.nan})
            continue
        stamps_t = pd.to_datetime(trades["decision_time"], utc=True)
        valid_part_c = trades[(stamps_t >= SPLIT_FIRST_VALIDATION[trial.timeframe]) & (stamps_t <= SPLIT_LAST_VALIDATION[trial.timeframe])]
        month_str_c = pd.to_datetime(valid_part_c["decision_time"]).dt.strftime("%Y-%m") if not valid_part_c.empty else pd.Series(dtype=str)
        for cohort in ("top20", "top50", "top100"):
            column = "selected_" + cohort
            allowed = set(universe.loc[(universe.market == trial.market) & universe[column].astype(bool)].apply(lambda r: (str(r.universe_month), str(r.symbol)), axis=1))
            if valid_part_c.empty:
                subset = valid_part_c
            else:
                mask_values = [(month, str(symbol)) in allowed for month, symbol in zip(month_str_c, valid_part_c["symbol"])]
                mask = pd.Series(mask_values, index=valid_part_c.index)
                subset = valid_part_c[mask]
            net = subset["net_return"].astype(float) if not subset.empty else pd.Series(dtype=float)
            sharpe = float(np.sqrt(PPY[trial.timeframe]) * net.mean() / net.std(ddof=0)) if len(net) > 1 and net.std(ddof=0) > 0 else np.nan
            cohort_diag_rows.append({"trial_id": trial.trial_id, "cohort": cohort, "trades": int(len(subset)), "mean_net_return": float(net.mean()) if len(net) else np.nan, "sharpe": sharpe})
    cohort_diag = pd.DataFrame(cohort_diag_rows)

    # Multiple testing: BH-FDR within market x timeframe family.
    hac["family"] = hac["market"] + "|" + hac["timeframe"]
    fdr_parts = []
    for family, group in hac.groupby("family"):
        p = group["p_value_two_sided"].to_numpy(dtype=float)
        m = len(p)
        bonf = np.minimum(np.where(np.isnan(p), np.nan, p * m), 1.0)
        order = np.argsort(np.where(np.isnan(p), 2.0, p))
        q = np.full(m, np.nan)
        running = 1.0
        for rank in range(m - 1, -1, -1):
            idx = order[rank]
            if np.isfinite(p[idx]):
                value = p[idx] * m / (rank + 1)
                running = min(running, value)
                q[idx] = min(running, 1.0)
        g = group.copy()
        g["bonferroni_p"] = bonf
        g["fdr_q_value"] = q
        fdr_parts.append(g)
    multiple_testing = pd.concat(fdr_parts, ignore_index=True).drop(columns=["family"])
    surviving_count = int((multiple_testing["fdr_q_value"] <= FDR_ALPHA).sum())

    # Frozen grading on validation evidence only.
    wf_count = wf.set_index("trial_id")["fold_count"].to_dict()
    wf_pos = wf.set_index("trial_id")["positive_fold_fraction"].to_dict()
    robustness_notes = []
    grades = []
    for row in validation.itertuples(index=False):
        mq = multiple_testing.loc[multiple_testing.trial_id == row.trial_id, "fdr_q_value"]
        qval = float(mq.iloc[0]) if len(mq) and np.isfinite(float(mq.iloc[0])) else float("nan")
        folds = int(wf_count.get(row.trial_id, 0))
        raw_pos = wf_pos.get(row.trial_id, np.nan)
        posfrac = float(raw_pos) if raw_pos is not None and np.isfinite(raw_pos) else -1.0
        if folds < 2:
            # Frozen criteria cannot be evaluated from a single fold; this must
            # never silently count as walk-forward replication PASS.
            grade = "D"
            mp = multiple_testing.loc[multiple_testing.trial_id == row.trial_id, "p_value_two_sided"]
            pval = float(mp.iloc[0]) if len(mp) else np.nan
            if np.isfinite(pval) and pval < 0.05:
                grade = "C"
            grades.append(grade)
            robustness_notes.append({"trial_id": row.trial_id, "note": "INSUFFICIENT_ROBUSTNESS_EVIDENCE", "fold_count": folds})
            continue
        grade = "D"
        if np.isfinite(qval) and np.isfinite(row.hac_t_stat) and abs(row.hac_t_stat) >= 3 and posfrac >= 0.75 and qval <= 0.05:
            grade = "A"
        elif np.isfinite(qval) and np.isfinite(row.hac_t_stat) and abs(row.hac_t_stat) >= 2 and posfrac >= 0.60 and qval <= 0.10:
            grade = "B"
        elif np.isfinite(row.hac_t_stat):
            mp = multiple_testing.loc[multiple_testing.trial_id == row.trial_id, "p_value_two_sided"]
            pval = float(mp.iloc[0]) if len(mp) else np.nan
            if np.isfinite(pval) and pval < 0.05:
                grade = "C"
            grades.append(grade)
    validation["grade"] = grades
    (CAMPAIGN / 'robustness_flags.json').write_text(json.dumps(robustness_notes, indent=2))

    validation.to_csv(CAMPAIGN / "validation_results.csv", index=False)
    train_desc.to_csv(CAMPAIGN / "train_descriptive.csv", index=False)
    hac.to_csv(CAMPAIGN / "hac_results.csv", index=False)
    boot.to_csv(CAMPAIGN / "bootstrap_results.csv", index=False)
    multiple_testing.to_csv(CAMPAIGN / "multiple_testing.csv", index=False)
    wf.to_csv(CAMPAIGN / "walk_forward_results.csv", index=False)
    yearly.to_csv(CAMPAIGN / "yearly_stability.csv", index=False)
    cohort_diag.to_csv(CAMPAIGN / "cohort_diagnostics.csv", index=False)
    concentration.to_csv(CAMPAIGN / "symbol_concentration.csv", index=False)

    shortlist_cols = ["trial_id", "feature_id", "market", "timeframe", "side", "executed_trades", "hit_rate", "mean_net_return", "sharpe", "hac_t_stat", "grade"]
    shortlist = validation[validation.grade.isin(["A", "B"])][shortlist_cols]
    shortlist.to_csv(CAMPAIGN / "candidate_shortlist.csv", index=False)

    counts = pd.Series(grades).value_counts().to_dict()
    summary = {
        "grades": counts,
        "fdr_survivors": surviving_count,
        "concentration_failures": int(concentration["concentration_flag"].sum()),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
