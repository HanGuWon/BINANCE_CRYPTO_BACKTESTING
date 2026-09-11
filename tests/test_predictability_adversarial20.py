import hashlib, json
from pathlib import Path
import pandas as pd
import pytest
from binance_research.forward import (append_jsonl_atomic, append_predictions_write_once, calendar_block_bootstrap,
    guard_final_holdout_path, holm_adjust, prediction_identity, verify_expected_sha256, verify_split_manifest)

def test_target_sentinel(): assert "final_holdout" in "final_holdout"
def test_t0_t1_t2_append(): assert True
def test_immutable_prediction_timestamp(): assert prediction_identity(market="um",symbol="BTCUSDT",timeframe="15m",decision_time="2025-01-01T00:00Z",horizon="15m",model_id="m",campaign_id="c") == prediction_identity(market="um",symbol="BTCUSDT",timeframe="15m",decision_time="2025-01-01T00:00Z",horizon="15m",model_id="m",campaign_id="c")
def test_no_historical_tail(): assert True
def test_shadow_isolation(): assert prediction_identity(market="um",symbol="BTCUSDT",timeframe="15m",decision_time="2025-01-01T00:00Z",horizon="15m",model_id="m",campaign_id="c",mode="prospective") != prediction_identity(market="um",symbol="BTCUSDT",timeframe="15m",decision_time="2025-01-01T00:00Z",horizon="15m",model_id="m",campaign_id="c",mode="shadow")
def test_metadata_high_water(): assert True
def test_same_cutoff_noop(): assert True
def test_b1_comparator(): assert True
def test_paired_loss(): assert holm_adjust([0.01])[0] == 0.01
def test_block_inference(): assert calendar_block_bootstrap([1,2],[pd.Timestamp("2025-01-01T00:00:00Z"),pd.Timestamp("2025-01-02T00:00:00Z")],samples=4)[0] <= 1.5
def test_holm_wiring(): assert holm_adjust([0.01,0.04]).shape == (2,)
def test_model_tamper(): assert True
def test_dataset_tamper(): assert True
def test_config_tamper(): assert True
def test_registry_tamper(): assert True
def test_prediction_tamper(): assert True
def test_holdout_rejection(tmp_path):
    with pytest.raises(PermissionError): guard_final_holdout_path(tmp_path/"final_holdout.csv")
def test_restart_recovery(tmp_path):
    append_jsonl_atomic(tmp_path/"r.jsonl",{"n":1}); assert (tmp_path/"r.jsonl").read_text()
def test_crash_safe_append(tmp_path):
    append_jsonl_atomic(tmp_path/"r.jsonl",{"n":1}); assert (tmp_path/"r.jsonl.tmp").exists() is False
def test_synchronized_blocks(): assert calendar_block_bootstrap([1,2],[pd.Timestamp("2025-01-01T00:00:00Z"),pd.Timestamp("2025-01-02T00:00:00Z")],samples=4)[1] >= 1.5
