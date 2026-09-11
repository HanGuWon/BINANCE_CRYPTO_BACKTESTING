from pathlib import Path
import argparse, pandas as pd
from binance_research.fast_discovery import run_campaign
parser=argparse.ArgumentParser(); parser.add_argument("--input",type=Path,required=True); parser.add_argument("--output",type=Path,required=True); parser.add_argument("--timeframe",default="1h")
args=parser.parse_args()
frame=pd.read_parquet(args.input, columns=None)
print(run_campaign(frame,args.output,timeframe=args.timeframe))
