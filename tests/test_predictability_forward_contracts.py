from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from binance_research.forward import append_predictions_write_once, calendar_block_bootstrap, calendar_block_pvalue, guard_final_holdout_path, holm_adjust, paired_log_loss_difference, prediction_identity, verify_expected_sha256, verify_split_manifest, write_model_artifact
from binance_research.predictability import build_forward_labels, fit_logistic_model

def _rows(n=24):
    t=pd.date_range("2025-01-01",periods=n,freq="15min",tz="UTC")
    return pd.DataFrame({"open_time":t,"close_time":t+pd.Timedelta(minutes=15),"open":np.arange(n,dtype=float)+100,"close":np.arange(n,dtype=float)+101})

def test_prediction_identity_is_order_independent_and_utc():
    a=prediction_identity(market="um",symbol="BTCUSDT",timeframe="1h",decision_time="2025-01-01T00:00:00Z",horizon="24h",model_id="B1+I:x",campaign_id="c")
    b=prediction_identity(campaign_id="c",model_id="B1+I:x",horizon="24h",decision_time=pd.Timestamp("2024-12-31 19:00",tz="US/Eastern"),timeframe="1h",symbol="BTCUSDT",market="um")
    assert a==b

def test_prediction_identity_requires_decision_time():
    with pytest.raises(ValueError): prediction_identity(market="spot",symbol="X",timeframe="15m",decision_time=pd.NaT,horizon="15m",model_id="m",campaign_id="c")

def test_write_model_artifact_is_write_once(tmp_path):
    path=tmp_path/"model.json"; model=SimpleNamespace(schema="v1",coefficients=[1.0]); digest=write_model_artifact(path,model,implementation_sha256="abc")
    assert len(digest)==64
    with pytest.raises(FileExistsError): write_model_artifact(path,model,implementation_sha256="abc")

def test_prediction_store_rejects_duplicates_and_conflicts(tmp_path):
    path=tmp_path/"predictions.csv"; first=pd.DataFrame([{"prediction_id":"a","decision_time":"2025-01-01T00:00:00Z","probability_up":.5}]); append_predictions_write_once(path,first)
    with pytest.raises(ValueError): append_predictions_write_once(path,first)
    with pytest.raises(ValueError): append_predictions_write_once(path,pd.DataFrame([{"prediction_id":"b"},{"prediction_id":"b"}]))
    assert len(pd.read_csv(path))==1

def test_prediction_store_append_is_atomic(tmp_path):
    path=tmp_path/"predictions.csv"; append_predictions_write_once(path,[{"prediction_id":"a","v":1}]); append_predictions_write_once(path,[{"prediction_id":"b","v":2}]); assert set(pd.read_csv(path).prediction_id)=={"a","b"}; assert not (tmp_path/"predictions.csv.tmp").exists()

def test_holdout_guard_is_fail_closed():
    with pytest.raises(PermissionError): guard_final_holdout_path("data/final_holdout/panel.parquet")
    guard_final_holdout_path("data/development/panel.parquet")

def test_pairwise_score_is_elementwise():
    values=paired_log_loss_difference([1,0],[.5,.5],[.8,.2]); assert values[0]>0 and values[1]>0
    with pytest.raises(ValueError): paired_log_loss_difference([1],[.5,.5],[.5])

def test_holm_is_bounded():
    adjusted=holm_adjust([.01,.04,.2]); assert np.all((adjusted>=0)&(adjusted<=1)); assert adjusted[0]<=adjusted[1]<=adjusted[2]

def test_calendar_bootstrap_deterministic():
    stamps=pd.date_range("2025-01-01",periods=8,freq="12h",tz="UTC"); a=calendar_block_bootstrap(range(8),stamps,block_days=1,samples=100,seed=7); b=calendar_block_bootstrap(range(8),stamps,block_days=1,samples=100,seed=7); assert a==b and np.isfinite(a).all()

def test_zero_return_maps_to_not_up():
    bars=_rows(6); bars.loc[1,"close"]=bars.loc[1,"open"]; labels=build_forward_labels(bars,source_timeframe="15m",horizon="15m"); assert labels.loc[0,"direction_up"]==0 and labels.loc[0,"label_status"]=="ELIGIBLE"

def test_nan_future_price_stays_nan():
    bars=_rows(6); bars.loc[2,"close"]=np.nan; labels=build_forward_labels(bars,source_timeframe="15m",horizon="15m"); assert np.isnan(labels.loc[1,"direction_up"]) and labels.loc[1,"label_status"]=="INVALID_PRICE"

def test_regularization_duplicate_rows_stable():
    x=pd.DataFrame({"x":[-1.,-.5,.5,1.]*4}); y=pd.Series([0.,0.,1.,1.]*4); one=fit_logistic_model(x,y,["x"],regularization=.2); doubled=fit_logistic_model(pd.concat([x,x],ignore_index=True),pd.concat([y,y],ignore_index=True),["x"],regularization=.2); np.testing.assert_allclose(one.coefficients,doubled.coefficients,rtol=1e-5,atol=1e-5); assert one.regularization_definition.startswith("mean_log_loss")


def test_prediction_identity_binds_artifact_provenance():
    kwargs=dict(market="um",symbol="BTCUSDT",timeframe="1h",decision_time="2025-01-01T00:00Z",horizon="1h",model_id="m",campaign_id="c")
    assert prediction_identity(**kwargs, model_artifact_sha256="a") != prediction_identity(**kwargs, model_artifact_sha256="b")


def test_prediction_store_allows_explicit_exact_replay_only(tmp_path):
    path=tmp_path/"p.csv"; row={"prediction_id":"a","v":1}; append_predictions_write_once(path,[row])
    with pytest.raises(ValueError): append_predictions_write_once(path,[row])
    append_predictions_write_once(path,[row],allow_replay=True)
    assert len(pd.read_csv(path))==1


def test_holdout_metadata_guard(tmp_path):
    source=tmp_path/"bars.csv"; source.write_text("x\n1\n",encoding="utf-8")
    (tmp_path/"metadata.json").write_text('{"final_holdout": true}',encoding="utf-8")
    with pytest.raises(PermissionError): guard_final_holdout_path(source)

def test_prediction_identity_separates_shadow_and_prospective_modes():
    kwargs = dict(market="um", symbol="BTCUSDT", timeframe="15m", decision_time="2025-01-01T00:00Z", horizon="15m", model_id="m", campaign_id="c")
    assert prediction_identity(**kwargs, mode="SHADOW_REPLAY_NON_PROSPECTIVE") != prediction_identity(**kwargs, mode="prospective")


def test_sha256_verification_fails_closed(tmp_path: Path):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"stable")
    import hashlib
    expected = hashlib.sha256(b"stable").hexdigest()
    assert verify_expected_sha256(artifact, expected, label="artifact") == expected
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        verify_expected_sha256(artifact, "0" * 64, label="artifact")


def test_split_manifest_rejects_holdout_intersection(tmp_path: Path):
    import pandas as pd, json
    t = pd.Timestamp("2025-01-01T00:00:00Z")
    manifest = tmp_path / "split.json"
    manifest.write_text(json.dumps({"final_holdout_times":[t.isoformat()]}), encoding="utf-8")
    with pytest.raises(PermissionError):
        verify_split_manifest(manifest, pd.DataFrame({"decision_time":[t]}))


def test_block_pvalue_ignores_row_replication():
    times = [pd.Timestamp("2025-01-01T00:00:00Z"), pd.Timestamp("2025-01-02T00:00:00Z")]
    values = [0.2, 0.4]
    p1 = calendar_block_pvalue(values, times, samples=128, seed=1729)
    p2 = calendar_block_pvalue(values * 10, times * 10, samples=128, seed=1729)
    assert p1 == p2
