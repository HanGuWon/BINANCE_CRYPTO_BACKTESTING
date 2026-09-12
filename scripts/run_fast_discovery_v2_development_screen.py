"""Run a bounded, development-only Fast Discovery V2 S0 screen."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from binance_research.data import deduplicate_klines, load_kline_archive, validate_klines
from binance_research.fast_discovery import DEFAULT_PRIMITIVES, screen_s0
from binance_research.features import CoreFeatureEngine


def _horizons(timeframe: str) -> tuple[str, ...]:
    valid = {"15m": ("1h", "4h", "24h"), "1h": ("1h", "4h", "24h"), "4h": ("4h", "24h")}
    return valid[timeframe]


def load_window(raw_root: Path, symbols: list[str], timeframe: str, months: list[str]) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    archives: list[str] = []
    for symbol in symbols:
        for month in months:
            archive = raw_root / "um" / "klines" / symbol / timeframe / f"{symbol}-{timeframe}-{month}.zip"
            if not archive.is_file():
                raise FileNotFoundError(archive)
            frame = deduplicate_klines(load_kline_archive(archive))
            issues = validate_klines(frame, timeframe)
            errors = [issue for issue in issues if issue.severity == "ERROR"]
            if errors:
                raise ValueError(f"archive integrity failure: {archive}: {errors[0].code}")
            frame["symbol"] = symbol
            frame["segment_id"] = f"{symbol}-window"
            frames.append(frame)
            archives.append(str(archive))
    return pd.concat(frames, ignore_index=True).sort_values(["symbol", "open_time"]).reset_index(drop=True), archives


def run(*, raw_root: Path, output: Path, symbols: list[str], timeframe: str, months: list[str]) -> dict[str, object]:
    bars, archives = load_window(raw_root, symbols, timeframe, months)
    engine = CoreFeatureEngine()
    results: list[pd.DataFrame] = []
    rejected: list[pd.DataFrame] = []
    for symbol, group in bars.groupby("symbol", sort=True):
        features = engine.compute(group.reset_index(drop=True))
        enriched = pd.concat([group.reset_index(drop=True), features], axis=1)
        scored, dropped = screen_s0(enriched, timeframe=timeframe, horizons=_horizons(timeframe), primitives=DEFAULT_PRIMITIVES, minimum_train=256, validation_size=128, step_size=128, market="um")
        if not scored.empty:
            scored.insert(0, "symbol", symbol)
            results.append(scored)
        if not dropped.empty:
            dropped.insert(0, "symbol", symbol)
            rejected.append(dropped)
    output.mkdir(parents=True, exist_ok=True)
    pd.concat(results, ignore_index=True).to_csv(output / "S0_DEVELOPMENT_RESULTS.csv", index=False) if results else pd.DataFrame().to_csv(output / "S0_DEVELOPMENT_RESULTS.csv", index=False)
    pd.concat(rejected, ignore_index=True).to_csv(output / "S0_DEVELOPMENT_REJECTIONS.csv", index=False) if rejected else pd.DataFrame().to_csv(output / "S0_DEVELOPMENT_REJECTIONS.csv", index=False)
    archive_hash = hashlib.sha256("\n".join(archives).encode()).hexdigest()
    receipt = {"protocol": "FAST_DISCOVERY_V2", "scope": "DEVELOPMENT_ONLY", "market": "um", "timeframe": timeframe, "symbols": symbols, "months": months, "rows": int(len(bars)), "archives": archives, "archive_list_sha256": archive_hash, "primitives": list(DEFAULT_PRIMITIVES), "trade_rows": 0, "final_holdout": "UNTOUCHED", "r3_outcomes": "NOT_ACCESSED"}
    (output / "DEVELOPMENT_SCREEN_RECEIPT.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/raw"))
    parser.add_argument("--output", type=Path, default=Path("campaigns/fast_discovery_v2/development_screen_um_2023q4"))
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--symbols", nargs="+", default=["1000BONKUSDT", "1000MOGUSDT"])
    parser.add_argument("--months", nargs="+", default=["2023-11", "2023-12", "2024-01", "2024-02"])
    args = parser.parse_args()
    print(json.dumps(run(raw_root=args.raw_root, output=args.output, symbols=args.symbols, timeframe=args.timeframe, months=args.months), sort_keys=True))

