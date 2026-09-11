import numpy as np
import pandas as pd
import binance_research.fast_discovery as fd

def synthetic():
    n=96; t=pd.date_range("2024-01-01", periods=n, freq="h"); d={"open_time":t,"open":np.arange(n)+100.0,"close":np.arange(n)+100.25,"symbol":["SYNTH"]*n,"segment_id":["s"]*n}
    for f in fd.DEFAULT_PRIMITIVES: d[f]=np.sin(np.arange(n)/7)
    for f in ("ema20_slope_5","sig_ema20_50"): d[f]=np.cos(np.arange(n)/9)
    return pd.DataFrame(d)
def fake(frame, feature_columns, **kwargs):
    name=feature_columns[0]; return pd.DataFrame([{"model":"I:"+name,"fold":0,"validation_rows":2,"log_loss_improvement":.2},{"model":"I:"+name,"fold":1,"validation_rows":2,"log_loss_improvement":.1}])
def test_slow_reference_matches_optimized(monkeypatch,tmp_path):
    monkeypatch.setattr(fd,"evaluate_walk_forward",fake); frame=synthetic(); out=tmp_path/"run"; got=fd.run_campaign(frame,out)
    assert got["s0_survivors"]==9 and got["cache_hits"]==0 and got["cache_misses"]==9
    assert set(pd.read_csv(out/"S1_COMBINATION_RESULTS.csv").status)=={"SURVIVOR"} and (pd.read_csv(out/"S2_FINALIST_RESULTS.csv").trade_rows==0).all()
def test_timestamp_block_fixture(monkeypatch):
    monkeypatch.setattr(fd,"evaluate_walk_forward",fake); one=synthetic(); one["open_time"]=pd.date_range("2024-01-01",periods=len(one),freq="min"); s,_=fd.screen_s0(one,primitives=["premium"]); assert int(s.iloc[0].independent_block_count)==2

def test_cli_requires_root_and_manifest(tmp_path):
    import subprocess,sys; r=subprocess.run([sys.executable,"scripts/run_fast_discovery.py","--input","x.parquet","--output",str(tmp_path)],capture_output=True,text=True); assert r.returncode!=0 and "required" in r.stderr
