"""Holdout-guarded R2A execution engine (preregistered trials only).

Design invariants:
- Predicate-filtered Parquet reads: rows at/after the frozen holdout boundary
  are never materialized by the panel loader.
- Every evaluator/scorer receives only pre-holdout frames; a runtime guard
  rejects any frame containing holdout timestamps.
- Deterministic trial_id checkpoints make resume bit-identical.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from binance_research.derivatives import funding_event_zscore  # noqa: E402
from verify_r2a_registry import HORIZON_BARS_24H, SIGNAL_SEMANTICS  # noqa: E402

# ------------------------------------------------------------------ guards

HOLDOUT_BOUNDARY_UTC = "2024-02-10T00:15:00+00:00"  # first_test_holdout_timestamp_utc (15m)
HOLDOUT_BOUNDARY_BY_TF = {
    "15m": pd.Timestamp("2024-02-10T00:15:00+00:00"),
    "1h": pd.Timestamp("2024-02-10T01:00:00+00:00"),
    "4h": pd.Timestamp("2024-02-10T04:00:00+00:00"),
}
TRAIN_BOUNDARY_UTC = "2024-01-20T00:00:00+00:00"
OPERATIONAL_EMBARGO_BARS = 1
SPLIT_LAST_TRAIN = {
    "15m": pd.Timestamp("2024-01-18T23:45:00+00:00"),
    "1h": pd.Timestamp("2024-01-18T23:00:00+00:00"),
    "4h": pd.Timestamp("2024-01-18T20:00:00+00:00"),
}
SPLIT_FIRST_VALIDATION = {
    "15m": pd.Timestamp("2024-01-20T00:15:00+00:00"),
    "1h": pd.Timestamp("2024-01-20T01:00:00+00:00"),
    "4h": pd.Timestamp("2024-01-20T04:00:00+00:00"),
}
SPLIT_LAST_VALIDATION = {
    "15m": pd.Timestamp("2024-02-08T23:45:00+00:00"),
    "1h": pd.Timestamp("2024-02-08T23:00:00+00:00"),
    "4h": pd.Timestamp("2024-02-08T20:00:00+00:00"),
}


class HoldoutViolation(RuntimeError):
    """Raised when any routine is handed timestamps at/after its holdout boundary."""


def assert_no_holdout(frame: pd.DataFrame, *, timeframe: str | None = None, timestamp_column: str = "timestamp", context: str = "") -> None:
    """Hard guard: reject any frame that contains holdout timestamps."""
    if timestamp_column not in frame:
        raise HoldoutViolation(f"{context}: missing {timestamp_column}; cannot prove holdout exclusion")
    stamps = pd.to_datetime(frame[timestamp_column], utc=True)
    boundary = HOLDOUT_BOUNDARY_BY_TF[timeframe] if timeframe else pd.Timestamp(HOLDOUT_BOUNDARY_UTC)
    violations = stamps >= boundary
    if bool(violations.any()):
        first = stamps[violations].min()
        raise HoldoutViolation(f"{context}: holdout row present at {first}")


def load_panel_pre_holdout(
    root: Path,
    market: str,
    timeframe: str,
    *,
    columns: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Stream partitions with predicate pushdown; holdout rows never load."""
    pattern_root = Path(root) / f"market={market}"
    paths = sorted(pattern_root.glob(f"symbol=*/timeframe={timeframe}/year=*/part-000.parquet"))
    if not paths:
        raise FileNotFoundError(f"no partitions for {market}/{timeframe} under {root}")
    boundary_ns = int(HOLDOUT_BOUNDARY_BY_TF[timeframe].value)
    parts: list[pd.DataFrame] = []
    for path in paths:
        parquet = pq.ParquetFile(path)
        schema_names = parquet.schema_arrow.names
        wanted = [c for c in columns if c in schema_names] if columns else None
        table = parquet.read(columns=wanted or None)
        stamps = table.column("timestamp").cast("int64")
        mask = stamps < boundary_ns
        if mask.null_count or not bool(mask.any()):
            continue
        parts.append(table.filter(mask).to_pandas())
    if not parts:
        raise FileNotFoundError(f"{market}/{timeframe}: every partition lies inside the holdout")
    frame = pd.concat(parts, ignore_index=True)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.sort_values(["symbol", "timestamp"], kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------- signals

_WARMUP_BARS: dict[tuple[str, str], int] = {
    ("trend.ema_20_50_spread", "ema_10_30"): 30,
    ("trend.ema_20_50_spread", "ema_20_50"): 50,
    ("trend.ema_20_50_spread", "ema_50_200"): 200,
    ("trend.ema_50_200_regime", "ema_10_30"): 30,
    ("trend.ema_50_200_regime", "ema_20_50"): 50,
    ("trend.ema_50_200_regime", "ema_50_200"): 200,
    ("trend.ema_slope", "default"): 25,
    ("trend.adx_dmi", "adx14_threshold20"): 28,
    ("trend.kaufman_er", "er10_threshold0.3"): 25,
    ("trend.donchian", "donchian_20"): 21,
    ("trend.donchian", "donchian_48"): 49,
    ("trend.donchian", "donchian_55"): 56,
    ("momentum.roc", "roc_6"): 7,
    ("momentum.roc", "roc_12"): 13,
    ("momentum.roc", "roc_24"): 25,
    ("momentum.rsi", "rsi_7_30_70"): 8,
    ("momentum.rsi", "rsi_14_30_70"): 15,
    ("momentum.rsi", "rsi_21_30_70"): 22,
    ("volatility.atr_natr", "natr14_filter"): 115,
    ("volatility.bollinger_bandwidth", "bb20_2s_filter"): 121,
    ("volatility.realized_percentile", "rv20_p100_filter"): 127,
    ("volume.rvol", "rvol20_filter"): 27,
    ("volume.vwap_deviation", "vwap_dev20_reversal"): 21,
    ("orderflow.taker_ratio", "ratio_sign"): 1,
    ("orderflow.cvd", "cvd_slope6_sign"): 7,
    ("context.btc_regime", "regime_follow"): 200,
    ("context.market_breadth", "breadth_0.4_0.6"): 1,
    ("derivatives.funding", "funding_sign"): 0,
    ("derivatives.funding_zscore", "z90_extreme"): 90,
}


def _safe_sign(series: pd.Series) -> pd.Series:
    result = np.sign(series)
    return result.where(series.notna())


def compute_signal(frame: pd.DataFrame, feature_id: str, variant: str, market: str) -> pd.Series:
    """Deterministic per-symbol signal on completed bars; NaN until warmup."""
    key = (feature_id, variant)
    if key not in SIGNAL_SEMANTICS:
        raise ValueError(f"unregistered signal: {key}")
    base = frame.reset_index(drop=True)
    close = base["close"].astype(float)
    high = base["high"].astype(float)
    low = base["low"].astype(float)
    volume = base["volume"].astype(float)
    if feature_id == "trend.ema_20_50_spread":
        fast, slow = {"ema_10_30": (10, 30), "ema_20_50": (20, 50), "ema_50_200": (50, 200)}[variant]
        ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
        ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
        return _safe_sign(ema_fast - ema_slow)
    if feature_id == "trend.ema_50_200_regime":
        fast, slow = {"ema_10_30": (10, 30), "ema_20_50": (20, 50), "ema_50_200": (50, 200)}[variant]
        ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
        ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
        return _safe_sign(ema_fast - ema_slow)
    if feature_id == "trend.ema_slope":
        ema20 = close.ewm(span=20, adjust=False, min_periods=20).mean()
        slope = (ema20 - ema20.shift(5)) / (5 * close)
        return _safe_sign(slope)
    if feature_id == "trend.adx_dmi":
        up = high.diff()
        down = -low.diff()
        plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0))
        minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0))
        tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().div(atr.replace(0, np.nan))
        minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().div(atr.replace(0, np.nan))
        adx = (plus_di - minus_di).abs().div((plus_di + minus_di).replace(0, np.nan)).mul(100).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        signal = pd.Series(0.0, index=base.index)
        signal[(adx >= 20) & (plus_di > minus_di)] = 1.0
        signal[(adx >= 20) & (minus_di > plus_di)] = -1.0
        return signal.where(adx.notna() & plus_di.notna() & minus_di.notna())
    if feature_id == "trend.kaufman_er":
        direction = close.diff(10).abs()
        path = close.diff().abs().rolling(10, min_periods=10).sum()
        er = direction.div(path.replace(0, np.nan)).clip(0, 1)
        slope = close.diff(5)
        signal = pd.Series(0.0, index=base.index)
        signal[(er >= 0.3) & (slope > 0)] = 1.0
        signal[(er >= 0.3) & (slope < 0)] = -1.0
        return signal.where(er.notna() & slope.notna())
    if feature_id == "trend.donchian":
        period = int(variant.split("_")[1])
        prior_high = high.shift(1).rolling(period, min_periods=period).max()
        prior_low = low.shift(1).rolling(period, min_periods=period).min()
        signal = pd.Series(0.0, index=base.index)
        signal[close > prior_high] = 1.0
        signal[close < prior_low] = -1.0
        return signal.where(prior_high.notna() & prior_low.notna())
    if feature_id == "momentum.roc":
        period = int(variant.split("_")[1])
        roc = close.pct_change(period, fill_method=None)
        return _safe_sign(roc)
    if feature_id == "momentum.rsi":
        parts = variant.split("_")
        period = int(parts[1])
        lower, upper = float(parts[2]), float(parts[3])
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        rs = gain.div(loss.replace(0, np.nan))
        rsi = 100 - 100 / (1 + rs)
        rsi = rsi.mask((loss == 0) & (gain > 0), 100.0).mask((gain == 0) & (loss > 0), 0.0).mask((gain == 0) & (loss == 0), 50.0)
        signal = pd.Series(0.0, index=base.index)
        signal[rsi <= lower] = 1.0
        signal[rsi >= upper] = -1.0
        return signal.where(rsi.notna())
    if feature_id in ("volatility.atr_natr", "volatility.bollinger_bandwidth", "volatility.realized_percentile", "volume.rvol"):
        # Preregistered deterministic filter semantics; never a post-hoc direction.
        log_return = np.log(close).diff()
        if feature_id == "volatility.atr_natr":
            tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
            atr = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
            natr = 100 * atr.div(close)
            expanding_rank = natr.expanding(min_periods=100).apply(lambda values: (values <= values[-1]).mean(), raw=True)
            active = expanding_rank > 2 / 3
            momentum = _safe_sign(close.pct_change(6, fill_method=None))
        elif feature_id == "volatility.bollinger_bandwidth":
            mean20 = close.rolling(20, min_periods=20).mean()
            std20 = close.rolling(20, min_periods=20).std(ddof=0)
            bandwidth = (4 * std20).div(mean20)
            active = bandwidth > bandwidth.shift(1)
            momentum = _safe_sign(close.diff())
        elif feature_id == "volatility.realized_percentile":
            rv = log_return.rolling(20, min_periods=20).std(ddof=0) * np.sqrt(20)
            percentile = rv.rolling(100, min_periods=100).apply(lambda values: (values <= values[-1]).mean(), raw=True)
            active = percentile > 0.8
            momentum = _safe_sign(close.pct_change(6, fill_method=None))
        else:
            volume_mean = volume.rolling(20, min_periods=20).mean()
            rvol = volume.div(volume_mean)
            active = rvol >= 2.0
            momentum = _safe_sign(close.pct_change(6, fill_method=None))
        signal = pd.Series(0.0, index=base.index)
        signal[active.fillna(False) & momentum.eq(1.0)] = 1.0
        signal[active.fillna(False) & momentum.eq(-1.0)] = -1.0
        return signal.where(momentum.notna() | active.fillna(False))
    if feature_id == "volume.vwap_deviation":
        typical = (high + low + close) / 3
        notional = (typical * volume).rolling(20, min_periods=20).sum()
        rolling_volume = volume.rolling(20, min_periods=20).sum()
        vwap = notional.div(rolling_volume.replace(0, np.nan))
        deviation = (close - vwap).div(vwap.replace(0, np.nan))
        return _safe_sign(deviation) * -1.0
    if feature_id == "orderflow.taker_ratio":
        taker_buy = frame["taker_buy_volume"].astype(float)
        aggressive_sell = volume - taker_buy
        ratio = taker_buy.div(aggressive_sell.replace(0, np.nan))
        return _safe_sign(ratio - 1.0)
    if feature_id == "orderflow.cvd":
        taker_buy = frame["taker_buy_volume"].astype(float)
        cvd = (taker_buy - (volume - taker_buy)).cumsum(skipna=False)
        return _safe_sign(cvd.diff(6))
    if feature_id == "context.btc_regime":
        return pd.to_numeric(frame["btc_regime"], errors="coerce")
    if feature_id == "context.market_breadth":
        breadth = pd.to_numeric(frame["market_breadth"], errors="coerce")
        signal = pd.Series(0.0, index=base.index)
        signal[breadth >= 0.6] = 1.0
        signal[breadth <= 0.4] = -1.0
        return signal.where(breadth.notna())
    if feature_id == "derivatives.funding":
        rate = pd.to_numeric(frame["funding_rate"], errors="coerce")
        return _safe_sign(rate) * -1.0
    if feature_id == "derivatives.funding_zscore":
        zscore_column = "funding_zscore90_y" if "funding_zscore90_y" in frame else "funding_zscore90"
        zscore = pd.to_numeric(frame[zscore_column], errors="coerce")
        signal = pd.Series(0.0, index=base.index)
        signal[zscore >= 3.0] = -1.0
        signal[zscore <= -3.0] = 1.0
        return signal.where(zscore.notna())
    raise ValueError(f"signal computation missing for {key}")


# ------------------------------------------------------------- evaluation

COSTS = {
    "spot": {"taker_bps": 10.0, "slippage_bps": 5.0},
    "um": {"taker_bps": 5.0, "slippage_bps": 5.0},
}


def _funding_events(symbol: str, raw_root: Path = Path("data/raw/um/fundingRate")) -> pd.DataFrame | None:
    """Load verified funding event archives (no interpolation)."""
    root = raw_root / symbol
    if not root.is_dir():
        return None
    import io
    import zipfile
    frames = []
    for path in sorted(root.glob(symbol + "-*.zip")):
        try:
            with zipfile.ZipFile(path) as archive:
                name = next(n for n in archive.namelist() if n.endswith(".csv"))
                with archive.open(name) as handle:
                    frame = pd.read_csv(io.TextIOWrapper(handle, encoding="utf-8"))
        except Exception:
            continue
        stamp_column = next((c for c in ("calc_time", "open_time", "timestamp") if c in frame), None)
        rate_column = next((c for c in ("last_funding_rate", "funding_rate", "close") if c in frame), None)
        if stamp_column is None or rate_column is None:
            continue
        frames.append(frame[[stamp_column, rate_column]].rename(columns={stamp_column: "timestamp", rate_column: "funding_rate"}))
    if not frames:
        return None
    events = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp")
    events["timestamp"] = pd.to_datetime(pd.to_numeric(events["timestamp"], errors="coerce"), unit="ms", utc=True)
    return events.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def _crossed_funding_cost(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp, direction: int, events: pd.DataFrame | None) -> float:
    if events is None or len(events) == 0:
        return 0.0
    crossed = events[(events.timestamp > entry_ts) & (events.timestamp <= exit_ts)]
    return -direction * float(crossed.funding_rate.sum())

def _max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return np.nan
    equity = (1 + values.astype(float)).cumprod()
    return float((equity / equity.cummax() - 1).min())


def _hac_t_stat(returns: pd.Series, max_lags: int | None = None) -> float:
    """Newey-West t-statistic for the mean of a return series."""
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    n = len(values)
    if n < 3:
        return np.nan
    lags = int(np.floor(4 * (n / 100) ** (2 / 9))) if max_lags is None else max_lags
    centered = values - values.mean()
    gamma = np.array([float(np.dot(centered[k:], centered[: n - k])) / n for k in range(lags + 1)])
    weights = 1 - np.arange(lags + 1) / (lags + 1)
    variance = gamma[0] + 2 * float(np.sum(weights[1:] * gamma[1:]))
    if variance <= 0:
        return np.nan
    return float(values.mean() / math.sqrt(variance / n))


def _month_block_bootstrap_ci(per_trade_returns: pd.Series, samples: int = 1000, seed: int = 1729) -> tuple[float, float]:
    """Calendar-month block bootstrap preserving cross-sectional dependence."""
    series = per_trade_returns.dropna()
    if len(series) < 30:
        return (np.nan, np.nan)
    if isinstance(series.index, pd.MultiIndex) and "universe_month" in series.index.names:
        months = series.index.get_level_values("universe_month")
    elif series.index.name == "universe_month":
        months = series.index.to_numpy()
    else:
        raise ValueError("block bootstrap requires a universe_month index level")
    rng = np.random.default_rng(seed)
    unique_blocks = sorted(set(months))
    estimates = np.empty(samples)
    for sample in range(samples):
        chosen = rng.choice(len(unique_blocks), size=len(unique_blocks), replace=True)
        values = series.to_numpy(dtype=float)
        parts = [values[months == unique_blocks[index]] for index in chosen]
        pooled = np.concatenate(parts) if parts else np.array([])
        estimates[sample] = pooled.mean() if len(pooled) else np.nan
    alpha = 0.05 / 2
    return (float(np.nanquantile(estimates, alpha)), float(np.nanquantile(estimates, 1 - alpha)))


def evaluate_trial(
    trades: pd.DataFrame,
    *,
    periods_per_year: float,
    total_eligible_rows: int,
    holding_bars: int,
) -> dict[str, Any]:
    """Validation-primary evidence for one trial from executed trades."""
    n_trades = int(len(trades))
    result: dict[str, Any] = {
        "observations": int(total_eligible_rows),
        "signals": n_trades,  # each signal produced at most one executed trade
        "executed_trades": n_trades,
        "signal_frequency": float(n_trades / total_eligible_rows) if total_eligible_rows else np.nan,
        "exposure": float(min(1.0, n_trades * holding_bars / total_eligible_rows)) if total_eligible_rows else np.nan,
        "turnover": float(2 * n_trades),
    }
    if n_trades == 0:
        nan_keys = [
            "gross_return", "net_return", "hit_rate", "mean_net_return", "median_net_return",
            "sharpe", "sortino", "max_drawdown", "calmar", "hac_t_stat",
            "bootstrap_ci_low", "bootstrap_ci_high",
        ]
        result.update({key: np.nan for key in nan_keys})
        return result
    gross = pd.to_numeric(trades["gross_return"], errors="coerce")
    net = pd.to_numeric(trades["net_return"], errors="coerce")
    mean_net = float(net.mean())
    downside = net[net < 0]
    downside_deviation = float(math.sqrt(float(np.mean(np.minimum(net.to_numpy(dtype=float), 0.0) ** 2))))
    timeline_indexed = trades.set_index("universe_month")["net_return"]
    ci_low, ci_high = _month_block_bootstrap_ci(timeline_indexed)
    sharpe = float(np.sqrt(periods_per_year) * mean_net / net.std(ddof=0)) if net.std(ddof=0) > 0 else np.nan
    mdd = _max_drawdown(net)
    annualized = mean_net * periods_per_year
    result.update({
        "gross_return": float((1 + gross).prod() - 1),
        "net_return": float((1 + net).prod() - 1),
        "hit_rate": float((net > 0).mean()),
        "mean_net_return": mean_net,
        "median_net_return": float(net.median()),
        "sharpe": sharpe,
        "sortino": float(np.sqrt(periods_per_year) * mean_net / downside_deviation) if downside_deviation > 0 else np.nan,
        "max_drawdown": mdd,
        "calmar": float(annualized / abs(mdd)) if mdd < 0 else np.nan,
        "hac_t_stat": _hac_t_stat(net),
        "bootstrap_ci_low": ci_low,
        "bootstrap_ci_high": ci_high,
    })
    return result


def _execute_symbol(
    group: pd.DataFrame,
    trial: dict[str, Any],
    universe_top50: set[tuple[str, str, str]],
    funding_cache: dict[str, pd.DataFrame | None],
) -> tuple[pd.DataFrame, int]:
    """Execute one trial on one symbol; return (trades, eligible_rows)."""
    market, timeframe, side = trial["market"], trial["timeframe"], trial["side"]
    horizon = HORIZON_BARS_24H[timeframe]
    embargo = OPERATIONAL_EMBARGO_BARS
    fee = COSTS[market]["taker_bps"] / 10_000
    slippage_total = 2 * COSTS[market]["slippage_bps"] / 10_000
    direction_base = 1 if side == "LONG" else -1
    signal = compute_signal(group, trial["feature_id"], trial["variant"], market)
    eligible = (group["row_class"] == "RESEARCH_ELIGIBLE").to_numpy()
    months = group["universe_month"].to_numpy()
    symbols = group["symbol"].iloc[0]
    selected = {(mkt, str(month), sym) for mkt, month, sym in universe_top50}
    opens = group["open"].astype(float).to_numpy()
    stamps = pd.to_datetime(group["timestamp"], utc=True)
    records: list[dict[str, Any]] = []
    next_available = 0
    n = len(group)
    for decision in range(n):
        raw = float(signal.iloc[decision]) if np.isfinite(float(signal.iloc[decision])) else 0.0
        if raw == 0.0 or not eligible[decision] or decision < next_available:
            continue
        month_key = str(months[decision])
        if (market, month_key, str(symbols)) not in selected:
            continue
        entry_index = decision + 1 + embargo
        exit_index = entry_index + horizon - 1 + embargo
        # Exit fill is the executable open `horizon` bars after the entry open.
        exit_index = entry_index + horizon
        if exit_index >= n or not np.isfinite(opens[entry_index]) or opens[entry_index] <= 0:
            continue
        entry_price = opens[entry_index]
        exit_price = opens[exit_index]
        gross = direction_base * (exit_price / entry_price - 1)
        funding_cost = 0.0
        if market == "um":
            if symbols not in funding_cache:
                funding_cache[symbols] = _funding_events(str(symbols))
            funding_cost = _crossed_funding_cost(stamps.iloc[entry_index], stamps.iloc[exit_index], direction_base, funding_cache[symbols])
        net = gross - fee * 2 - slippage_total - funding_cost
        records.append({
            "trial_id": trial["trial_id"],
            "market": market, "timeframe": timeframe, "side": side, "symbol": str(symbols),
            "universe_month": month_key,
            "decision_time": stamps.iloc[decision].isoformat(),
            "entry_time": stamps.iloc[entry_index].isoformat(),
            "exit_time": stamps.iloc[exit_index].isoformat(),
            "gross_return": gross, "net_return": net, "funding_cost": funding_cost,
        })
        next_available = exit_index
    trades = pd.DataFrame.from_records(records)
    return trades, int(eligible.sum())


def run_single_trial(
    trial: dict[str, Any],
    panel: pd.DataFrame,
    *,
    universe_top50: set[tuple[str, str, str]],
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Execute one preregistered trial on a PRE-HOLDOUT panel (guard enforced)."""
    assert_no_holdout(panel, timeframe=trial["timeframe"], context=trial["trial_id"])
    funding_cache: dict[str, pd.DataFrame | None] = {}
    all_trades: list[pd.DataFrame] = []
    eligible_total = 0
    for symbol, group in panel.groupby("symbol", sort=True):
        trades, eligible_count = _execute_symbol(group.reset_index(drop=True), trial, universe_top50, funding_cache)
        all_trades.append(trades)
        eligible_total += eligible_count
    combined = (pd.concat(all_trades, ignore_index=True) if any(len(t) for t in all_trades) else pd.DataFrame(columns=["trial_id", "net_return"]))
    periods_per_year = {"15m": 4 * 365 * 24, "1h": 365 * 24, "4h": 6 * 365}[trial["timeframe"]]
    evidence = evaluate_trial(combined, periods_per_year=periods_per_year, total_eligible_rows=eligible_total, holding_bars=HORIZON_BARS_24H[trial["timeframe"]])
    evidence["trial_id"] = trial["trial_id"]
    return evidence, combined
