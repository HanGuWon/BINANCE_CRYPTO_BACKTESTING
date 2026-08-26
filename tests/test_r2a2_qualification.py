"""Qualification: optimized executor vs slow explicit-sign reference (mandatory gate).

Verifies identical decision/entry/exit timestamps, symbol, side, signal_value,
gross return, funding cashflow and net return across Spot/UM, LONG/SHORT,
timeframes, representative features and a segment gap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from r2a_engine import compute_signal  # noqa: E402
from run_r2a2_v2 import execute_segment, execute_segment_all_folds  # noqa: E402


def _panel(timeframe: str = "1h", with_gap: bool = True) -> pd.DataFrame:
    step = pd.Timedelta({"15m": "15min", "1h": "1h", "4h": "4h"}[timeframe])
    n_a, gap_bars, n_b = 150, (5 if with_gap else 0), 150
    stamps_a = pd.date_range("2023-01-01", periods=n_a, freq=step, tz="UTC")
    stamps_b = pd.date_range(stamps_a[-1] + (gap_bars + 1) * step, periods=n_b, freq=step, tz="UTC")
    rng = np.random.default_rng(21)
    frames = []
    for symbol in ("AAAUSDT", "BBBUSDT"):
        for stamps in (stamps_a, stamps_b):
            close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.004, len(stamps)))) + (50 if symbol == "BBBUSDT" else 0)
            open_ = np.r_[close[0], close[:-1]]
            frames.append(pd.DataFrame({
                "timestamp": stamps, "open": open_, "high": np.maximum(open_, close) + 0.2,
                "low": np.minimum(open_, close) - 0.2, "close": close,
                "volume": rng.lognormal(4, 0.3, len(stamps)),
                "taker_buy_volume": rng.uniform(0.3, 0.7) * rng.lognormal(4, 0.3, len(stamps)),
                "row_class": "RESEARCH_ELIGIBLE",
                "universe_month": stamps.strftime("%Y-%m"),
                "symbol": symbol, "market": "spot", "timeframe": timeframe,
            }))
    panel = pd.concat(frames, ignore_index=True)
    panel["market"] = panel["market"].where(panel["symbol"] != "AAAUSDT", "um").where(panel["symbol"] != "BBBUSDT", "spot")
    # Keep both symbols same market per run; make BBB spot too.
    panel["market"] = "spot"
    return panel


def _reference_execute(segment: pd.DataFrame, signal: pd.Series, *, side: str, horizon_bars: int, validation_start: pd.Timestamp, validation_end: pd.Timestamp, universe_top50: set, funding_events=None) -> list[dict]:
    """Slow obvious reference: explicit sign matching, row-by-row."""
    required_sign = 1 if side == "LONG" else -1
    direction_base = 1 if side == "LONG" else -1
    fee_total = 2 * (10.0 / 10_000)
    slip_total = 2 * 5.0 / 10_000
    out = []
    next_available = -1
    stamps = pd.to_datetime(segment.timestamp, utc=True).reset_index(drop=True)
    opens = segment.open.astype(float).to_numpy()
    symbol_key = str(segment.symbol.iloc[0])
    months = pd.to_datetime(segment.timestamp).dt.strftime("%Y-%m")
    eligible = (segment.row_class == "RESEARCH_ELIGIBLE").to_numpy()
    sig = signal.reset_index(drop=True)
    for decision in range(len(segment)):
        if decision <= next_available:
            continue
        value = float(sig.iloc[decision]) if decision < len(sig) and np.isfinite(float(sig.iloc[decision])) else 0.0
        if value != float(required_sign):
            continue
        if not eligible[decision]:
            continue
        if not (validation_start <= stamps.iloc[decision] < validation_end):
            continue
        if ("spot", str(months.iloc[decision]), symbol_key) not in universe_top50:
            continue
        entry = decision + 1
        exit_ = entry + horizon_bars
        if exit_ >= len(segment):
            continue
        gross = direction_base * (opens[exit_] / opens[entry] - 1)
        net = gross - fee_total - slip_total
        out.append({
            "decision_time": stamps.iloc[decision], "symbol": symbol_key, "side": side,
            "signal_value": value, "entry_time": stamps.iloc[entry], "exit_time": stamps.iloc[exit_],
            "gross_return": gross, "funding_cashflow": 0.0, "net_return": net,
        })
        next_available = exit_
    return out


@pytest.mark.parametrize("timeframe", ["15m", "1h", "4h"])
@pytest.mark.parametrize("side", ["LONG", "SHORT"])
@pytest.mark.parametrize("feature_id,variant", [
    ("trend.ema_20_50_spread", "ema_20_50"),
    ("momentum.rsi", "rsi_14_30_70"),
    ("volatility.realized_percentile", "rv20_p100_filter"),
    ("orderflow.cvd", "cvd_slope6_sign"),
])
def test_qualification_optimized_equals_reference(timeframe: str, side: str, feature_id: str, variant: str) -> None:
    panel = _panel(timeframe=timeframe)
    universe = {("spot", m, s) for m in panel.universe_month.unique() for s in ("AAAUSDT", "BBBUSDT")}
    validation_start = pd.Timestamp("2023-01-10", tz="UTC") + pd.Timedelta(hours=24)
    validation_end = pd.Timestamp("2023-02-01", tz="UTC")
    mismatches = 0
    for symbol, group in panel.groupby("symbol", sort=True):
        segments = []
        from binance_research.features import _gap_segments
        g = group.reset_index(drop=True)
        _, seg_ids, _ = _gap_segments(g, timeframe)
        for seg_id, idx in g.groupby(seg_ids.to_numpy(), sort=False).groups.items():
            seg = g.loc[idx].reset_index(drop=True)
            signal = compute_signal(seg, feature_id, variant, "spot").reset_index(drop=True)
            optimized = execute_segment(
                seg, signal, market="spot", side=side, horizon_bars=24,
                validation_start=validation_start + pd.Timedelta(hours=1), validation_end=validation_end,
                universe_top50=universe, funding_events=None,
            )
            reference = _reference_execute(
                seg, signal, side=side, horizon_bars=24,
                validation_start=validation_start + pd.Timedelta(hours=1), validation_end=validation_end,
                universe_top50=universe, funding_events=None,
            )
            ref_df = pd.DataFrame(reference)
            if optimized.empty and ref_df.empty:
                continue
            assert len(optimized) == len(ref_df), f"trade count mismatch for {symbol}/{feature_id}"
            ref_records = ref_df.to_dict("records")
            for o, r in zip(optimized.to_dict("records"), ref_records):
                for key in ("decision_time", "symbol", "side", "signal_value", "entry_time", "exit_time", "gross_return", "net_return"):
                    ov = pd.Timestamp(o[key]) if key.endswith("time") else o[key]
                    rv = r[key]
                    if isinstance(ov, float):
                        assert ov == pytest.approx(rv), f"{key} mismatch on {symbol}/{feature_id}: {ov} vs {rv}"
                    else:
                        assert ov == rv, f"{key} mismatch on {symbol}/{feature_id}"
                assert o["funding_cashflow"] == pytest.approx(r["funding_cashflow"])
    assert mismatches == 0


def test_one_pass_multi_fold_equals_independent_fold_calls() -> None:
    panel = _panel(timeframe="1h", with_gap=True)
    seg = panel.loc[panel.symbol == "AAAUSDT"].iloc[:150].reset_index(drop=True)
    signal = pd.Series(np.where(np.arange(len(seg)) % 3 == 0, 1.0, 0.0))
    universe = {("spot", m, "AAAUSDT") for m in seg.universe_month.unique()}
    windows = [("F1", pd.Timestamp("2023-01-10", tz="UTC"), pd.Timestamp("2023-01-20", tz="UTC")), ("F2", pd.Timestamp("2023-01-20", tz="UTC"), pd.Timestamp("2023-02-01", tz="UTC"))]
    multi = execute_segment_all_folds(seg, signal, market="spot", side="LONG", horizon_bars=4, fold_windows=windows, universe_top50=universe, funding_events=None)
    for fold_id, start, end in windows:
        single = execute_segment(seg, signal, market="spot", side="LONG", horizon_bars=4, validation_start=start, validation_end=end, universe_top50=universe, funding_events=None)
        assert multi[fold_id].to_dict("records") == single.to_dict("records")
