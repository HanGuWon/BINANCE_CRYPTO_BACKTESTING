from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence
import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster import hierarchy
from scipy.spatial.distance import squareform


EULER_GAMMA = 0.5772156649015329


def block_bootstrap_mean_ci(
    values: pd.Series,
    block_size: int,
    samples: int = 2_000,
    confidence: float = 0.95,
    seed: int = 1729,
) -> tuple[float, float]:
    clean = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if block_size < 1 or samples < 100:
        raise ValueError("block_size must be positive and samples at least 100")
    if len(clean) < block_size * 2:
        raise ValueError("insufficient observations for block bootstrap")
    rng = np.random.default_rng(seed)
    starts = np.arange(len(clean) - block_size + 1)
    estimates = np.empty(samples)
    blocks_needed = int(np.ceil(len(clean) / block_size))
    for sample in range(samples):
        selected = rng.choice(starts, size=blocks_needed, replace=True)
        bootstrap = np.concatenate([clean[start : start + block_size] for start in selected])[: len(clean)]
        estimates[sample] = bootstrap.mean()
    alpha = (1 - confidence) / 2
    return float(np.quantile(estimates, alpha)), float(np.quantile(estimates, 1 - alpha))


def correlation_matrix(frame: pd.DataFrame, method: str = "spearman", minimum_periods: int = 20) -> pd.DataFrame:
    numeric = frame.select_dtypes(include=[np.number])
    return numeric.corr(method=method, min_periods=minimum_periods)


def trade_overlap_matrix(signals: pd.DataFrame) -> pd.DataFrame:
    active = signals.fillna(0).ne(0)
    output = pd.DataFrame(np.nan, index=active.columns, columns=active.columns)
    for left in active:
        for right in active:
            union = (active[left] | active[right]).sum()
            output.loc[left, right] = float((active[left] & active[right]).sum() / union) if union else np.nan
    return output


def hierarchical_feature_clusters(correlation: pd.DataFrame, threshold: float = 0.35) -> pd.Series:
    if correlation.empty:
        return pd.Series(dtype="Int64", name="cluster")
    corr = correlation.fillna(0).clip(-1, 1)
    values = corr.to_numpy(dtype=float, copy=True)
    np.fill_diagonal(values, 1.0)
    corr = pd.DataFrame(values, index=corr.index, columns=corr.columns)
    distance = 1 - corr.abs()
    linkage = hierarchy.linkage(squareform(distance.values, checks=False), method="average")
    labels = hierarchy.fcluster(linkage, t=threshold, criterion="distance")
    return pd.Series(labels, index=correlation.index, name="cluster", dtype="Int64")


def deflated_sharpe_probability(
    observed_sharpe_periodic: float,
    trial_sharpes_periodic: Sequence[float] | pd.Series,
    observations: int,
    *,
    skewness: float,
    excess_kurtosis: float,
    moment_policy: Literal["observed", "gaussian_zero"] = "observed",
) -> float:
    """Approximate Bailey/Lopez de Prado DSR on periodic Sharpe inputs.

    This function performs no annualization.  Gaussian-zero moments are
    accepted only when explicitly requested by ``moment_policy``.
    """
    if moment_policy not in {"observed", "gaussian_zero"}:
        raise ValueError("moment_policy must be observed or gaussian_zero")
    if not np.isfinite(observed_sharpe_periodic):
        raise ValueError("observed_sharpe_periodic must be finite")
    if not np.isfinite(skewness) or not np.isfinite(excess_kurtosis):
        raise ValueError("skewness and excess_kurtosis must be finite")
    if moment_policy == "gaussian_zero" and (skewness != 0.0 or excess_kurtosis != 0.0):
        raise ValueError("gaussian_zero moment policy requires zero moments")
    trials = pd.to_numeric(pd.Series(trial_sharpes_periodic), errors="coerce")
    if trials.isna().any() or not np.isfinite(trials.to_numpy(dtype=float)).all():
        raise ValueError("trial_sharpes_periodic must contain only finite values")
    if observations < 3 or len(trials) < 2:
        return np.nan
    std_trials = float(trials.std(ddof=1))
    if std_trials == 0:
        return np.nan
    n_trials = len(trials)
    expected_max = std_trials * (
        (1 - EULER_GAMMA) * stats.norm.ppf(1 - 1 / n_trials)
        + EULER_GAMMA * stats.norm.ppf(1 - 1 / (n_trials * np.e))
    )
    denominator = np.sqrt(max(1e-15, (1 - skewness * observed_sharpe_periodic + (excess_kurtosis / 4) * observed_sharpe_periodic**2) / (observations - 1)))
    return float(stats.norm.cdf((observed_sharpe_periodic - expected_max) / denominator))


def annualize_sharpe(sharpe_periodic: float, periods_per_year: float) -> float:
    """Presentation-only conversion from periodic to annualized Sharpe."""
    if not np.isfinite(sharpe_periodic) or not np.isfinite(periods_per_year) or periods_per_year <= 0:
        raise ValueError("sharpe_periodic must be finite and periods_per_year must be positive")
    return float(sharpe_periodic * np.sqrt(periods_per_year))


@dataclass(frozen=True)
class StabilityDiagnostic:
    best_parameter: str
    best_score: float
    median_score: float
    positive_fraction: float
    isolated_peak_ratio: float


def parameter_stability(table: pd.DataFrame, parameter_column: str, score_column: str) -> StabilityDiagnostic:
    clean = table[[parameter_column, score_column]].dropna().sort_values(score_column, ascending=False)
    if clean.empty:
        raise ValueError("no finite parameter scores")
    best = clean.iloc[0]
    median = float(clean[score_column].median())
    denominator = max(abs(median), 1e-12)
    return StabilityDiagnostic(
        best_parameter=str(best[parameter_column]),
        best_score=float(best[score_column]),
        median_score=median,
        positive_fraction=float((clean[score_column] > 0).mean()),
        isolated_peak_ratio=float(abs(best[score_column]) / denominator),
    )
