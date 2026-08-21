from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats

from .statistics import block_bootstrap_mean_ci


@dataclass(frozen=True)
class QuantileModel:
    edges: tuple[float, ...]
    quantiles: int
    fitted_count: int


def fit_quantile_model(training_values: pd.Series, quantiles: int = 5) -> QuantileModel:
    finite = pd.to_numeric(training_values, errors="coerce").dropna().to_numpy(dtype=float)
    if quantiles < 2:
        raise ValueError("at least two quantiles are required")
    if len(finite) < quantiles * 2:
        raise ValueError("insufficient training observations for requested quantiles")
    raw = np.quantile(finite, np.linspace(0, 1, quantiles + 1)[1:-1])
    edges = tuple(float(value) for value in np.unique(raw))
    return QuantileModel(edges, quantiles, len(finite))


def apply_quantile_model(values: pd.Series, model: QuantileModel) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    result = pd.Series(pd.NA, index=values.index, dtype="Int64")
    valid = numeric.notna()
    result.loc[valid] = np.searchsorted(np.asarray(model.edges), numeric.loc[valid].to_numpy(), side="right") + 1
    return result


def _future_path(bars: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if horizon < 1:
        raise ValueError("horizon must be at least one bar")
    n = len(bars)
    entry_return = np.full(n, np.nan)
    mfe = np.full(n, np.nan)
    mae = np.full(n, np.nan)
    time_mfe = np.full(n, np.nan)
    time_mae = np.full(n, np.nan)
    opens = bars["open"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    for decision in range(n):
        entry = decision + 1
        exit_bar = decision + horizon
        if entry >= n or exit_bar >= n or not np.isfinite(opens[entry]) or opens[entry] == 0:
            continue
        entry_price = opens[entry]
        entry_return[decision] = closes[exit_bar] / entry_price - 1
        path_high = highs[entry : exit_bar + 1] / entry_price - 1
        path_low = lows[entry : exit_bar + 1] / entry_price - 1
        if len(path_high) and np.isfinite(path_high).any() and np.isfinite(path_low).any():
            mfe[decision] = np.nanmax(path_high)
            mae[decision] = np.nanmin(path_low)
            time_mfe[decision] = int(np.nanargmax(path_high)) + 1
            time_mae[decision] = int(np.nanargmin(path_low)) + 1
    return pd.DataFrame(
        {"future_return": entry_return, "mfe": mfe, "mae": mae, "time_to_mfe": time_mfe, "time_to_mae": time_mae},
        index=bars.index,
    )


def _safe_correlation(x: pd.Series, y: pd.Series, method: str) -> float:
    paired = pd.concat([x, y], axis=1).dropna()
    if len(paired) < 3 or paired.iloc[:, 0].nunique() < 2 or paired.iloc[:, 1].nunique() < 2:
        return np.nan
    return float(paired.corr(method=method).iloc[0, 1])


def _summarize(sample: pd.DataFrame, feature: pd.Series) -> dict[str, float | int]:
    aligned = pd.concat([sample, feature.rename("feature")], axis=1).dropna(subset=["future_return", "feature"])
    returns = aligned["future_return"]
    return {
        "count": int(len(aligned)),
        "mean_future_return": float(returns.mean()) if len(aligned) else np.nan,
        "median_future_return": float(returns.median()) if len(aligned) else np.nan,
        "hit_rate": float((returns > 0).mean()) if len(aligned) else np.nan,
        "information_coefficient": _safe_correlation(aligned["feature"], returns, "pearson"),
        "rank_ic": _safe_correlation(aligned["feature"], returns, "spearman"),
        "mean_mfe": float(aligned["mfe"].mean()) if len(aligned) else np.nan,
        "mean_mae": float(aligned["mae"].mean()) if len(aligned) else np.nan,
        "median_time_to_mfe": float(aligned["time_to_mfe"].median()) if len(aligned) else np.nan,
        "median_time_to_mae": float(aligned["time_to_mae"].median()) if len(aligned) else np.nan,
    }


def predictive_study(
    bars: pd.DataFrame,
    feature: pd.Series,
    horizons: Iterable[int],
    quantile_model: QuantileModel,
    feature_id: str,
    partition: str,
) -> pd.DataFrame:
    """Evaluate OOS targets; the supplied quantile model must be fitted on training data."""
    quantile = apply_quantile_model(feature, quantile_model)
    records: list[dict[str, object]] = []
    for horizon in horizons:
        path = _future_path(bars, int(horizon))
        overall = _summarize(path, feature)
        overall_sample = path["future_return"].dropna()
        if len(overall_sample) >= 20:
            block_size = max(2, int(np.sqrt(len(overall_sample))))
            ci_low, ci_high = block_bootstrap_mean_ci(overall_sample, block_size, samples=200)
            overall["mean_return_ci_low"] = ci_low
            overall["mean_return_ci_high"] = ci_high
        records.append({"feature_id": feature_id, "partition": partition, "horizon_bars": horizon, "slice": "overall", **overall})
        for value in sorted(int(item) for item in quantile.dropna().unique()):
            mask = quantile == value
            summary = _summarize(path.loc[mask], feature.loc[mask])
            records.append({"feature_id": feature_id, "partition": partition, "horizon_bars": horizon, "slice": f"quantile_{value}", **summary})
        for label, mask in (("feature_positive", feature > 0), ("feature_negative", feature < 0)):
            summary = _summarize(path.loc[mask], feature.loc[mask])
            records.append({"feature_id": feature_id, "partition": partition, "horizon_bars": horizon, "slice": label, **summary})
    result = pd.DataFrame.from_records(records)
    monotonicity: dict[int, float] = {}
    for horizon, group in result[result["slice"].str.startswith("quantile_")].groupby("horizon_bars"):
        ordered = group.sort_values("slice")
        if len(ordered) >= 3:
            monotonicity[int(horizon)] = float(stats.spearmanr(np.arange(len(ordered)), ordered["mean_future_return"], nan_policy="omit").statistic)
    result["quantile_monotonicity"] = result["horizon_bars"].map(monotonicity)
    return result
