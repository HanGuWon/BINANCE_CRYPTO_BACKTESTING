"""Regression tests for the frozen R2A.2 aggregation contract."""
from __future__ import annotations

import pandas as pd
import numpy as np
import pytest
import sys
import hashlib
import json
from pathlib import Path

from scripts.aggregate_r2a2 import (
    BOOTSTRAP_SAMPLES,
    REQUIRED_TRADE_FIELDS,
    SEED,
    _assert_pre_holdout,
    add_cross_market_diagnostics,
    aggregate_artifact_hashes,
    aggregate_symbol_concentration,
    bh,
    calendar_block_bootstrap,
    checkpoint_path,
    cohort_subset,
    evaluate_temporal_replication,
    main,
)
import scripts.aggregate_r2a2 as aggregation


def _row(**overrides: object) -> object:
    values = {
        "valid_fold_count": 4,
        "positive_fold_fraction": 0.75,
        "fdr_q_value": 0.01,
        "aggregate_hac_t": 3.1,
        "max_top_symbol_share_abs": 0.4,
        "worst_fold_aggregate_mean": 0.01,
        "best_fold_aggregate_mean": 0.03,
    }
    values.update(overrides)
    return type("Row", (), values)()


def _trades() -> pd.DataFrame:
    return pd.DataFrame({
        "decision_time": pd.to_datetime(["2020-01-02", "2020-01-02", "2020-02-02", "2020-02-02"], utc=True),
        "symbol": ["AAA", "BBB", "AAA", "BBB"],
        "net_return": [0.10, 0.30, -0.20, 0.00],
    })


def test_calendar_bootstrap_is_1000_and_seed_deterministic() -> None:
    values = calendar_block_bootstrap(_trades())
    assert len(values) == BOOTSTRAP_SAMPLES == 1000
    assert np.array_equal(values, calendar_block_bootstrap(_trades(), samples=1000, seed=SEED))


def test_calendar_bootstrap_preserves_cross_sectional_blocks() -> None:
    trades = _trades()
    # Sampling the DataFrame must equal sampling its already equal-weighted
    # decision-time series: symbols in a month are never sampled separately.
    series = trades.groupby("decision_time", sort=True).net_return.mean()
    np.testing.assert_array_equal(calendar_block_bootstrap(trades), calendar_block_bootstrap(series))


@pytest.mark.parametrize("field,value", [
    ("max_top_symbol_share_abs", 0.5001),
    ("aggregate_hac_t", 2.99),
    ("fdr_q_value", 0.0501),
    ("positive_fold_fraction", 0.749),
])
def test_every_replication_criterion_is_required(field: str, value: float) -> None:
    assert evaluate_temporal_replication(_row(**{field: value})) == "NO_REPLICATION"


def test_catastrophic_reversal_cannot_pass() -> None:
    assert evaluate_temporal_replication(_row(worst_fold_aggregate_mean=-0.25, best_fold_aggregate_mean=0.10)) == "NO_REPLICATION"


def test_fewer_than_four_valid_folds_is_insufficient() -> None:
    assert evaluate_temporal_replication(_row(valid_fold_count=3)) == "INSUFFICIENT_FOLDS"


def test_missing_required_evidence_fails_closed() -> None:
    assert evaluate_temporal_replication(_row(max_top_symbol_share_abs=float("nan"))) == "INSUFFICIENT_EVIDENCE"


def test_bh_accepts_full_registry_family_without_subfamily_split() -> None:
    p = pd.Series(np.linspace(0.001, 0.999, 756))
    q = bh(p)
    assert len(q) == 756
    assert q.index.equals(p.index)
    assert (q.dropna() >= p).all()


def test_holdout_guard_rejects_entry_or_exit_timestamp() -> None:
    frame = _trades().assign(
        entry_time=pd.to_datetime(["2020-01-02", "2020-01-02", "2024-02-11", "2020-02-02"], utc=True),
        exit_time=pd.to_datetime(["2020-01-03", "2020-01-03", "2024-02-11", "2020-02-03"], utc=True),
    )
    frame["decision_time"] = pd.to_datetime(frame["decision_time"], utc=True)
    frame["signal_value"] = 1.0
    frame["gross_return"] = 0.0
    frame["funding_cashflow"] = 0.0
    frame["side"] = "LONG"
    with pytest.raises(RuntimeError, match="holdout contamination"):
        _assert_pre_holdout(frame, "1h", Path("synthetic.parquet"))


def test_required_fields_and_canonical_root_guard() -> None:
    assert REQUIRED_TRADE_FIELDS == {"decision_time", "symbol", "side", "signal_value", "entry_time", "exit_time", "gross_return", "funding_cashflow", "net_return"}
    old = sys.argv
    try:
        sys.argv = ["aggregate_r2a2.py", "--root", "D:/some/final_holdout"]
        with pytest.raises(RuntimeError, match="v10"):
            main()
    finally:
        sys.argv = old


def _synthetic_aggregation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[object, Path, list[str]]:
    campaign = tmp_path / "r2a2_temporal_horizon_v1"
    campaign.mkdir()
    sibling = campaign.parent / "r1_final_panel_v1"
    sibling.mkdir()
    registry = pd.DataFrame([{"trial_id": "T0001", "feature_id": "f", "variant": "v", "market": "spot", "timeframe": "1h", "side": "LONG", "horizon_bars": 4}])
    folds = pd.DataFrame([{"fold_id": "F01"}])
    registry.to_csv(campaign / "trial_registry.csv", index=False)
    folds.to_csv(campaign / "fold_registry.csv", index=False)
    universe = pd.DataFrame([{"market": "spot", "universe_month": "2020-01", "symbol": "AAA", "selected_top20": True, "selected_top50": True, "selected_top100": True}])
    universe.to_csv(sibling / "universe_monthly.csv", index=False)
    times = pd.date_range("2020-01-02", periods=30, freq="h", tz="UTC")
    trades = pd.DataFrame({"decision_time": times, "symbol": "AAA", "side": "LONG", "signal_value": 1.0, "entry_time": times + pd.Timedelta(hours=1), "exit_time": times + pd.Timedelta(hours=5), "gross_return": 0.01, "funding_cashflow": 0.0, "net_return": 0.009, "universe_month": times.strftime("%Y-%m")})
    root = tmp_path / "checkpoints_v10"
    root.mkdir()
    trades.to_parquet(root / "T0001_F01_trades.parquet", index=False)
    registry_sha = aggregation.sha256(campaign / "trial_registry.csv")
    (root / "run_manifest.json").write_text(json.dumps({"registry_sha256": registry_sha, "implementation_sha": "impl", "source_tree_sha256": "tree", "source_dirty": False, "completed_units": ["T0001|F01"], "failed_units": []}), encoding="utf-8")
    monkeypatch.setattr(aggregation, "CAMPAIGN", campaign)
    monkeypatch.setattr(aggregation, "CANONICAL_CHECKPOINT_ROOT", root.resolve())
    monkeypatch.setattr(aggregation, "EXPECTED_OUTCOME_IMPLEMENTATION_SHA", "impl")
    monkeypatch.setattr(aggregation, "EXPECTED_OUTCOME_REGISTRY_SHA256", registry_sha)
    monkeypatch.setattr(aggregation, "EXPECTED_OUTCOME_SOURCE_TREE_SHA256", "tree")
    monkeypatch.setattr(aggregation, "aggregation_source_state", lambda: ("agg-synthetic", False))
    names = ["fold_results.csv", "horizon_results.csv", "temporal_replication.csv", "multiple_testing.csv", "bootstrap_results.csv", "cohort_diagnostics.csv", "yearly_diagnostics.csv", "symbol_concentration.csv", "mfe_mae_diagnostics.csv", "candidate_shortlist.csv", "holdout_guard_proof.json", "aggregate_manifest.json"]
    return aggregation, root, names


def test_repeated_full_aggregation_artifact_hashes_are_identical(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module, root, names = _synthetic_aggregation(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["aggregate_r2a2.py", "--root", str(root)])
    assert module.main() == 0
    first = module.aggregate_artifact_hashes(module.CAMPAIGN, names)
    assert module.main() == 0
    second = module.aggregate_artifact_hashes(module.CAMPAIGN, names)
    assert first == second


def test_full_aggregation_never_opens_final_holdout_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module, root, _ = _synthetic_aggregation(monkeypatch, tmp_path)
    seen: list[Path] = []
    original = module.pd.read_parquet
    def traced(path: object, *args: object, **kwargs: object):
        seen.append(Path(path).resolve())
        return original(path, *args, **kwargs)
    monkeypatch.setattr(module.pd, "read_parquet", traced)
    monkeypatch.setattr(sys, "argv", ["aggregate_r2a2.py", "--root", str(root)])
    assert module.main() == 0
    assert seen and all(path.parent == root.resolve() for path in seen)
    assert all("final_holdout" not in str(path).lower() for path in seen)


def test_aggregate_symbol_concentration_expected_value() -> None:
    trades = pd.DataFrame({"symbol": ["AAA", "AAA", "BBB"], "net_return": [0.2, 0.2, 0.6]})
    result = aggregate_symbol_concentration(trades)
    assert result["top_symbol"] == "BBB"
    assert result["top_symbol_share_abs"] == pytest.approx(0.6)


def test_cross_market_and_um_side_diagnostics_expected_values() -> None:
    frame = pd.DataFrame([
        {"feature_id": "f", "variant": "v", "market": "spot", "timeframe": "1h", "side": "LONG", "horizon_bars": 4, "aggregate_mean_net_return": 0.10},
        {"feature_id": "f", "variant": "v", "market": "um", "timeframe": "1h", "side": "LONG", "horizon_bars": 4, "aggregate_mean_net_return": 0.05},
        {"feature_id": "f", "variant": "v", "market": "um", "timeframe": "1h", "side": "SHORT", "horizon_bars": 4, "aggregate_mean_net_return": -0.02},
        {"feature_id": "f", "variant": "v", "market": "spot", "timeframe": "1h", "side": "LONG", "horizon_bars": 12, "aggregate_mean_net_return": -0.10},
    ])
    result = add_cross_market_diagnostics(frame)
    um_long = result[(result.market == "um") & (result.side == "LONG") & (result.horizon_bars == 4)].iloc[0]
    assert um_long.spot_um_consistency_note == "same_direction"
    assert um_long.um_long_short_mean_delta == pytest.approx(0.07)
    assert int(result[result.horizon_bars == 4].horizon_decay_position.iloc[0]) == 1
    assert result[result.horizon_bars == 12].spot_um_consistency_note.iloc[0] == "not_comparable"


def test_repeated_bootstrap_artifact_is_byte_deterministic() -> None:
    first = pd.DataFrame({"draw": calendar_block_bootstrap(_trades())}).to_csv(index=False)
    second = pd.DataFrame({"draw": calendar_block_bootstrap(_trades())}).to_csv(index=False)
    assert first == second


def test_cohort_subset_is_functional_and_distinct() -> None:
    trades = pd.DataFrame({"universe_month": ["2020-01", "2020-01", "2020-01"], "symbol": ["AAA", "BBB", "CCC"], "net_return": [0.1, 0.2, 0.3]})
    mapping = {("spot", "2020-01", "AAA", "top20"): True, ("spot", "2020-01", "AAA", "top50"): True, ("spot", "2020-01", "BBB", "top50"): True, ("spot", "2020-01", "AAA", "top100"): True, ("spot", "2020-01", "BBB", "top100"): True, ("spot", "2020-01", "CCC", "top100"): True}
    assert len(cohort_subset(trades, "spot", "top20", mapping)) == 1
    assert len(cohort_subset(trades, "spot", "top50", mapping)) == 2
    assert len(cohort_subset(trades, "spot", "top100", mapping)) == 3


def test_checkpoint_path_and_artifact_hashes_are_pinned(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="canonical"):
        checkpoint_path(Path("D:/some/final_holdout"), "T0001", "F01")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    assert aggregate_artifact_hashes(tmp_path, ["a.txt"]) == aggregate_artifact_hashes(tmp_path, ["a.txt"])
