"""R1.7.1 regression gates: corrected coverage audit and split metadata."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from binance_research.audit import (  # noqa: E402
    CLASSIFICATION_FORWARD_SHADOW,
    CLASSIFICATION_R2A_PRIMARY,
    audit_feature_coverage,
    candidate_columns,
    classify_structural_coverage,
    registered_feature_ids,
)

CAMPAIGN = Path(__file__).resolve().parents[1] / "campaigns" / "r1_final_panel_v1"


def _panel(tmp_path: Path) -> Path:
    rows = []
    base = pd.Timestamp("2024-01-01", tz="UTC")
    for index in range(10):
        stamp = base + pd.Timedelta(hours=index)
        # First two rows are WARMUP_CONTEXT_ONLY; the rest are research.
        row_class = "WARMUP_CONTEXT_ONLY" if index < 2 else "RESEARCH_ELIGIBLE"
        rows.append({
            "timestamp": stamp,
            "row_class": row_class,
            "ema20_50_spread": 0.01 if index >= 3 else None,
            "rsi14": 55.0 if index >= 2 else None,
            # funding_rate is finite even for a warmup row: it must NOT count.
            "funding_rate": 0.0001 if index != 5 else None,
        })
    frame = pd.DataFrame(rows)
    destination = tmp_path / "market=um" / "symbol=BTCUSDT" / "timeframe=1h" / "year=2024"
    destination.mkdir(parents=True)
    frame.to_parquet(destination / "part-000.parquet", index=False)
    return tmp_path


def test_finite_rows_never_exceed_research_eligible_rows(tmp_path: Path) -> None:
    result = audit_feature_coverage(_panel(tmp_path), markets=("um",), timeframes=("1h",))
    assert (result["finite_rows"] <= result["research_eligible_rows"]).all()
    eligible = result.loc[result.feature == "trend.ema_20_50_spread", "research_eligible_rows"].iloc[0]
    finite = result.loc[result.feature == "trend.ema_20_50_spread", "finite_rows"].iloc[0]
    assert eligible == 8
    assert finite == 7  # warmup rows excluded; first eligible row NaN.


def test_features_are_audited_independently(tmp_path: Path) -> None:
    result = audit_feature_coverage(_panel(tmp_path), markets=("um",), timeframes=("1h",))
    spread = result.loc[result.feature == "trend.ema_20_50_spread"].iloc[0]
    rsi = result.loc[result.feature == "momentum.rsi"].iloc[0]
    funding = result.loc[result.feature == "derivatives.funding"].iloc[0]
    assert int(funding["finite_rows"]) == 7  # independent of ema/rsi counts.
    assert set(result["feature"]) <= set(registered_feature_ids())
    assert spread["feature"] == "trend.ema_20_50_spread" and rsi["feature"] == "momentum.rsi"


def test_first_and_last_finite_timestamps_are_populated(tmp_path: Path) -> None:
    result = audit_feature_coverage(_panel(tmp_path), markets=("um",), timeframes=("1h",))
    rsi = result.loc[result.feature == "momentum.rsi"].iloc[0]
    assert rsi["first_finite_timestamp"] == "2024-01-01T02:00:00+00:00"
    assert rsi["last_finite_timestamp"] == "2024-01-01T09:00:00+00:00"


def test_missing_timeframe_yields_no_rows_and_shadow_classification(tmp_path: Path) -> None:
    um_result = audit_feature_coverage(_panel(tmp_path), markets=("um",), timeframes=("15m",))
    assert (um_result["finite_rows"] == 0).all()
    # With no eligible rows the denominator is zero, so NOT_APPLICABLE is
    # expected for every feature; FORWARD_SHADOW is used when there ARE
    # eligible rows but none finite.
    assert (um_result["classification"] == "NOT_APPLICABLE").all()
    assert classify_structural_coverage(0, float("nan")) == CLASSIFICATION_FORWARD_SHADOW


def test_classification_from_structure_not_performance() -> None:
    assert classify_structural_coverage(100, 0.9) == CLASSIFICATION_R2A_PRIMARY
    assert classify_structural_coverage(100, 0.5) == "R2B_RESTRICTED"


def test_um_derivatives_not_applicable_to_spot() -> None:
    assert candidate_columns("derivatives.funding", "spot") == ()
    assert candidate_columns("derivatives.funding", "um") == ("funding_rate",)


@pytest.mark.parametrize("timeframe,step,purge", [("15m", "15min", 96), ("1h", "1h", 24), ("4h", "4h", 6)])
def test_split_metadata_matches_global_calendar_split(timeframe: str, step: str, purge: int) -> None:
    from binance_research.splits import global_calendar_split
    from regenerate_r171_verification import split_metadata_frame

    metadata = split_metadata_frame()
    row = metadata.loc[metadata.timeframe == timeframe].iloc[0]
    step_delta = pd.Timedelta(step)
    train_boundary = pd.Timestamp(row.train_boundary_utc)
    validation_boundary = pd.Timestamp(row.validation_boundary_utc)
    frame = pd.DataFrame({
        "timestamp": pd.date_range(train_boundary - 200 * step_delta, validation_boundary + 200 * step_delta, freq=step_delta, tz="UTC"),
    })
    split = global_calendar_split(
        frame,
        train_end=train_boundary.isoformat(),
        validation_end=validation_boundary.isoformat(),
        timeframe=timeframe,
        operational_embargo_bars=int(row.operational_embargo_bars),
    )
    assert split.train["timestamp"].max() == pd.Timestamp(row.last_train_timestamp_utc)
    assert split.validation["timestamp"].min() == pd.Timestamp(row.first_validation_timestamp_utc)
    assert split.validation["timestamp"].max() == pd.Timestamp(row.last_validation_timestamp_utc)
    assert split.test["timestamp"].min() == pd.Timestamp(row.first_test_holdout_timestamp_utc)
    assert int(row.purge_bars_24h) == purge


def test_campaign_artifacts_are_consistent() -> None:
    features = pd.read_csv(CAMPAIGN / "feature_availability_final.csv")
    splits = pd.read_csv(CAMPAIGN / "split_metadata_final.csv")
    assert len(splits) == 3
    assert set(splits.timeframe) == {"15m", "1h", "4h"}
    assert not features.duplicated(["feature", "market", "timeframe"]).any()
    assert (features["finite_rows"] <= features["research_eligible_rows"]).all()
    populated = features["finite_rows"] > 0
    assert features.loc[populated, "first_finite_timestamp"].ne("").all()
    assert features.loc[populated, "last_finite_timestamp"].ne("").all()
    report = (CAMPAIGN / "R1_7_VERIFICATION.md").read_text(encoding="utf-8")
    assert "selected_15m_summary.json" in report
    summary_files = {p.name for p in CAMPAIGN.glob("*summary*.json")}
    assert {"selected_15m_summary.json", "selected_1h_summary.json", "selected_4h_summary.json"} <= summary_files
