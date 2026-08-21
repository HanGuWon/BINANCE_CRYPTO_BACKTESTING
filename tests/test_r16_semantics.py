from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from binance_research.census import asset_taxonomy_table
from binance_research.derivatives import (
    backward_asof_event_feature,
    crossed_funding_events,
    funding_event_zscore,
    validate_metrics_schema,
)
from binance_research.features import build_cohort_aware_breadth, compute_gap_safe_features, CoreFeatureEngine
from binance_research.panel import select_verified_causal_liquidity_universe
from binance_research.provenance import append_archive_revision
from binance_research.splits import global_calendar_split, horizon_purge_bars
from binance_research.timeframes import compare_native_to_resampled


def test_gap_segments_persist_and_reset_all_feature_families(bars: pd.DataFrame) -> None:
    bars = bars.copy()
    bars.loc[250:, "open_time"] += pd.Timedelta(hours=3)
    bars.loc[250:, "close_time"] += pd.Timedelta(hours=3)
    output = compute_gap_safe_features(CoreFeatureEngine(), bars, "1h")
    assert output.loc[249, "segment_id"] == 0
    assert output.loc[250, "segment_id"] == 1
    assert output.loc[250, "gap_size_bars"] == 3
    assert output.loc[250, ["ema50_200_spread", "rsi14", "atr14", "roc24", "realized_vol_percentile100"]].isna().all()
    assert output.loc[250, "cvd"] == bars.loc[250, "taker_buy_volume"] - (bars.loc[250, "volume"] - bars.loc[250, "taker_buy_volume"])


def test_asset_taxonomy_excludes_stable_fiat_and_retains_diagnostic() -> None:
    table = asset_taxonomy_table(
        [("spot", "USDCUSDT"), ("spot", "AEURUSDT"), ("spot", "BTCUSDT"), ("um", "BTCUSDT"), ("um", "BTCUSDT_240329")],
        funding_verified_symbols={"BTCUSDT"},
    )
    assert table.loc[table.symbol == "USDCUSDT", "classification"].item() == "STABLECOIN"
    assert table.loc[table.symbol == "AEURUSDT", "classification"].item() == "FIAT_OR_TOKENIZED_FIAT"
    assert bool(table.loc[table.symbol == "BTCUSDT", "primary_crypto_eligible"].iloc[0])
    assert table.loc[table.symbol == "BTCUSDT_240329", "classification"].item() == "DATED_DELIVERY"
    assert table["all_tradable_usdt_diagnostic"].all()


def test_funding_event_crossing_and_event_unit_zscore() -> None:
    events = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=100, freq="8h", tz="UTC"), "funding_rate": np.linspace(-.001, .001, 100)})
    scored = funding_event_zscore(events)
    assert scored["funding_zscore"].iloc[:89].isna().all()
    positions = pd.DataFrame({"entry_timestamp": [events.timestamp.iloc[0]], "exit_timestamp": [events.timestamp.iloc[3]], "side": [1]})
    crossed = crossed_funding_events(positions, events)
    assert crossed.loc[0, "crossed_event_count"] == 3
    assert crossed.loc[0, "funding_cashflow_return"] == -(events.funding_rate.iloc[1:4].sum())
    bars = pd.DataFrame({"timestamp": [events.timestamp.iloc[90] + pd.Timedelta(minutes=1)]})
    joined = backward_asof_event_feature(bars, scored)
    assert joined.loc[0, "funding_zscore"] == scored.loc[90, "funding_zscore"]


def test_metrics_schema_is_not_open_interest_equivalence() -> None:
    result = validate_metrics_schema(pd.DataFrame(columns=["create_time", "sum_open_interest", "sum_open_interest_value"]))
    assert result["schema_status"] == "MISSING_REQUIRED_FIELDS"
    assert result["economic_equivalence_to_openInterestHist"] is False


def test_cohort_breadth_denominator_excludes_unselected_and_warmup() -> None:
    times = pd.date_range("2024-01-01", periods=55, freq="h", tz="UTC")
    panel = pd.concat([
        pd.DataFrame({"timestamp": times, "market": "spot", "symbol": symbol, "close": np.arange(55, dtype=float) + offset})
        for symbol, offset in [("A", 0), ("B", 1), ("C", -1)]
    ], ignore_index=True)
    cohorts = pd.DataFrame({"market": ["spot", "spot"], "universe_month": ["2024-01", "2024-01"], "symbol": ["A", "B"], "selected_top50": [True, True]})
    result = build_cohort_aware_breadth(panel, cohorts, timeframe="1h", minimum_valid_fraction=0.5)
    assert result["selected_count"].max() == 2
    assert "valid_fraction" in result
    assert "coverage_status" in result


def test_global_calendar_split_and_24h_purge() -> None:
    frame = pd.DataFrame({"timestamp": pd.date_range("2023-12-31", periods=300, freq="15min", tz="UTC")})
    split = global_calendar_split(frame, train_end="2024-01-02", validation_end="2024-01-03", timeframe="15m")
    assert horizon_purge_bars("15m") == 96
    assert split.purge_bars["target_horizon"] == 96
    assert split.train.timestamp.max() < pd.Timestamp("2024-01-01", tz="UTC")


def test_archive_revision_registry_is_append_only(tmp_path: Path) -> None:
    destination = tmp_path / "archive_revisions.csv"
    revision = {"archive_url": "u", "old_sha256": "a", "new_sha256": "b", "old_last_modified": "1", "new_last_modified": "2", "detected_at": "3", "revision_status": "DETECTED_VALID_REVISION", "campaigns_using_old_revision": "r1", "campaigns_using_new_revision": "r16"}
    append_archive_revision(destination, revision)
    append_archive_revision(destination, revision)
    assert len(pd.read_csv(destination)) == 1


def test_native_timeframe_comparison_matches_exact_aggregation() -> None:
    times = pd.date_range("2024-01-01", periods=16, freq="15min", tz="UTC")
    source = pd.DataFrame({"open_time": times, "open": 1., "high": 2., "low": 0., "close": 1., "volume": 1., "quote_volume": 1., "trade_count": 1, "taker_buy_volume": .5, "taker_buy_quote_volume": .5, "close_time": times + pd.Timedelta(minutes=15) - pd.Timedelta(milliseconds=1)})
    native = source.iloc[::4].copy().reset_index(drop=True)
    native["open_time"] = times[::4]
    native["close_time"] = times[::4] + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1)
    native["volume"] = 4
    native["quote_volume"] = 4
    native["trade_count"] = 4
    native["taker_buy_volume"] = 2
    native["taker_buy_quote_volume"] = 2
    result = compare_native_to_resampled(source, native, target="1h")
    assert result["status"].eq("MATCH").all()


def test_partial_prior_month_is_excluded_and_future_month_cannot_rewrite_membership() -> None:
    frame = pd.DataFrame(
        {
            "market": ["spot", "spot", "spot"],
            "universe_month": ["2024-03-01"] * 3,
            "volume_month": ["2024-02-01"] * 3,
            "symbol": ["A", "B", "C"],
            "first_observed": ["2023-01-01T00:00:00Z"] * 3,
            "prior_month_expected_days": [29] * 3,
            "prior_month_observed_days": [29, 28, 29],
            "coverage_ratio": [1.0, 28 / 29, 1.0],
            "prior_month_quote_volume": [100.0, 1000.0, 50.0],
        }
    )
    result = select_verified_causal_liquidity_universe(frame, top_n=2)
    assert set(result.loc[result.selected_top50, "symbol"]) == {"A", "C"}
    revised = frame.copy()
    revised.loc[0, "prior_month_quote_volume"] = 1.0
    revised.loc[1, "prior_month_quote_volume"] = 999999.0
    assert set(select_verified_causal_liquidity_universe(revised, top_n=2).loc[lambda x: x.selected_top50, "symbol"]) == {"A", "C"}
