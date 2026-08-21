from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RegimeThresholds:
    volatility: tuple[float, float, float]
    liquidity: tuple[float, float]


def fit_regime_thresholds(training: pd.DataFrame) -> RegimeThresholds:
    required = {"realized_vol20", "quote_volume"}
    if missing := required - set(training.columns):
        raise ValueError(f"missing regime columns: {', '.join(sorted(missing))}")
    volatility = training["realized_vol20"].dropna()
    liquidity = training["quote_volume"].dropna()
    if len(volatility) < 20 or len(liquidity) < 20:
        raise ValueError("insufficient training observations for regime thresholds")
    return RegimeThresholds(
        tuple(float(value) for value in volatility.quantile([0.25, 0.75, 0.95])),
        tuple(float(value) for value in liquidity.quantile([1 / 3, 2 / 3])),
    )


def classify_regimes(frame: pd.DataFrame, thresholds: RegimeThresholds) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    btc = pd.to_numeric(frame.get("btc_regime", pd.Series(np.nan, index=frame.index)), errors="coerce")
    result["btc_trend_regime"] = btc.map({1.0: "bull", 0.0: "neutral", -1.0: "bear"}).fillna("unavailable")
    volatility = pd.to_numeric(frame["realized_vol20"], errors="coerce")
    v_low, v_high, v_panic = thresholds.volatility
    result["volatility_regime"] = np.select(
        [volatility <= v_low, volatility <= v_high, volatility <= v_panic, volatility > v_panic],
        ["low", "normal", "high", "panic_extreme"],
        default="unavailable",
    )
    quote_volume = pd.to_numeric(frame["quote_volume"], errors="coerce")
    l_low, l_high = thresholds.liquidity
    result["liquidity_bucket"] = np.select(
        [quote_volume <= l_low, quote_volume <= l_high, quote_volume > l_high],
        ["low", "medium", "high"],
        default="unavailable",
    )
    breadth = pd.to_numeric(frame.get("market_breadth", pd.Series(np.nan, index=frame.index)), errors="coerce")
    result["breadth_regime"] = np.select(
        [breadth >= 0.60, breadth <= 0.40, breadth.notna()],
        ["broad_bullish", "broad_bearish", "mixed"],
        default="unavailable",
    )
    oi_change = pd.to_numeric(frame.get("oi_pct_change", pd.Series(np.nan, index=frame.index)), errors="coerce")
    result["open_interest_regime"] = np.select(
        [oi_change > 0, oi_change < 0, oi_change.notna()],
        ["rising", "falling", "flat"], default="unavailable",
    )
    funding = pd.to_numeric(frame.get("funding_zscore90", pd.Series(np.nan, index=frame.index)), errors="coerce")
    result["funding_regime"] = np.select(
        [funding >= 1, funding <= -1, funding.notna()],
        ["positive_extreme", "negative_extreme", "normal"], default="unavailable",
    )
    return result
