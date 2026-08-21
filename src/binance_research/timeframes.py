"""Native-vs-resampled timeframe quality comparisons."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data import INTERVAL_MS, resample_klines


COMPARE_COLUMNS = ("open", "high", "low", "close", "volume", "quote_volume", "trade_count", "taker_buy_volume", "taker_buy_quote_volume")


def compare_native_to_resampled(
    source_15m: pd.DataFrame,
    native: pd.DataFrame,
    *,
    target: str,
) -> pd.DataFrame:
    """Compare completed native bars to exact 15m aggregation by timestamp."""
    if target not in {"1h", "4h"}:
        raise ValueError("target must be 1h or 4h")
    source = source_15m.copy()
    actual = native.copy()
    for frame in (source, actual):
        if "open_time" not in frame:
            raise ValueError("timeframe comparison requires open_time")
        frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
    expected = resample_klines(source.sort_values("open_time"), "1h" if target == "1h" else "4h")
    left = expected.set_index("open_time")
    right = actual.set_index("open_time")
    common = left.index.intersection(right.index)
    rows: list[dict[str, object]] = []
    for column in COMPARE_COLUMNS:
        if column not in left or column not in right:
            rows.append({"target": target, "field": column, "status": "MISSING_FIELD", "common_rows": len(common), "mismatch_count": None, "max_abs_diff": None})
            continue
        a = pd.to_numeric(left.loc[common, column], errors="coerce")
        b = pd.to_numeric(right.loc[common, column], errors="coerce")
        tolerance = 0.0 if column == "trade_count" else 1e-6
        difference = (a - b).abs()
        mismatch = ~pd.Series(np.isclose(a.to_numpy(), b.to_numpy(), rtol=1e-9, atol=tolerance), index=common)
        rows.append({"target": target, "field": column, "status": "MATCH" if not mismatch.any() else "MISMATCH", "common_rows": len(common), "mismatch_count": int(mismatch.sum()), "max_abs_diff": float(difference.max()) if len(difference) else None})
    return pd.DataFrame(rows)


def freeze_timeframe_source_policy(comparisons: pd.DataFrame) -> dict[str, str]:
    """Choose a source using integrity/coverage, never return performance."""
    policy = {"15m": "NATIVE_15M"}
    for timeframe in ("1h", "4h"):
        subset = comparisons[comparisons["target"] == timeframe]
        mismatch = subset["status"].eq("MISMATCH").any() if len(subset) else True
        missing = subset["status"].eq("MISSING_FIELD").any() if len(subset) else True
        policy[timeframe] = "NATIVE_" + timeframe.upper() if not mismatch and not missing else "RESAMPLED_FROM_15M_GAP_SAFE"
    return policy
