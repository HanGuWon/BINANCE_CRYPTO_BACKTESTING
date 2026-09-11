from pathlib import Path
import argparse, json, sys
import pandas as pd
from binance_research.fast_discovery import run_campaign

p=argparse.ArgumentParser(); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--timeframe", default="1h"); p.add_argument("--market", default="um"); p.add_argument("--dataset-root", type=Path); p.add_argument("--split-manifest", type=Path)
a=p.parse_args()
if a.market != "um": raise SystemExit("Fast Discovery requires --market um")
if a.dataset_root and a.dataset_root not in a.input.resolve().parents: raise SystemExit("input is outside declared causal dataset root")
manifest=None
if a.split_manifest:
    manifest=json.loads(a.split_manifest.read_text(encoding="utf-8")); holdout=manifest.get("final_holdout_times", [])
else: holdout=[]
try:
    import pyarrow.parquet as pq
    schema=set(pq.read_schema(a.input).names)
except Exception as exc:
    raise SystemExit(f"cannot inspect parquet schema: {exc}")
allowed=[c for c in ("timestamp","open_time","open","close","symbol","timeframe","segment_id","premium","premium_zscore90","donchian_breakout20","roc6","rvol20","vwap_deviation20","taker_buy_sell_ratio","cvd_slope6","bb_bandwidth20","ema20_slope_5","sig_ema20_50") if c in schema]
if not {"open_time","open","close"}.issubset(schema):
    # Fail-closed campaign is allowed for unavailable historical labels, but still records the reason.
    pass
frame=pd.read_parquet(a.input, columns=allowed)
if holdout and "timestamp" in frame:
    observed=set(pd.to_datetime(frame["timestamp"], errors="coerce").dropna().astype(str));
    if observed.intersection(set(map(str, holdout))): raise SystemExit("input intersects final holdout")
summary=run_campaign(frame, a.output, timeframe=a.timeframe, market=a.market, split_manifest=manifest)
print(json.dumps(summary, sort_keys=True))