"""Dedicated, resume-safe R2B historical pre-holdout executor.

This module is intentionally separate from the R2A engine.  It consumes only
the frozen R2B causal premium root and raw UM klines/funding archives, applies
the exact fold registry, and writes one atomic checkpoint per trial-fold unit.
No final-holdout or January-2024 rows are eligible by construction.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from r2b_signals import signal_from_frame, side_accepts_signal

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA")
CAUSAL_ROOT = DATA_ROOT / "processed" / "r2b_restricted_derivatives_v1_repaired_v2_causal3"
RAW_KLINES = DATA_ROOT / "raw" / "um" / "klines"
RAW_FUNDING = DATA_ROOT / "raw" / "um" / "fundingRate"
CAMPAIGN = ROOT / "campaigns" / "r2b_restricted_derivatives_v1"
STEP = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}
HOLDOUT = pd.Timestamp("2024-02-10T00:00:00Z")
JANUARY_2024 = pd.Timestamp("2024-01-01T00:00:00Z")
REQUIRED_TRADE_FIELDS = (
    "decision_time", "symbol", "side", "signal_variant", "signal_value",
    "source_open_time", "source_available_time", "entry_time", "exit_time",
    "gross_return", "funding_cashflow", "net_return",
)
KLINE_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _read_parquet(path: Path) -> pd.DataFrame:
    return pq.ParquetFile(path).read().to_pandas()


def load_causal_symbol(symbol: str, timeframe: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Load one symbol/timeframe from the repaired root, strictly pre-holdout."""
    if timeframe not in STEP:
        raise ValueError(timeframe)
    paths = sorted((CAUSAL_ROOT / f"market=um/symbol={symbol}/timeframe={timeframe}").glob("year=*/part-000.parquet"))
    pieces = []
    for path in paths:
        frame = _read_parquet(path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame[(frame.timestamp >= start) & (frame.timestamp < end) & (frame.timestamp < JANUARY_2024)]
        if len(frame):
            pieces.append(frame)
    if not pieces:
        return pd.DataFrame()
    frame = pd.concat(pieces, ignore_index=True).sort_values("timestamp", kind="stable").drop_duplicates("timestamp")
    frame = frame[frame.row_class.eq("RESEARCH_ELIGIBLE")].reset_index(drop=True)
    frame["source_open_time"] = pd.to_datetime(frame["premium_source_timestamp"], utc=True)
    frame["source_available_time"] = pd.to_datetime(frame["premium_source_available_time"], utc=True)
    if (frame.source_available_time >= frame.timestamp + STEP[timeframe]).any():
        raise RuntimeError(f"causal availability violation: {symbol}/{timeframe}")
    return frame


def load_raw_klines(symbol: str, timeframe: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    root = RAW_KLINES / symbol / timeframe
    pieces = []
    for path in sorted(root.glob(f"{symbol}-{timeframe}-*.zip")):
        try:
            with zipfile.ZipFile(path) as archive:
                name = next(n for n in archive.namelist() if n.endswith(".csv"))
                with archive.open(name) as handle:
                    raw = pd.read_csv(handle)
                    if "open_time" not in raw.columns:
                        handle.seek(0)
                        raw = pd.read_csv(handle, header=None, names=KLINE_COLUMNS)
        except (OSError, KeyError, StopIteration, ValueError):
            continue
        raw["timestamp"] = pd.to_datetime(raw["open_time"], unit="ms", utc=True)
        raw = raw[(raw.timestamp >= start) & (raw.timestamp < end)]
        if len(raw):
            pieces.append(raw[["timestamp", "open"]])
    if not pieces:
        return pd.DataFrame(columns=["timestamp", "open"])
    return pd.concat(pieces, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")


def load_funding(symbol: str) -> pd.DataFrame:
    root = RAW_FUNDING / symbol
    pieces = []
    for path in sorted(root.glob(f"{symbol}-*.zip")):
        try:
            with zipfile.ZipFile(path) as archive:
                name = next(n for n in archive.namelist() if n.endswith(".csv"))
                with archive.open(name) as handle:
                    raw = pd.read_csv(io.TextIOWrapper(handle, encoding="utf-8"))
        except (OSError, KeyError, StopIteration, ValueError):
            continue
        stamp = next((c for c in ("calc_time", "open_time", "timestamp") if c in raw), None)
        rate = next((c for c in ("last_funding_rate", "funding_rate", "close") if c in raw), None)
        if stamp and rate:
            piece = raw[[stamp, rate]].rename(columns={stamp: "timestamp", rate: "funding_rate"})
            piece["timestamp"] = pd.to_datetime(pd.to_numeric(piece.timestamp, errors="coerce"), unit="ms", utc=True)
            pieces.append(piece.dropna(subset=["timestamp"]))
    if not pieces:
        return pd.DataFrame(columns=["timestamp", "funding_rate"])
    return pd.concat(pieces, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


def prepare_symbol(symbol: str, timeframe: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    panel = load_causal_symbol(symbol, timeframe, start, end)
    if panel.empty:
        return panel
    prices = load_raw_klines(symbol, timeframe, start, end)
    return panel.merge(prices, on="timestamp", how="left", validate="one_to_one").sort_values("timestamp").reset_index(drop=True)


def execute_frame(panel: pd.DataFrame, trial: dict[str, object], validation_start: pd.Timestamp, validation_end: pd.Timestamp, funding: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return pd.DataFrame(columns=REQUIRED_TRADE_FIELDS)
    timeframe, side = str(trial["timeframe"]), str(trial["side"])
    horizon = int(trial["horizon_bars"])
    signals = signal_from_frame(panel, str(trial["feature_id"]), str(trial["signal_variant"]), segment_column="segment_id")
    direction = 1.0 if side == "LONG" else -1.0
    rows = []
    for _, segment in panel.groupby("segment_id", sort=False):
        positions = segment.index.to_list()
        next_available = -1
        for local, pos in enumerate(positions):
            decision_time = panel.at[pos, "timestamp"]
            if decision_time < validation_start or decision_time >= validation_end or local <= next_available:
                continue
            raw = signals.iloc[pos]
            if not side_accepts_signal(float(raw) if pd.notna(raw) else np.nan, side):
                continue
            entry_local, exit_local = local + 1, local + horizon + 1
            if exit_local >= len(positions):
                continue
            entry_pos, exit_pos = positions[entry_local], positions[exit_local]
            entry_open, exit_open = panel.at[entry_pos, "open"], panel.at[exit_pos, "open"]
            if not np.isfinite(entry_open) or not np.isfinite(exit_open) or float(entry_open) <= 0:
                continue
            entry_time, exit_time = panel.at[entry_pos, "timestamp"], panel.at[exit_pos, "timestamp"]
            crossed = funding[(funding.timestamp > entry_time) & (funding.timestamp <= exit_time)]
            funding_cashflow = -direction * float(crossed.funding_rate.sum())
            gross = direction * (float(exit_open) / float(entry_open) - 1.0)
            rows.append({
                "decision_time": decision_time, "symbol": str(panel.at[pos, "symbol"]), "side": side,
                "signal_variant": str(trial["signal_variant"]), "signal_value": float(raw),
                "source_open_time": panel.at[pos, "source_open_time"], "source_available_time": panel.at[pos, "source_available_time"],
                "entry_time": entry_time, "exit_time": exit_time, "gross_return": gross,
                "funding_cashflow": funding_cashflow, "net_return": gross - 0.002 + funding_cashflow,
            })
            next_available = exit_local
    return pd.DataFrame(rows, columns=REQUIRED_TRADE_FIELDS)


def run_unit(trial: dict[str, object], fold: dict[str, object], *, out_root: Path, symbols: list[str] | None = None) -> dict[str, object]:
    unit_id = f"{fold['fold_id']}__{trial['trial_id']}"
    checkpoint = out_root / "units" / f"{unit_id}.json"
    if checkpoint.exists():
        return json.loads(checkpoint.read_text(encoding="utf-8"))
    validation_start = pd.Timestamp(fold["validation_start_utc"])
    validation_end = pd.Timestamp(fold["validation_end_exclusive_utc"])
    history_start = validation_start - pd.Timedelta(days=370)
    universe = pd.read_csv(CAMPAIGN.parent / "r1_final_panel_v1" / "universe_monthly.csv")
    selected = universe[(universe.market == "um") & (universe.selected_top50 == True) & (pd.to_datetime(universe.universe_month + "-01", utc=True) < validation_end) & (pd.to_datetime(universe.universe_month + "-01", utc=True) >= history_start)]
    selected_symbols = sorted(set(selected.symbol.astype(str))) if symbols is None else sorted(set(symbols))
    all_trades = []
    eligible = 0
    for symbol in selected_symbols:
        frame = prepare_symbol(symbol, str(trial["timeframe"]), history_start, validation_end)
        if frame.empty:
            continue
        eligible += len(frame)
        all_trades.append(execute_frame(frame, trial, validation_start, validation_end, load_funding(symbol)))
    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame(columns=REQUIRED_TRADE_FIELDS)
    status = "VALID" if len(trades) >= int(fold.get("minimum_trades", 30)) else "INSUFFICIENT_TRADES"
    trade_path = out_root / "trades" / f"{unit_id}.parquet"
    trade_path.parent.mkdir(parents=True, exist_ok=True)
    trades.to_parquet(trade_path, index=False)
    result = {"unit_id": unit_id, "fold_id": fold["fold_id"], "trial_id": trial["trial_id"], "status": status, "executed_trades": int(len(trades),), "eligible_rows": int(eligible), "trade_file_sha256": hashlib.sha256(trade_path.read_bytes()).hexdigest(), "holdout_status": "UNTOUCHED", "january_2024_rows": 0}
    _atomic_json(checkpoint, result)
    return result


def load_registry() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    trials = pd.read_csv(CAMPAIGN / "trial_registry.csv").to_dict("records")
    folds = pd.read_csv(CAMPAIGN / "fold_registry.csv").to_dict("records")
    if len(trials) != 72 or len(set(str(row["fold_id"]) for row in folds)) != 8:
        raise RuntimeError("R2B registry/fold contract is not exact")
    return trials, folds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--unit", help="run one F01__R2B0001 unit; omit for all 576")
    args = parser.parse_args()
    trials, folds = load_registry()
    fold_map = {(str(row["fold_id"]), str(row["timeframe"]), int(row["horizon_bars"])): row for row in folds}
    trial_map = {str(row["trial_id"]): row for row in trials}
    if args.unit:
        fold_id, trial_id = args.unit.split("__", 1)
        trial = trial_map[trial_id]
        result = run_unit(trial, fold_map[(fold_id, str(trial["timeframe"]), int(trial["horizon_bars"]))], out_root=args.out_root)
        print(json.dumps(result, sort_keys=True))
        return 0
    results = []
    for fold_id in sorted(set(str(row["fold_id"]) for row in folds)):
        for trial in trials:
            fold = fold_map[(fold_id, str(trial["timeframe"]), int(trial["horizon_bars"]))]
            results.append(run_unit(trial, fold, out_root=args.out_root))
    manifest = {"campaign_id": "r2b_restricted_derivatives_v1", "outcome_run_started": True, "final_holdout_status": "UNTOUCHED", "unit_count": len(results), "status_counts": pd.Series([r["status"] for r in results]).value_counts().to_dict(), "units": results}
    _atomic_json(args.out_root / "run_manifest.json", manifest)
    print(json.dumps({"unit_count": len(results), "status_counts": manifest["status_counts"], "final_holdout_status": "UNTOUCHED"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
