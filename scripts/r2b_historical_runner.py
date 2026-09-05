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
import subprocess
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
_PANEL_CACHE: dict[tuple[str, str, str, str], pd.DataFrame] = {}
_FUNDING_CACHE: dict[str, pd.DataFrame] = {}


def derive_execution_segments(panel: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Split execution continuity at source, timestamp, or price boundaries."""
    if timeframe not in STEP:
        raise ValueError(timeframe)
    result = panel.sort_values("timestamp", kind="stable").reset_index(drop=True).copy()
    if result.empty:
        result["execution_segment_id"] = pd.Series(dtype="int64")
        return result
    timestamps = pd.to_datetime(result["timestamp"], utc=True)
    expected = STEP[timeframe]
    original = result["segment_id"].ne(result["segment_id"].shift())
    timestamp_gap = timestamps.diff().ne(expected)
    if "open" in result:
        price = pd.to_numeric(result["open"], errors="coerce").to_numpy(dtype=float)
    else:
        price = np.full(len(result), np.nan, dtype=float)
    unavailable_price = ~np.isfinite(price) | (price <= 0)
    price_boundary = pd.Series(unavailable_price, index=result.index) | pd.Series(unavailable_price, index=result.index).shift(fill_value=False)
    starts = (original | timestamp_gap | price_boundary).astype("int64")
    starts.iloc[0] = 1
    result["execution_segment_id"] = starts.cumsum().astype("int64")
    return result


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


def _source_tree_sha256() -> str:
    digest = hashlib.sha256()
    files = []
    for directory in ("scripts", "src", "tests", "configs"):
        path = ROOT / directory
        if path.exists():
            files.extend(item for item in path.rglob("*") if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc")
    for path in sorted(files, key=lambda item: item.relative_to(ROOT).as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_status_clean() -> bool:
    output = subprocess.run(["git", "status", "--porcelain", "--", "scripts", "src", "tests", "configs"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return not output.strip()


def _launch_identity() -> dict[str, object]:
    manifest = json.loads((CAMPAIGN / "R2B_OUTCOME_LAUNCH_MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("launch_status") != "READY_TO_EXECUTE_PRE_HOLDOUT" or not manifest.get("outcome_run_permitted"):
        raise RuntimeError("R2B launch manifest is not executable")
    if not _git_status_clean():
        raise RuntimeError("scientific source tree is dirty; refusing historical execution")
    source_tree = _source_tree_sha256()
    if source_tree != manifest.get("source_tree_sha256"):
        raise RuntimeError(f"source-tree hash mismatch: {source_tree} != {manifest.get('source_tree_sha256')}")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    implementation = str(manifest.get("implementation_commit", ""))
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", implementation, head], cwd=ROOT)
    if ancestor.returncode != 0:
        raise RuntimeError(f"implementation commit {implementation} is not an ancestor of HEAD {head}")
    return {"implementation_commit": implementation, "head_commit": head, "source_tree_sha256": source_tree, "registry_sha256": str(manifest["registry_sha256"]), "fold_registry_sha256": str(manifest["fold_registry_sha256"]), "causal_root_tree_sha256": str(manifest["causal_root_tree_sha256"]), "launch_commit": str(manifest["launch_commit"])}


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
    if symbol in _FUNDING_CACHE:
        return _FUNDING_CACHE[symbol]
    root = RAW_FUNDING / symbol
    pieces = []
    archive_count = 0
    parse_errors = []
    for path in sorted(root.glob(f"{symbol}-*.zip")):
        archive_count += 1
        try:
            with zipfile.ZipFile(path) as archive:
                name = next(n for n in archive.namelist() if n.endswith(".csv"))
                with archive.open(name) as handle:
                    raw = pd.read_csv(io.TextIOWrapper(handle, encoding="utf-8"))
        except (OSError, KeyError, StopIteration, ValueError) as exc:
            parse_errors.append(f"{path.name}: {exc}")
            continue
        stamp = next((c for c in ("calc_time", "open_time", "timestamp") if c in raw), None)
        rate = next((c for c in ("last_funding_rate", "funding_rate", "close") if c in raw), None)
        if stamp and rate:
            piece = raw[[stamp, rate]].rename(columns={stamp: "timestamp", rate: "funding_rate"})
            piece["timestamp"] = pd.to_datetime(pd.to_numeric(piece.timestamp, errors="coerce"), unit="ms", utc=True)
            pieces.append(piece.dropna(subset=["timestamp"]))
    if not pieces:
        detail = "; ".join(parse_errors[:3]) or "no archives"
        raise RuntimeError(f"funding source unavailable or corrupt for {symbol}: {detail}")
    if parse_errors:
        raise RuntimeError(f"funding source contains corrupt archives for {symbol}: {parse_errors[0]}")
    result = pd.concat(pieces, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    _FUNDING_CACHE[symbol] = result
    return result


def prepare_symbol(symbol: str, timeframe: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    key = (symbol, timeframe, start.isoformat(), end.isoformat())
    if key in _PANEL_CACHE:
        return _PANEL_CACHE[key]
    panel = load_causal_symbol(symbol, timeframe, start, end)
    if panel.empty:
        return panel
    prices = load_raw_klines(symbol, timeframe, start, end)
    result = panel.merge(prices, on="timestamp", how="left", validate="one_to_one").sort_values("timestamp").reset_index(drop=True)
    result = derive_execution_segments(result, timeframe)
    _PANEL_CACHE[key] = result
    return result


def execute_frame(panel: pd.DataFrame, trial: dict[str, object], validation_start: pd.Timestamp, validation_end: pd.Timestamp, funding: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return pd.DataFrame(columns=REQUIRED_TRADE_FIELDS)
    timeframe, side = str(trial["timeframe"]), str(trial["side"])
    horizon = int(trial["horizon_bars"])
    signals = signal_from_frame(panel, str(trial["feature_id"]), str(trial["signal_variant"]), segment_column="execution_segment_id")
    direction = 1.0 if side == "LONG" else -1.0
    funding_times = funding["timestamp"].map(lambda value: pd.Timestamp(value).value).to_numpy(dtype="int64") if len(funding) else np.array([], dtype="int64")
    funding_cumulative = np.cumsum(funding["funding_rate"].astype(float).to_numpy()) if len(funding) else np.array([], dtype=float)
    rows = []
    for _, segment in panel.groupby("execution_segment_id", sort=False):
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
            left = int(np.searchsorted(funding_times, entry_time.value, side="right"))
            right = int(np.searchsorted(funding_times, exit_time.value, side="right"))
            crossed_sum = float(funding_cumulative[right - 1] - (funding_cumulative[left - 1] if left else 0.0)) if right > left else 0.0
            funding_cashflow = -direction * crossed_sum
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
    identity = _launch_identity()
    if checkpoint.exists():
        prior = json.loads(checkpoint.read_text(encoding="utf-8"))
        trade_path = out_root / "trades" / f"{unit_id}.parquet"
        if prior.get("implementation_commit") != identity["implementation_commit"] or prior.get("source_tree_sha256") != identity["source_tree_sha256"] or not trade_path.exists() or hashlib.sha256(trade_path.read_bytes()).hexdigest() != prior.get("trade_file_sha256"):
            raise RuntimeError(f"stale or mismatched checkpoint: {unit_id}")
        existing = pd.read_parquet(trade_path)
        if set(REQUIRED_TRADE_FIELDS) != set(existing.columns) or len(existing) != int(prior.get("executed_trades", -1)):
            raise RuntimeError(f"invalid checkpoint trade schema/count: {unit_id}")
        return prior
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
    result = {"unit_id": unit_id, "fold_id": fold["fold_id"], "trial_id": trial["trial_id"], "timeframe": trial["timeframe"], "horizon_bars": int(trial["horizon_bars"]), "side": trial["side"], "feature_id": trial["feature_id"], "signal_variant": trial["signal_variant"], "status": status, "executed_trades": int(len(trades)), "eligible_rows": int(eligible), "trade_file_sha256": hashlib.sha256(trade_path.read_bytes()).hexdigest(), "implementation_commit": identity["implementation_commit"], "source_tree_sha256": identity["source_tree_sha256"], "holdout_status": "UNTOUCHED", "january_2024_rows": 0}
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
    parser.add_argument("--fold-id", help="run all 72 trials for one frozen fold")
    parser.add_argument("--finalize", action="store_true", help="write the run manifest from all terminal checkpoints")
    args = parser.parse_args()
    identity = _launch_identity()
    trials, folds = load_registry()
    fold_map = {(str(row["fold_id"]), str(row["timeframe"]), int(row["horizon_bars"])): row for row in folds}
    trial_map = {str(row["trial_id"]): row for row in trials}
    if args.unit:
        fold_id, trial_id = args.unit.split("__", 1)
        trial = trial_map[trial_id]
        result = run_unit(trial, fold_map[(fold_id, str(trial["timeframe"]), int(trial["horizon_bars"]))], out_root=args.out_root)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.finalize:
        expected = {(fold_id, str(trial["trial_id"])) for fold_id in sorted(set(str(row["fold_id"]) for row in folds)) for trial in trials}
        results = []
        for fold_id, trial_id in sorted(expected):
            path = args.out_root / "units" / f"{fold_id}__{trial_id}.json"
            if not path.exists():
                raise RuntimeError(f"missing terminal unit {fold_id}__{trial_id}")
            results.append(json.loads(path.read_text(encoding="utf-8")))
        manifest = {"campaign_id": "r2b_restricted_derivatives_v1", "outcome_run_started": True, "final_holdout_status": "UNTOUCHED", "unit_count": len(results), "status_counts": pd.Series([r["status"] for r in results]).value_counts().to_dict(), "implementation_commit": identity["implementation_commit"], "head_commit": identity["head_commit"], "source_tree_sha256": identity["source_tree_sha256"], "registry_sha256": identity["registry_sha256"], "fold_registry_sha256": identity["fold_registry_sha256"], "causal_root_tree_sha256": identity["causal_root_tree_sha256"], "units": results}
        _atomic_json(args.out_root / "run_manifest.json", manifest)
        print(json.dumps({"unit_count": len(results), "status_counts": manifest["status_counts"], "final_holdout_status": "UNTOUCHED"}, sort_keys=True))
        return 0
    results = []
    fold_ids = [args.fold_id] if args.fold_id else sorted(set(str(row["fold_id"]) for row in folds))
    for fold_id in fold_ids:
        for trial in trials:
            fold = fold_map[(fold_id, str(trial["timeframe"]), int(trial["horizon_bars"]))]
            results.append(run_unit(trial, fold, out_root=args.out_root))
    manifest = {"campaign_id": "r2b_restricted_derivatives_v1", "outcome_run_started": True, "final_holdout_status": "UNTOUCHED", "unit_count": len(results), "status_counts": pd.Series([r["status"] for r in results]).value_counts().to_dict(), "implementation_commit": identity["implementation_commit"], "head_commit": identity["head_commit"], "source_tree_sha256": identity["source_tree_sha256"], "registry_sha256": identity["registry_sha256"], "fold_registry_sha256": identity["fold_registry_sha256"], "causal_root_tree_sha256": identity["causal_root_tree_sha256"], "units": results}
    _atomic_json(args.out_root / "run_manifest.json", manifest)
    print(json.dumps({"unit_count": len(results), "status_counts": manifest["status_counts"], "final_holdout_status": "UNTOUCHED"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
