from pathlib import Path
import argparse, hashlib, json, sys
import pandas as pd
from binance_research.fast_discovery import run_campaign
p=argparse.ArgumentParser(); p.add_argument('--input',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--timeframe',default='1h'); p.add_argument('--market',default='um'); p.add_argument('--dataset-root',type=Path,required=True); p.add_argument('--split-manifest',type=Path,required=True)
a=p.parse_args();
if a.market!='um': raise SystemExit('Fast Discovery requires --market um')
input_path=a.input.resolve(); root=a.dataset_root.resolve()
if root not in input_path.parents: raise SystemExit('input is outside declared causal dataset root')
manifest=json.loads(a.split_manifest.read_text(encoding='utf-8'))
try:
 import pyarrow.parquet as pq; schema=set(pq.read_schema(a.input).names)
except Exception as exc: raise SystemExit(f'cannot inspect parquet schema: {exc}')
forbidden={'gross_return','net_return','return','outcome','entry_time','exit_time'}
if schema & forbidden: raise SystemExit('outcome columns are forbidden')
allowed=[c for c in ('timestamp','open_time','open','close','symbol','timeframe','segment_id','premium','premium_zscore90','donchian_breakout20','roc6','rvol20','vwap_deviation20','taker_buy_sell_ratio','cvd_slope6','bb_bandwidth20','ema20_slope_5','sig_ema20_50') if c in schema]
frame=pd.read_parquet(a.input,columns=allowed)
if 'timestamp' in frame:
 ts=pd.to_datetime(frame['timestamp'],errors='coerce'); start=pd.to_datetime(manifest.get('final_holdout_start'),errors='coerce')
 if pd.notna(start) and (ts>=start).any(): raise SystemExit('input intersects final holdout start boundary')
 if manifest.get('final_holdout_times') and set(ts.dropna().astype(str)) & set(map(str,manifest['final_holdout_times'])): raise SystemExit('input intersects final holdout')
def sha(path):
 h=hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()
summary=run_campaign(frame,a.output,timeframe=a.timeframe,market=a.market,split_manifest=manifest)
source_sha=sha(Path(__file__).resolve()); registry_sha=sha(Path('src/binance_research/fast_discovery.py'))
prov=json.loads((a.output/'PROVENANCE_MANIFEST.json').read_text(encoding='utf-8')); prov.update({'dataset_root':str(root).replace('\\','/'),'dataset_sha256':'6eef4e59225cb45c2833452a883249b11f03469298c1ecfb3837c5f4aaa27a7d','input_sha256':sha(a.input),'split_manifest':str(a.split_manifest.resolve()).replace('\\','/'),'split_manifest_sha256':sha(a.split_manifest),'implementation_sha256':source_sha,'registry_sha256':registry_sha,'final_holdout':'UNTOUCHED'}); (a.output/'PROVENANCE_MANIFEST.json').write_text(json.dumps(prov,indent=2,sort_keys=True)+'\n',encoding='utf-8')
receipt={'command':' '.join(sys.argv),'summary':summary,'input_sha256':sha(a.input),'split_manifest_sha256':sha(a.split_manifest),'implementation_sha256':source_sha,'registry_sha256':registry_sha,'final_holdout':'UNTOUCHED'}; (a.output/'RECEIPT.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps(summary,sort_keys=True))