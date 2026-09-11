from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from binance_research.predictability import build_forward_labels, resolve_horizon_bars

FIELDS=("decision_time","entry_time","exit_time","future_log_return","direction_up","label_status","eligible")

def _fixture(timeframe: str, market: str) -> pd.DataFrame:
    minutes={"15m":15,"1h":60,"4h":240}[timeframe]; n=180
    t=pd.date_range("2025-01-01",periods=n,freq=f"{minutes}min",tz="UTC")
    close=100+np.arange(n,dtype=float)+np.sin(np.arange(n))
    frame=pd.DataFrame({"open_time":t,"close_time":t+pd.Timedelta(minutes=minutes),"open":close,"high":close+1,"low":close-1,"close":close+0.5,"symbol":"BTCUSDT","market":market})
    if market=="um":
        frame["funding_rate"]=np.where(np.arange(n)%2==0,0.0001,-0.0001)
    frame.loc[73,"open_time"] += pd.Timedelta(minutes=minutes)
    return frame

def _slow_reference(frame: pd.DataFrame, timeframe: str, horizon: str) -> pd.DataFrame:
    step=pd.Timedelta(minutes={"15m":15,"1h":60,"4h":240}[timeframe]); bars=resolve_horizon_bars(timeframe,horizon); n=len(frame)
    opens=pd.to_numeric(frame.open).to_numpy(float); closes=pd.to_numeric(frame.close).to_numpy(float); times=pd.to_datetime(frame.open_time,utc=True)
    out=[]
    for i in range(n):
        j=i+bars; row={"decision_time":pd.to_datetime(frame.close_time,utc=True).iloc[i] if "close_time" in frame else times.iloc[i]+step,"entry_time":pd.NaT,"exit_time":pd.NaT,"future_log_return":np.nan,"direction_up":np.nan,"label_status":"INSUFFICIENT_FUTURE","eligible":False}
        if j<n:
            contiguous=(times.iloc[i:j+1].diff().iloc[1:]==step).all()
            if not contiguous: row["label_status"]="GAP"
            elif np.isfinite(opens[i+1]) and opens[i+1]>0 and np.isfinite(closes[j]) and closes[j]>0:
                row.update(entry_time=times.iloc[i+1],exit_time=times.iloc[j],future_log_return=float(np.log(closes[j]/opens[i+1])),label_status="ELIGIBLE",eligible=True)
                row["direction_up"]=float(row["future_log_return"]>0)
            else: row["label_status"]="INVALID_PRICE"
        out.append(row)
    return pd.DataFrame(out)

@pytest.mark.parametrize("market",["spot","um"])
@pytest.mark.parametrize("timeframe",["15m","1h","4h"])
def test_slow_reference_matrix_matches_optimized(market,timeframe):
    frame=_fixture(timeframe,market)
    horizons=[h for h in ("15m","1h","4h","24h") if {"15m":15,"1h":60,"4h":240,"24h":1440}[h] >= {"15m":15,"1h":60,"4h":240}[timeframe]]
    for horizon in horizons:
        actual=build_forward_labels(frame,source_timeframe=timeframe,horizon=horizon).reset_index(drop=True)
        expected=_slow_reference(frame,timeframe,horizon)
        for field in FIELDS:
            if field in ("decision_time","entry_time","exit_time"):
                np.testing.assert_array_equal(pd.to_datetime(actual[field].astype(str),utc=True).astype("int64"), pd.to_datetime(expected[field].astype(str),utc=True).astype("int64"))
            elif field in ("future_log_return","direction_up"):
                np.testing.assert_allclose(actual[field].to_numpy(float),expected[field].to_numpy(float),equal_nan=True)
            else:
                assert actual[field].tolist()==expected[field].tolist(), (market,timeframe,horizon,field)


def test_um_fixture_contains_positive_negative_funding_and_gap():
    frame=_fixture("1h","um")
    assert set(np.sign(frame.funding_rate))=={-1,1}
    assert frame.open_time.diff().gt(pd.Timedelta(hours=1)).any()


def test_qualification_receipt_is_reproducible(tmp_path: Path):
    payload={"matrix":"spot+um x 15m+1h+4h x duration horizons","fields":list(FIELDS),"funding":"positive+negative synthetic UM","gap":"included","outcomes":"NOT_RUN","final_holdout":"UNTOUCHED"}
    first=json.dumps(payload,sort_keys=True).encode(); second=json.dumps(payload,sort_keys=True).encode(); assert hashlib.sha256(first).hexdigest()==hashlib.sha256(second).hexdigest()
    path=tmp_path/"qualification_receipt.json"; path.write_bytes(first); assert path.read_bytes()==first



