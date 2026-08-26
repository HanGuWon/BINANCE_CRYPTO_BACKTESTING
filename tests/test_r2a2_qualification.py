"""Strict qualification of the optimized executor against a slow reference.

The matrix is derived from the committed 756-trial registry rather than a
hand-picked Spot-only subset. Every registered timeframe/horizon/feature
combination is exercised for Spot LONG and UM LONG/SHORT. UM cases use
event-time funding with alternating positive and negative rates.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from binance_research.features import _gap_segments  # noqa: E402
from r2a_engine import compute_signal  # noqa: E402
from run_r2a2_v2 import execute_segment, execute_segment_all_folds  # noqa: E402

FIELDS = ("decision_time", "signal_value", "symbol", "side", "entry_time", "exit_time", "gross_return", "funding_cashflow", "net_return")
STEP = {"15m": pd.Timedelta("15min"), "1h": pd.Timedelta("1h"), "4h": pd.Timedelta("4h")}
COSTS = {"spot": (2 * 10.0 / 10_000, 2 * 5.0 / 10_000), "um": (2 * 5.0 / 10_000, 2 * 5.0 / 10_000)}


def _panel(market: str, timeframe: str, *, with_gap: bool = True) -> pd.DataFrame:
    step = STEP[timeframe]
    n_a, gap_bars, n_b = 260, (7 if with_gap else 0), 260
    stamps_a = pd.date_range("2023-01-01", periods=n_a, freq=step, tz="UTC")
    stamps_b = pd.date_range(stamps_a[-1] + (gap_bars + 1) * step, periods=n_b, freq=step, tz="UTC")
    rows: list[pd.DataFrame] = []
    for symbol_index, symbol in enumerate(("AAAUSDT", "BBBUSDT")):
        rng = np.random.default_rng(21 + symbol_index)
        stamps = stamps_a.append(stamps_b)
        close = 100 * np.exp(np.cumsum(rng.normal(0.0004 if symbol_index == 0 else -0.0002, 0.012, len(stamps))))
        close *= 1 + 0.04 * np.sin(np.arange(len(stamps)) / 9.0)
        open_ = np.r_[close[0], close[:-1]]
        volume = rng.lognormal(5.0, 0.35, len(stamps))
        funding_rate = np.where(np.arange(len(stamps)) % 4 < 2, 0.001, -0.0015)
        funding_zscore = np.where(np.arange(len(stamps)) % 6 < 3, 4.0, -4.0)
        rows.append(pd.DataFrame({
            "timestamp": stamps, "open": open_, "high": np.maximum(open_, close) + 0.3,
            "low": np.minimum(open_, close) - 0.3, "close": close, "volume": volume,
            "taker_buy_volume": volume * np.where(np.arange(len(stamps)) % 2, 0.35, 0.65),
            "funding_rate": funding_rate, "funding_zscore90": funding_zscore,
            "btc_regime": np.where(np.arange(len(stamps)) % 2, -1.0, 1.0),
            "market_breadth": np.where(np.arange(len(stamps)) % 2, 0.3, 0.7),
            "row_class": "RESEARCH_ELIGIBLE", "universe_month": stamps.strftime("%Y-%m"),
            "symbol": symbol, "market": market, "timeframe": timeframe,
        }))
    return pd.concat(rows, ignore_index=True)


def _funding_events(panel: pd.DataFrame) -> pd.DataFrame:
    stamps = pd.to_datetime(panel.timestamp, utc=True)
    events = pd.date_range(stamps.min() - pd.Timedelta("8h"), stamps.max() + pd.Timedelta("8h"), freq="8h", tz="UTC")
    return pd.DataFrame({"timestamp": events, "funding_rate": np.where(np.arange(len(events)) % 2, -0.0015, 0.001)})


def _reference_execute(segment: pd.DataFrame, signal: pd.Series, *, market: str, side: str, horizon_bars: int, validation_start: pd.Timestamp, validation_end: pd.Timestamp, universe_top50: set[tuple[str, str, str]], funding_events: pd.DataFrame | None) -> list[dict[str, object]]:
    """Intentionally slow row-by-row reference with explicit sign matching."""
    required_sign = 1.0 if side == "LONG" else -1.0
    direction = 1.0 if side == "LONG" else -1.0
    fee_total, slip_total = COSTS[market]
    group = segment.reset_index(drop=True)
    stamps = pd.to_datetime(group.timestamp, utc=True).reset_index(drop=True)
    opens = group.open.astype(float).to_numpy()
    eligible = group.row_class.eq("RESEARCH_ELIGIBLE").to_numpy()
    months = group.universe_month.astype(str).to_numpy()
    symbol = str(group.symbol.iloc[0])
    raw = signal.reset_index(drop=True).astype(float)
    next_available = -1
    records: list[dict[str, object]] = []
    for decision in range(len(group)):
        value = float(raw.iloc[decision]) if np.isfinite(raw.iloc[decision]) else 0.0
        if value != required_sign or decision <= next_available or not eligible[decision]:
            continue
        if not (validation_start <= stamps.iloc[decision] < validation_end) or (market, months[decision], symbol) not in universe_top50:
            continue
        entry, exit_ = decision + 1, decision + 1 + horizon_bars
        if exit_ >= len(group) or not np.isfinite(opens[entry]) or opens[entry] <= 0:
            continue
        gross = direction * (opens[exit_] / opens[entry] - 1.0)
        funding = 0.0
        if market == "um" and funding_events is not None:
            crossed = funding_events[(funding_events.timestamp > stamps.iloc[entry]) & (funding_events.timestamp <= stamps.iloc[exit_])]
            funding = -direction * float(crossed.funding_rate.sum())
        net = gross - fee_total - slip_total + funding
        records.append({"decision_time": stamps.iloc[decision], "signal_value": value, "symbol": symbol, "side": side, "entry_time": stamps.iloc[entry], "exit_time": stamps.iloc[exit_], "gross_return": gross, "funding_cashflow": funding, "net_return": net})
        next_available = exit_
    return records


def _assert_equal(optimized: pd.DataFrame, reference: list[dict[str, object]], label: str) -> None:
    assert len(optimized) == len(reference), f"trade count mismatch: {label}"
    for index, (actual, expected) in enumerate(zip(optimized.to_dict("records"), reference)):
        for field in FIELDS:
            av, ev = actual[field], expected[field]
            if field.endswith("_time"):
                assert pd.Timestamp(av) == pd.Timestamp(ev), f"{label} row {index} {field}"
            elif field in {"gross_return", "funding_cashflow", "net_return", "signal_value"}:
                assert float(av) == float(ev), f"{label} row {index} {field}: {av} != {ev}"
            else:
                assert av == ev, f"{label} row {index} {field}: {av} != {ev}"


def test_registered_matrix_qualification() -> None:
    registry = pd.read_csv(ROOT / "campaigns" / "r2a2_temporal_horizon_v1" / "trial_registry.csv")
    assert len(registry) == 756
    assert set(registry.timeframe) == {"15m", "1h", "4h"}
    assert set(registry.loc[registry.market == "spot", "side"]) == {"LONG"}
    assert set(registry.loc[registry.market == "um", "side"]) == {"LONG", "SHORT"}
    assert {"derivatives.funding", "derivatives.funding_zscore"}.issubset(set(registry.feature_id))
    for timeframe, group in registry.groupby("timeframe"):
        assert set(group.horizon_bars.astype(int)) == set(registry.loc[registry.timeframe == timeframe, "horizon_bars"].astype(int))

    observed_funding_cashflows: list[float] = []
    for market in ("spot", "um"):
        for timeframe in ("15m", "1h", "4h"):
            panel = _panel(market, timeframe, with_gap=True)
            universe = {(market, month, symbol) for month in panel.universe_month.unique() for symbol in panel.symbol.unique()}
            funding = _funding_events(panel) if market == "um" else None
            start = pd.to_datetime(panel.timestamp, utc=True).min() + STEP[timeframe]
            end = pd.to_datetime(panel.timestamp, utc=True).max() + STEP[timeframe]
            subset = registry[(registry.market == market) & (registry.timeframe == timeframe)]
            seen_gap = False
            signal_cache: dict[tuple[str, str, str, str], pd.Series] = {}
            for symbol, symbol_frame in panel.groupby("symbol", sort=True):
                group = symbol_frame.reset_index(drop=True)
                _, segment_ids, _ = _gap_segments(group, timeframe)
                segments = list(group.groupby(segment_ids.to_numpy(), sort=False))
                seen_gap |= len(segments) > 1
                for segment_id, segment_rows in segments:
                    segment = segment_rows.reset_index(drop=True)
                    for trial in subset.itertuples(index=False):
                        cache_key = (str(segment_id), trial.feature_id, trial.variant, market)
                        if cache_key not in signal_cache:
                            signal_cache[cache_key] = compute_signal(segment, trial.feature_id, trial.variant, market).reset_index(drop=True)
                        signal = signal_cache[cache_key]
                        actual = execute_segment(segment, signal, market=market, side=trial.side, horizon_bars=int(trial.horizon_bars), validation_start=start, validation_end=end, universe_top50=universe, funding_events=funding)
                        expected = _reference_execute(segment, signal, market=market, side=trial.side, horizon_bars=int(trial.horizon_bars), validation_start=start, validation_end=end, universe_top50=universe, funding_events=funding)
                        _assert_equal(actual, expected, f"{market}/{timeframe}/{symbol}/{segment_id}/{trial.trial_id}")
                        if market == "um" and not actual.empty:
                            observed_funding_cashflows.extend(actual.funding_cashflow.astype(float).tolist())
            assert seen_gap, f"gap segment was not exercised for {market}/{timeframe}"

    funding_rows = registry[(registry.market == "um") & registry.feature_id.isin(["derivatives.funding", "derivatives.funding_zscore"])]
    assert len(funding_rows) > 0
    event_rates = _funding_events(_panel("um", "1h"))["funding_rate"]
    assert event_rates.min() < 0 < event_rates.max(), "synthetic funding must contain both signs"
    assert any(abs(value) > 0 for value in observed_funding_cashflows), "UM qualification did not cross a funding event"


def test_one_pass_multi_fold_equals_independent_fold_calls() -> None:
    panel = _panel("spot", "1h", with_gap=True)
    segment = panel.loc[panel.symbol == "AAAUSDT"].iloc[:260].reset_index(drop=True)
    signal = pd.Series(np.where(np.arange(len(segment)) % 3 == 0, 1.0, 0.0))
    universe = {("spot", month, "AAAUSDT") for month in segment.universe_month.unique()}
    windows = [("F1", pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2023-01-08", tz="UTC")), ("F2", pd.Timestamp("2023-01-08", tz="UTC"), pd.Timestamp("2023-01-20", tz="UTC"))]
    multi = execute_segment_all_folds(segment, signal, market="spot", side="LONG", horizon_bars=4, fold_windows=windows, universe_top50=universe, funding_events=None)
    for fold_id, start, end in windows:
        single = execute_segment(segment, signal, market="spot", side="LONG", horizon_bars=4, validation_start=start, validation_end=end, universe_top50=universe, funding_events=None)
        pd.testing.assert_frame_equal(multi[fold_id].reset_index(drop=True), single.reset_index(drop=True), check_exact=True)
