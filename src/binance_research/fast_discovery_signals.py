"""Outcome-blind S0 primitive semantics for Fast Discovery V2."""
from __future__ import annotations

import numpy as np
import pandas as pd

S0_SIGNAL_SEMANTICS: dict[str, dict[str, object]] = {
    "donchian_breakout20": {"kind": "directional", "equation": "+1 if close > prior_high20; -1 if close < prior_low20; 0 otherwise; NaN during warmup", "polarity": "continuation"},
    "roc6": {"kind": "directional", "equation": "sign(roc6); zero remains 0; NaN remains NaN", "polarity": "continuation"},
    "vwap_deviation20": {"kind": "directional", "equation": "-sign(vwap_deviation20); zero remains 0; NaN remains NaN", "polarity": "reversion"},
    "taker_buy_sell_ratio": {"kind": "directional", "equation": "sign(taker_buy_sell_ratio - 1); zero remains 0; NaN remains NaN", "polarity": "buy-pressure"},
    "cvd_slope6": {"kind": "directional", "equation": "sign(cvd_slope6); zero remains 0; NaN remains NaN", "polarity": "continuation"},
    "rvol20": {"kind": "continuous", "equation": "rvol20 unchanged", "polarity": "none"},
    "bb_bandwidth20": {"kind": "continuous", "equation": "bb_bandwidth20 unchanged", "polarity": "none"},
    "premium": {"kind": "continuous", "equation": "premium unchanged; no polarity selected in S0", "polarity": "none"},
    "premium_zscore90": {"kind": "continuous", "equation": "premium_zscore90 unchanged; no threshold or polarity selected in S0", "polarity": "none"},
}


def _signed(values: pd.Series, *, reverse: bool = False) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    signed = np.sign(numeric)
    if reverse:
        signed = -signed
    result = pd.Series(signed, index=values.index, dtype="float64")
    result.loc[numeric.isna()] = np.nan
    return result


def apply_s0_signal_semantics(frame: pd.DataFrame, *, primitives: tuple[str, ...] | list[str] | None = None) -> pd.DataFrame:
    """Add deterministic ``sig_<primitive>`` columns without using outcomes."""
    requested = tuple(primitives or S0_SIGNAL_SEMANTICS)
    unknown = sorted(set(requested) - set(S0_SIGNAL_SEMANTICS))
    if unknown:
        raise ValueError(f"unknown S0 primitive semantics: {', '.join(unknown)}")
    result = frame.copy()
    for feature_id in requested:
        if feature_id not in result.columns:
            raise ValueError(f"frame missing S0 primitive: {feature_id}")
        spec = S0_SIGNAL_SEMANTICS[feature_id]
        if spec["kind"] == "continuous":
            result[f"sig_{feature_id}"] = pd.to_numeric(result[feature_id], errors="coerce")
        elif feature_id == "vwap_deviation20":
            result[f"sig_{feature_id}"] = _signed(result[feature_id], reverse=True)
        elif feature_id == "taker_buy_sell_ratio":
            result[f"sig_{feature_id}"] = _signed(pd.to_numeric(result[feature_id], errors="coerce") - 1.0)
        else:
            result[f"sig_{feature_id}"] = _signed(result[feature_id])
    result.attrs["signal_semantics_version"] = "FAST_DISCOVERY_S0_V2"
    result.attrs["holdout_status"] = "UNTOUCHED"
    return result

