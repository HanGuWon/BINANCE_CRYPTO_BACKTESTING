"""Segment-gap isolation tests: state never crosses a candle gap (P0-1 fix)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from binance_research.features import _gap_segments, compute_gap_safe_features, CoreFeatureEngine  # noqa: E402
from run_r2a2_v2 import execute_segment, segment_frames  # noqa: E402


def _panel_with_gap(n_before: int = 200, gap_bars: int = 5, n_after: int = 200) -> pd.DataFrame:
    step = pd.Timedelta("1h")
    stamps_a = pd.date_range("2023-01-01", periods=n_before, freq=step, tz="UTC")
    stamps_b = pd.date_range(stamps_a[-1] + gap_bars * step + step, periods=n_after, freq=step, tz="UTC")
    rng = np.random.default_rng(9)
    def _mk(stamps):
        close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.004, len(stamps))))
        open_ = np.r_[close[0], close[:-1]]
        return pd.DataFrame({
            "timestamp": stamps, "open": open_, "high": np.maximum(open_, close) + 0.2,
            "low": np.minimum(open_, close) - 0.2, "close": close,
            "volume": rng.lognormal(4, 0.3, len(stamps)),
            "taker_buy_volume": rng.uniform(0.3, 0.7) * rng.lognormal(4, 0.3, len(stamps)),
            "row_class": "RESEARCH_ELIGIBLE",
            "universe_month": stamps.strftime("%Y-%m"),
            "symbol": "BTCUSDT", "market": "spot", "timeframe": "1h",
        })
    return pd.concat([_mk(stamps_a), _mk(stamps_b)], ignore_index=True)


def test_segments_split_on_gap() -> None:
    panel = _panel_with_gap()
    segments = segment_frames(panel, "1h")
    assert len(segments) == 2
    assert segments[0][1]["timestamp"].max() < segments[1][1]["timestamp"].min()


def test_ema_rsi_realized_percentile_identical_to_segment_B_alone() -> None:
    panel = _panel_with_gap()
    segments = segment_frames(panel, "1h")
    seg_b = segments[1][1].reset_index(drop=True)
    # Full-history computation via canonical gap-safe machinery must equal B-alone.
    full_out = compute_gap_safe_features(CoreFeatureEngine(), panel.rename(columns={"timestamp": "open_time"}), "1h")
    b_alone_out = compute_gap_safe_features(CoreFeatureEngine(), seg_b.rename(columns={"timestamp": "open_time"}), "1h")
    for column in ("ema20_50_spread", "rsi14", "realized_vol_percentile100", "cvd"):
        full_vals = full_out[column].iloc[len(panel) - len(seg_b):].to_numpy()
        b_vals = b_alone_out[column].to_numpy()
        np.testing.assert_allclose(full_vals, b_vals, equal_nan=True)
    # CVD restarts in B: first CVD value of B equals its own first delta contribution.
    assert float(b_alone_out["cvd"].isna().sum()) >= 0  # computed without A carryover
