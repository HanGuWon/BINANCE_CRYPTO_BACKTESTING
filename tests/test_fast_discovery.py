import hashlib
import numpy as np
import pandas as pd
import binance_research.fast_discovery as fd

def _frame(n=96):
    t=pd.date_range("2024-01-01", periods=n, freq="h")
    d={"open_time":t,"open":np.linspace(100,110,n),"close":np.linspace(100.5,110.5,n),"symbol":["SYNTH"]*n,"segment_id":["seg1"]*n}
    for f in fd.DEFAULT_PRIMITIVES + ("ema20_slope_5","sig_ema20_50"): d[f]=np.sin(np.arange(n)/5)
    return pd.DataFrame(d)
def _fake_eval(frame, feature_columns, **kwargs):
    name=feature_columns[0]; return pd.DataFrame([{"model":"I:"+name,"fold":0,"validation_rows":4,"log_loss_improvement":0.2},{"model":"I:"+name,"fold":1,"validation_rows":4,"log_loss_improvement":0.1}])
def test_s0_missing_label_columns_fails_closed():
    s,r=fd.screen_s0(pd.DataFrame({"premium":[0.1]})); assert s.empty and set(r.status)=={"HISTORICAL_UNAVAILABLE"}
def test_cache_key_and_s1_grammar():
    c=fd.FeatureCache(); k=fd.canonical_cache_key("um","1h","BTCUSDT","seg","roc6","raw","abc"); assert c.get(k,lambda:pd.Series([1])) is c.get(k,lambda:pd.Series([2])); assert c.hits==1 and len(fd.build_s1_registry())==4 and (fd.build_s1_registry().component_count==3).all()
def test_campaign_writes_zero_trade_finalist_artifacts(tmp_path):
    summary=fd.run_campaign(pd.DataFrame({"premium":[0.1,0.2],"symbol":["BTCUSDT"]*2}),tmp_path); assert summary["s0_survivors"]==0 and (tmp_path/"S2_FINALIST_RESULTS.csv").exists(); assert "trade_rows" in pd.read_csv(tmp_path/"S2_FINALIST_RESULTS.csv").columns
def test_nonempty_s0_s1_s2_and_cache(monkeypatch,tmp_path):
    monkeypatch.setattr(fd,"evaluate_walk_forward",_fake_eval); out=tmp_path/"a"; summary=fd.run_campaign(_frame(),out); assert summary["s0_survivors"]==9 and summary["s1_survivors"]>=1 and summary["cache_misses"]==9; assert (pd.read_csv(out/"S2_FINALIST_RESULTS.csv")["trade_rows"]==0).all()
def test_calendar_block_count_uses_fold_ids(monkeypatch):
    monkeypatch.setattr(fd,"evaluate_walk_forward",_fake_eval); s,_=fd.screen_s0(_frame(),primitives=["premium"]); assert int(s.iloc[0].independent_block_count)==2
def test_rerun_artifacts_are_deterministic(monkeypatch,tmp_path):
    monkeypatch.setattr(fd,"evaluate_walk_forward",_fake_eval); a=tmp_path/"a"; b=tmp_path/"b"; fd.run_campaign(_frame(),a); fd.run_campaign(_frame(),b)
    for name in ("FEATURE_REGISTRY.csv","COMBINATION_REGISTRY.csv","S0_PRIMITIVE_RESULTS.csv","S0_REJECTIONS.csv","S1_COMBINATION_RESULTS.csv","S2_FINALIST_RESULTS.csv","FINAL_REPORT.md"): assert hashlib.sha256((a/name).read_bytes()).hexdigest()==hashlib.sha256((b/name).read_bytes()).hexdigest()
def test_required_manifests_written(tmp_path):
    fd.run_campaign(pd.DataFrame({"premium":[0.1]}),tmp_path)
    for name in ("FAST_DISCOVERY_PROTOCOL.md","PREREGISTRATION.json","SPLIT_MANIFEST.json","PROVENANCE_MANIFEST.json","SCREENING_POLICY.json"): assert (tmp_path/name).exists()

def test_provenance_manifest_pins_computed_source_and_artifact_identity(tmp_path):
    import json
    fd.run_campaign(_frame(), tmp_path)
    manifest = json.loads((tmp_path / "PROVENANCE_MANIFEST.json").read_text(encoding="utf-8"))
    assert len(manifest["implementation_commit"]) == 40
    assert len(manifest["source_tree_sha256"]) == 64
    assert isinstance(manifest["scientific_source_clean"], bool)
    assert len(manifest["combination_registry_sha256"]) == 64
    assert len(manifest["screening_policy_sha256"]) == 64


def test_provenance_mismatch_fails_closed(monkeypatch):
    monkeypatch.setattr(fd, "_source_identity", lambda: {"implementation_commit": "a" * 40, "source_tree_sha256": "b" * 64, "scientific_source_clean": True})
    manifest = {"implementation_commit": "c" * 40, "source_tree_sha256": "b" * 64}
    import pytest
    with pytest.raises(ValueError, match="implementation_commit"):
        fd.verify_source_identity(manifest)


def test_dirty_provenance_fails_closed(monkeypatch):
    monkeypatch.setattr(fd, "_source_identity", lambda: {"implementation_commit": "a" * 40, "source_tree_sha256": "b" * 64, "scientific_source_clean": False})
    manifest = {"implementation_commit": "a" * 40, "source_tree_sha256": "b" * 64}
    import pytest
    with pytest.raises(ValueError, match="dirty"):
        fd.verify_source_identity(manifest)
