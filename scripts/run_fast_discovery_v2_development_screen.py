"""Run a bounded, development-only Fast Discovery V2 S0 screen."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from binance_research.data import deduplicate_klines, load_kline_archive, validate_klines
from binance_research.fast_discovery import DEFAULT_PRIMITIVES, screen_s0_panel
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




def attach_causal_membership(bars: pd.DataFrame, universe_path: Path, *, market: str) -> tuple[pd.DataFrame, int, str]:
    """Filter bars to prior-month Top50 membership and return exclusion audit facts."""
    if not universe_path.is_file():
        raise FileNotFoundError(universe_path)
    membership = pd.read_csv(universe_path)
    required = {"market", "symbol", "universe_month", "selected_top50"}
    missing = required - set(membership.columns)
    if missing:
        raise ValueError(f"universe membership missing columns: {', '.join(sorted(missing))}")
    if membership.duplicated(["market", "symbol", "universe_month"]).any():
        raise ValueError("universe membership is not unique")
    membership["market"] = membership["market"].astype(str)
    membership["symbol"] = membership["symbol"].astype(str)
    membership["universe_month"] = membership["universe_month"].astype(str)
    membership = membership.loc[membership["market"].eq(str(market))].copy()
    digest = hashlib.sha256(universe_path.read_bytes()).hexdigest()
    frame = bars.copy()
    frame["universe_month"] = pd.to_datetime(frame["open_time"], utc=True).dt.strftime("%Y-%m")
    frame = frame.merge(membership[["market", "symbol", "universe_month", "selected_top50"]], on=["symbol", "universe_month"], how="left", validate="many_to_one")
    if frame["selected_top50"].isna().any():
        raise ValueError("bar has no point-in-time cohort membership")
    frame["selected_top50"] = frame["selected_top50"].astype(bool)
    excluded = int((~frame["selected_top50"]).sum())
    frame = frame.loc[frame["selected_top50"]].reset_index(drop=True)
    frame["market"] = str(market)
    return frame, excluded, digest
def run(*, raw_root: Path, output: Path, symbols: list[str], timeframe: str, months: list[str], universe_path: Path) -> dict[str, object]:
    bars, archives = load_window(raw_root, symbols, timeframe, months)
    bars, excluded_non_top50_rows, cohort_sha256 = attach_causal_membership(bars, universe_path, market="um")
    engine = CoreFeatureEngine()
    enriched_parts: list[pd.DataFrame] = []
    for _, group in bars.groupby("symbol", sort=True):
        features = engine.compute(group.reset_index(drop=True))
        enriched_parts.append(pd.concat([group.reset_index(drop=True), features], axis=1))
    enriched = pd.concat(enriched_parts, ignore_index=True)
    complete, dropped, _ = screen_s0_panel(enriched, timeframe=timeframe, horizons=_horizons(timeframe), primitives=DEFAULT_PRIMITIVES, minimum_train=256, validation_size=128, step_size=128, market="um")
    results = complete
    rejected = dropped
    output.mkdir(parents=True, exist_ok=True)
    results.to_csv(output / "S0_DEVELOPMENT_RESULTS.csv", index=False)
    rejected.to_csv(output / "S0_DEVELOPMENT_REJECTIONS.csv", index=False)
    archive_hash = hashlib.sha256("\n".join(archives).encode()).hexdigest()
    receipt = {"protocol": "FAST_DISCOVERY_V2", "scope": "DEVELOPMENT_ONLY", "market": "um", "timeframe": timeframe, "symbols": symbols, "months": months, "rows": int(len(bars)), "excluded_non_top50_rows": excluded_non_top50_rows, "cohort_source": str(universe_path), "cohort_sha256": cohort_sha256, "archives": archives, "archive_list_sha256": archive_hash, "primitives": list(DEFAULT_PRIMITIVES), "horizons": list(_horizons(timeframe)), "trade_rows": 0, "final_holdout": "UNTOUCHED", "r3_outcomes": "NOT_ACCESSED"}
    (output / "DEVELOPMENT_SCREEN_RECEIPT.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, default=Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/raw"))
    parser.add_argument("--output", type=Path, default=Path("campaigns/fast_discovery_v2/development_screen_um_2023q4"))
    parser.add_argument("--universe", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1/universe_monthly.csv"))
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--symbols", nargs="+", default=["1000BONKUSDT", "1000MOGUSDT"])
    parser.add_argument("--months", nargs="+", default=["2023-11", "2023-12", "2024-01", "2024-02"])
    args = parser.parse_args()
    print(json.dumps(run(raw_root=args.raw_root, output=args.output, symbols=args.symbols, timeframe=args.timeframe, months=args.months, universe_path=args.universe), sort_keys=True))

