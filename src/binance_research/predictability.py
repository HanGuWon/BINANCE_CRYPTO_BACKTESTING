from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit


TIMEFRAME_MINUTES: dict[str, int] = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
}

HORIZON_MINUTES: dict[str, int] = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "24h": 1440,
}

# Backward-compatible 15m mapping. New callers resolve against source timeframe.
HORIZON_BARS: dict[str, int] = {
    "15m": 1,
    "1h": 4,
    "4h": 16,
    "24h": 96,
}


def resolve_horizon_bars(source_timeframe: str, horizon: str) -> int:
    """Resolve a duration horizon to native bars without implicit rounding."""
    try:
        source_minutes = TIMEFRAME_MINUTES[source_timeframe]
    except KeyError as exc:
        raise ValueError(f"unsupported source timeframe: {source_timeframe}") from exc
    try:
        horizon_minutes = HORIZON_MINUTES[horizon]
    except KeyError as exc:
        raise ValueError(f"unsupported horizon: {horizon}") from exc
    if horizon_minutes < source_minutes:
        raise ValueError(f"horizon {horizon} is shorter than source timeframe {source_timeframe}")
    if horizon_minutes % source_minutes:
        raise ValueError(f"horizon {horizon} is not divisible by source timeframe {source_timeframe}")
    return horizon_minutes // source_minutes


@dataclass(frozen=True)
class LogisticModel:
    feature_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    means: tuple[float, ...]
    scales: tuple[float, ...]
    regularization: float

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        if not self.feature_names:
            return np.full(len(frame), expit(self.intercept), dtype=float)
        values = frame.loc[:, list(self.feature_names)].to_numpy(dtype=float)
        means = np.asarray(self.means, dtype=float)
        scales = np.asarray(self.scales, dtype=float)
        values = (values - means) / scales
        return expit(self.intercept + values @ np.asarray(self.coefficients, dtype=float))


def _finite_rows(frame: pd.DataFrame, columns: Sequence[str], target: pd.Series | None = None) -> np.ndarray:
    values = frame.loc[:, list(columns)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(values).all(axis=1)
    if target is not None:
        target_values = pd.to_numeric(target, errors="coerce").to_numpy(dtype=float)
        mask &= np.isfinite(target_values)
    return mask


def build_forward_labels(
    bars: pd.DataFrame,
    horizon_bars: int | None = None,
    *,
    source_timeframe: str = "15m",
    horizon: str | None = None,
) -> pd.DataFrame:
    """Build next-open labels with explicit maturity and candle continuity."""
    if source_timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"unsupported source timeframe: {source_timeframe}")
    if horizon is not None:
        resolved = resolve_horizon_bars(source_timeframe, horizon)
        if horizon_bars is not None and horizon_bars != resolved:
            raise ValueError("horizon_bars conflicts with duration horizon")
        horizon_bars = resolved
    if horizon_bars is None:
        raise ValueError("horizon or horizon_bars is required")
    if horizon_bars < 1:
        raise ValueError("horizon_bars must be positive")
    required = {"open", "close"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"missing label columns: {', '.join(sorted(missing))}")
    opens = pd.to_numeric(bars["open"], errors="coerce").to_numpy(dtype=float)
    closes = pd.to_numeric(bars["close"], errors="coerce").to_numpy(dtype=float)
    n = len(bars)
    future = np.full(n, np.nan, dtype=float)
    entry_index = np.full(n, -1, dtype=int)
    exit_index = np.full(n, -1, dtype=int)
    status = np.full(n, "INSUFFICIENT_FUTURE", dtype=object)
    interval = pd.Timedelta(minutes=TIMEFRAME_MINUTES[source_timeframe])
    open_times = None
    if "open_time" in bars:
        open_times = pd.to_datetime(bars["open_time"], utc=True, errors="coerce").reset_index(drop=True)
    close_times = None
    if "close_time" in bars:
        close_times = pd.to_datetime(bars["close_time"], utc=True, errors="coerce").reset_index(drop=True)
    decision_times = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns, UTC]")
    if open_times is not None:
        decision_times = close_times.copy() if close_times is not None else open_times + interval
        if close_times is not None:
            decision_times = decision_times.where(decision_times.notna(), open_times + interval)
    entry_times = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns, UTC]")
    exit_times = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns, UTC]")
    available_times = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns, UTC]")
    for decision in range(n):
        entry = decision + 1
        exit_bar = decision + horizon_bars
        if exit_bar >= n:
            continue
        if open_times is not None:
            segment = open_times.iloc[decision : exit_bar + 1]
            if segment.isna().any() or not (segment.diff().iloc[1:] == interval).all():
                status[decision] = "GAP"
                continue
        if not np.isfinite(opens[entry]) or opens[entry] <= 0 or not np.isfinite(closes[exit_bar]) or closes[exit_bar] <= 0:
            status[decision] = "INVALID_PRICE"
            continue
        future[decision] = np.log(closes[exit_bar] / opens[entry])
        entry_index[decision] = entry
        exit_index[decision] = exit_bar
        status[decision] = "ELIGIBLE"
        if open_times is not None:
            entry_times.iloc[decision] = open_times.iloc[entry]
            exit_times.iloc[decision] = open_times.iloc[exit_bar]
            available_times.iloc[decision] = (close_times.iloc[exit_bar] if close_times is not None and pd.notna(close_times.iloc[exit_bar]) else open_times.iloc[exit_bar] + interval)
    direction = np.where(future > 0, 1, np.where(future < 0, 0, np.nan))
    return pd.DataFrame(
        {
            "future_log_return": future,
            "direction_up": direction,
            "entry_index": entry_index,
            "exit_index": exit_index,
            "label_status": status,
            "eligible": status == "ELIGIBLE",
            "decision_time": decision_times.to_numpy(),
            "entry_time": entry_times.to_numpy(),
            "exit_time": exit_times.to_numpy(),
            "label_available_time": available_times.to_numpy(),
        },
        index=bars.index,
    )


def mature_training_mask(labels: pd.DataFrame, first_validation_decision_time: object) -> pd.Series:
    """Return labels eligible and fully observed strictly before validation."""
    eligible = labels.get("eligible", labels["direction_up"].notna()).astype(bool)
    if "label_available_time" not in labels:
        return eligible
    boundary = pd.Timestamp(first_validation_decision_time)
    boundary = boundary.tz_localize("UTC") if boundary.tzinfo is None else boundary.tz_convert("UTC")
    available = pd.to_datetime(labels["label_available_time"], utc=True, errors="coerce")
    return eligible & available.notna() & (available < boundary)

def fit_logistic_model(
    frame: pd.DataFrame,
    target: pd.Series,
    feature_names: Iterable[str],
    regularization: float = 1.0,
) -> LogisticModel:
    names = tuple(feature_names)
    if regularization < 0:
        raise ValueError("regularization must be non-negative")
    if names:
        mask = _finite_rows(frame, names, target)
        values = frame.loc[mask, list(names)].to_numpy(dtype=float)
    else:
        target_values = pd.to_numeric(target, errors="coerce").to_numpy(dtype=float)
        mask = np.isfinite(target_values)
        values = np.empty((int(mask.sum()), 0), dtype=float)
    labels = pd.to_numeric(target, errors="coerce").to_numpy(dtype=float)[mask]
    labels = np.rint(labels).astype(float)
    if len(labels) < 8 or np.unique(labels).size < 2:
        raise ValueError("logistic training requires at least two classes and eight rows")
    if names:
        means = values.mean(axis=0)
        scales = values.std(axis=0)
        scales[scales == 0] = 1.0
        standardized = (values - means) / scales
    else:
        means = np.empty(0, dtype=float)
        scales = np.empty(0, dtype=float)
        standardized = values
    prior = float(np.clip(labels.mean(), 1e-6, 1 - 1e-6))
    initial = np.concatenate(([log(prior / (1 - prior))], np.zeros(len(names), dtype=float)))

    def objective(parameters: np.ndarray) -> tuple[float, np.ndarray]:
        intercept = parameters[0]
        coefficients = parameters[1:]
        logits = intercept + standardized @ coefficients
        probabilities = expit(logits)
        loss = -np.sum(labels * np.log(np.clip(probabilities, 1e-12, 1.0)) + (1 - labels) * np.log(np.clip(1 - probabilities, 1e-12, 1.0)))
        loss += 0.5 * regularization * float(np.dot(coefficients, coefficients))
        error = probabilities - labels
        gradient = np.concatenate(([error.sum()], standardized.T @ error + regularization * coefficients))
        return float(loss), gradient

    result = minimize(lambda p: objective(p), initial, jac=True, method="L-BFGS-B")
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError(f"logistic optimization failed: {result.message}")
    return LogisticModel(names, tuple(float(v) for v in result.x[1:]), float(result.x[0]), tuple(float(v) for v in means), tuple(float(v) for v in scales), regularization)


def constant_probability(target: pd.Series) -> float:
    values = pd.to_numeric(target, errors="coerce").dropna().to_numpy(dtype=float)
    if not len(values):
        raise ValueError("cannot fit a constant probability without labels")
    return float(np.clip(values.mean(), 1e-6, 1 - 1e-6))


def _log_loss(labels: np.ndarray, probabilities: np.ndarray) -> float:
    probabilities = np.clip(probabilities, 1e-12, 1 - 1e-12)
    return float(-np.mean(labels * np.log(probabilities) + (1 - labels) * np.log(1 - probabilities)))


def _roc_auc(labels: np.ndarray, probabilities: np.ndarray) -> float:
    positives = labels == 1
    negatives = labels == 0
    if not positives.any() or not negatives.any():
        return np.nan
    ranks = pd.Series(probabilities).rank(method="average").to_numpy(dtype=float)
    return float((ranks[positives].sum() - positives.sum() * (positives.sum() + 1) / 2) / (positives.sum() * negatives.sum()))


def probability_metrics(labels: pd.Series, probabilities: Sequence[float], baseline_probabilities: Sequence[float] | None = None) -> dict[str, float | int]:
    values = pd.to_numeric(labels, errors="coerce").to_numpy(dtype=float)
    probs = np.asarray(probabilities, dtype=float)
    mask = np.isfinite(values) & np.isfinite(probs)
    values, probs = values[mask], probs[mask]
    if len(values) == 0:
        return {"count": 0, "observed_up_rate": np.nan, "predicted_up_rate": np.nan, "direction_accuracy": np.nan, "balanced_accuracy": np.nan, "log_loss": np.nan, "brier_score": np.nan, "roc_auc": np.nan, "log_loss_improvement": np.nan}
    predicted = probs >= 0.5
    positive = values == 1
    negative = values == 0
    sensitivity = float((predicted[positive]).mean()) if positive.any() else np.nan
    specificity = float((~predicted[negative]).mean()) if negative.any() else np.nan
    baseline_loss = np.nan
    if baseline_probabilities is not None:
        base = np.asarray(baseline_probabilities, dtype=float)[mask]
        baseline_loss = _log_loss(values, base)
    loss = _log_loss(values, probs)
    return {
        "count": int(len(values)),
        "observed_up_rate": float(values.mean()),
        "predicted_up_rate": float(predicted.mean()),
        "direction_accuracy": float((predicted == values).mean()),
        "balanced_accuracy": float(np.nanmean([sensitivity, specificity])),
        "log_loss": loss,
        "brier_score": float(np.mean((probs - values) ** 2)),
        "roc_auc": _roc_auc(values, probs),
        "log_loss_improvement": float(baseline_loss - loss) if np.isfinite(baseline_loss) else np.nan,
    }


def block_bootstrap_mean_ci(values: Sequence[float], block_size: int = 7, samples: int = 1000, seed: int = 1729) -> tuple[float, float]:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if len(clean) < max(2, block_size * 2):
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    starts = np.arange(len(clean) - block_size + 1)
    count = int(np.ceil(len(clean) / block_size))
    means = np.empty(samples, dtype=float)
    for index in range(samples):
        selected = rng.choice(starts, size=count, replace=True)
        sample = np.concatenate([clean[start : start + block_size] for start in selected])[: len(clean)]
        means[index] = sample.mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def _baseline_columns(frame: pd.DataFrame) -> pd.DataFrame:
    close = pd.to_numeric(frame["close"], errors="coerce")
    output = pd.DataFrame(index=frame.index)
    output["baseline_return_1"] = close.pct_change(fill_method=None)
    output["baseline_volatility_16"] = close.pct_change(fill_method=None).rolling(16, min_periods=8).std()
    if "volume" in frame:
        volume = pd.to_numeric(frame["volume"], errors="coerce")
        output["baseline_volume_change"] = volume.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    return output


def evaluate_walk_forward(
    frame: pd.DataFrame,
    feature_columns: Sequence[str],
    horizons: Sequence[str] = ("15m", "1h", "4h", "24h"),
    minimum_train: int = 256,
    validation_size: int = 96,
    step_size: int = 96,
    regularization: float = 1.0,
    source_timeframe: str = "15m",
) -> pd.DataFrame:
    baseline = _baseline_columns(frame)
    available = [name for name in feature_columns if name in frame]
    rows: list[dict[str, object]] = []
    for horizon_name in horizons:
        horizon_bars = resolve_horizon_bars(source_timeframe, horizon_name)
        label_frame = build_forward_labels(frame, horizon_bars, source_timeframe=source_timeframe, horizon=horizon_name)
        labels = label_frame["direction_up"]
        fold = 0
        train_end = minimum_train
        while train_end < len(frame):
            validation_end = min(len(frame), train_end + validation_size)
            if validation_end <= train_end:
                break
            train_slice = slice(0, train_end)
            validation_slice = slice(train_end, validation_end)
            y_train = labels.iloc[train_slice]
            y_validation = labels.iloc[validation_slice]
            first_validation_time = label_frame.iloc[train_end]["decision_time"]
            if pd.isna(first_validation_time):
                valid_train = y_train.notna()
            else:
                valid_train = mature_training_mask(label_frame.iloc[train_slice], first_validation_time).set_axis(y_train.index)
            valid_validation = y_validation.notna() & label_frame.iloc[validation_slice]["eligible"].to_numpy(dtype=bool)
            if valid_train.sum() >= 8 and valid_validation.sum() > 0 and y_train[valid_train].nunique() > 1:
                baseline_probability = constant_probability(y_train[valid_train])
                baseline_probabilities = np.full(int(valid_validation.sum()), baseline_probability)
                validation_labels = y_validation[valid_validation]
                base_frame_train = baseline.iloc[train_slice]
                base_frame_validation = baseline.iloc[validation_slice].loc[valid_validation]
                base_names = list(baseline.columns)
                base_model = fit_logistic_model(base_frame_train.loc[valid_train], y_train[valid_train], base_names, regularization)
                base_probabilities = base_model.predict_proba(base_frame_validation)
                base_plus_names = base_names + available
                combined_train = pd.concat([base_frame_train, frame.loc[frame.index[train_slice], available]], axis=1)
                combined_validation = pd.concat([base_frame_validation, frame.loc[frame.index[validation_slice], available].loc[valid_validation]], axis=1)
                def add_result(model_name: str, probabilities: np.ndarray, comparator: np.ndarray) -> None:
                    metrics = probability_metrics(validation_labels, probabilities, comparator)
                    current_loss = -np.log(np.clip(probabilities, 1e-12, 1 - 1e-12)) * validation_labels.to_numpy() - np.log(np.clip(1 - probabilities, 1e-12, 1 - 1e-12)) * (1 - validation_labels.to_numpy())
                    comparator_loss = -np.log(np.clip(comparator, 1e-12, 1 - 1e-12)) * validation_labels.to_numpy() - np.log(np.clip(1 - comparator, 1e-12, 1 - 1e-12)) * (1 - validation_labels.to_numpy())
                    ci_low, ci_high = block_bootstrap_mean_ci(comparator_loss - current_loss)
                    rows.append({"horizon": horizon_name, "fold": fold, "model": model_name, "train_rows": int(valid_train.sum()), "validation_rows": int(valid_validation.sum()), "ci_low_log_loss_improvement": ci_low, "ci_high_log_loss_improvement": ci_high, **metrics})
                add_result("B0", baseline_probabilities, baseline_probabilities)
                add_result("B1", base_probabilities, baseline_probabilities)
                model_specs: list[tuple[str, Sequence[str], pd.DataFrame, pd.DataFrame, np.ndarray]] = [("B1+I", base_names + available, combined_train, combined_validation, base_probabilities)]
                for feature in available:
                    model_specs.append(("I:" + feature, [feature], frame.loc[frame.index[train_slice], [feature]].loc[valid_train], frame.loc[frame.index[validation_slice], [feature]].loc[valid_validation], base_probabilities))
                for model_name, names, train_frame, validation_frame, comparator in model_specs:
                    try:
                        model = fit_logistic_model(train_frame.loc[valid_train], y_train[valid_train], names, regularization)
                        probabilities = model.predict_proba(validation_frame)
                    except ValueError:
                        continue
                    add_result(model_name, probabilities, comparator)
            fold += 1
            train_end += step_size
    return pd.DataFrame.from_records(rows)
