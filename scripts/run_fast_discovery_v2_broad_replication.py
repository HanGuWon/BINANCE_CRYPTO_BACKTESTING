"""Build and run the preregistered Fast Discovery V2.1 broad replication.

This runner is deliberately development-only.  It discovers existing D-backed
UM kline archives, applies the point-in-time Top50 cohort, truncates each lane
at the contract's first holdout open, computes segment-safe features once per
symbol, and emits aggregate B0/B1/B1+I S0 rows.  It never materializes trade
rows or reads final-holdout data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from binance_research.data import deduplicate_klines, load_kline_archive, validate_klines
from binance_research.fast_discovery import screen_s0_panel
from binance_research.features import CoreFeatureEngine, compute_gap_safe_features
from binance_research.fast_discovery import _source_identity


CAMPAIGN_ID = "FAST_DISCOVERY_V2_1_BROAD_REPLICATION_V1"
DEVELOPMENT_START = pd.Timestamp("2020-03-01T00:00:00Z")
MONTH_END = pd.Timestamp("2024-03-01T00:00:00Z")
CUTOFFS = {
    "15m": pd.Timestamp("2024-02-10T00:15:00Z"),
    "1h": pd.Timestamp("2024-02-10T01:00:00Z"),
    "4h": pd.Timestamp("2024-02-10T04:00:00Z"),
}
HORIZONS = {"15m": ("1h", "4h", "24h"), "1h": ("1h", "4h", "24h"), "4h": ("4h", "24h")}
V3_FEATURES = ("donchian_breakout20", "roc6", "rvol20", "vwap_deviation20", "taker_buy_sell_ratio", "cvd_slope6", "bb_bandwidth20", "premium", "premium_zscore90", "relative_strength_24h", "relative_strength_rank", "btc_regime", "top50_breadth")
PILOT_PAIRS = (
    ("donchian_breakout20", "1h"),
    ("donchian_breakout20", "4h"),
    ("roc6", "1h"),
    ("roc6", "4h"),
    ("rvol20", "4h"),
    ("vwap_deviation20", "1h"),
    ("vwap_deviation20", "4h"),
    ("taker_buy_sell_ratio", "4h"),
    ("cvd_slope6", "1h"),
    ("cvd_slope6", "4h"),
    ("cvd_slope6", "24h"),
)


def cohort_membership(universe_path: Path) -> dict[tuple[str, str], bool]:
    """Load the authoritative UM PIT cohort without consulting outcomes."""
    frame = pd.read_csv(universe_path)
    required = {"market", "symbol", "universe_month", "selected_top50"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"cohort missing columns: {', '.join(sorted(missing))}")
    frame = frame.loc[frame["market"].astype(str).eq("um")].copy()
    frame["symbol"] = frame["symbol"].astype(str)
    frame["universe_month"] = frame["universe_month"].astype(str).str[:7]
    if frame.duplicated(["symbol", "universe_month"]).any():
        raise ValueError("cohort has duplicate UM symbol-month rows")
    return {
        (str(row.symbol), str(row.universe_month)): bool(str(row.selected_top50).lower() == "true")
        for row in frame.itertuples(index=False)
    }


def _month_from_name(name: str) -> str | None:
    import re
    match = re.search(r"-(\d{4}-\d{2})(?:\.zip)?$", str(name))
    if not match:
        return None
    month = match.group(1)
    try:
        pd.Timestamp(month + "-01", tz="UTC")
    except ValueError:
        return None
    return month

def discover_archives(raw_root: Path, membership: dict[tuple[str, str], bool], timeframe: str) -> tuple[list[dict[str, object]], list[str]]:
    """Discover all cohort-known archives in the frozen development months."""
    if timeframe not in CUTOFFS:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    rows: list[dict[str, object]] = []
    for symbol_dir in sorted(raw_root.iterdir(), key=lambda p: p.name) if raw_root.is_dir() else []:
        if not symbol_dir.is_dir():
            continue
        key_dir = symbol_dir / timeframe
        if not key_dir.is_dir():
            continue
        for archive in sorted(key_dir.glob("*.zip"), key=lambda p: p.name):
            month = _month_from_name(archive.name)
            if month is None:
                continue
            month_start = pd.Timestamp(month + "-01", tz="UTC")
            if month_start < DEVELOPMENT_START or month_start >= MONTH_END:
                continue
            if (symbol_dir.name, month) not in membership:
                continue
            rows.append(
                {
                    "symbol": symbol_dir.name,
                    "timeframe": timeframe,
                    "universe_month": month,
                    "selected_top50": bool(membership[(symbol_dir.name, month)]),
                    "relative_path": archive.relative_to(raw_root).as_posix(),
                    "size_bytes": int(archive.stat().st_size),
                }
            )
    rows.sort(key=lambda row: (str(row["symbol"]), str(row["timeframe"]), str(row["universe_month"])))
    expected = [
        (symbol, month)
        for (symbol, month), selected in sorted(membership.items())
        if selected
        and DEVELOPMENT_START <= pd.Timestamp(month + "-01", tz="UTC") < MONTH_END
    ]
    found = {(str(row["symbol"]), str(row["universe_month"])) for row in rows}
    missing = [f"{symbol}|{timeframe}|{month}" for symbol, month in expected if (symbol, month) not in found]
    return rows, missing


def archive_list_sha256(rows: Iterable[dict[str, object]]) -> str:
    payload = "\n".join(
        f"{row['relative_path']}|{row['size_bytes']}|{row['selected_top50']}" for row in rows
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_preregistration(
    root: Path,
    *,
    cohort_path: Path,
    cohort_sha256: str,
    registry_sha256: str,
    manifests: dict[str, dict[str, object]],
    source_identity: dict[str, object],
) -> None:
    split = {
        "development_start_utc": DEVELOPMENT_START.isoformat(),
        "development_month_end_exclusive_utc": MONTH_END.isoformat(),
        "first_holdout_open_utc": {key: value.isoformat() for key, value in CUTOFFS.items()},
        "source_timeframe": "native Binance UM kline archive per lane",
        "point_in_time_rule": "bar open_time < lane first holdout open; Top50 selected by same universe_month",
        "calendar_blocks": "UTC calendar month labels emitted by evaluate_walk_forward; independent blocks are unioned",
        "final_holdout": "UNTOUCHED",
    }
    (root / "SPLIT_MANIFEST.json").write_text(json.dumps(split, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    prereg = {
        "campaign_id": CAMPAIGN_ID,
        "status": "PREREGISTERED_DEVELOPMENT_ONLY",
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "development_interval": split,
        "market": "um",
        "timeframes": ["1h", "4h", "15m"],
        "cohort_source": str(cohort_path),
        "cohort_sha256": cohort_sha256,
        "v3_feature_registry": "campaigns/fast_discovery_v2/FEATURE_REGISTRY_V3.csv",
        "v3_feature_registry_sha256": registry_sha256,
        "replication_family_15m": [{"feature_id": feature, "horizon": horizon} for feature, horizon in PILOT_PAIRS],
        "structural_family_1h_4h": list(V3_FEATURES),
        "b0_contract": "baseline-only probability model with causal labels",
        "b1_contract": "baseline model with fixed logistic feature model",
        "b1_plus_i_contract": "baseline plus fixed feature model; paired validation log-loss improvement",
        "minimum_train": 256,
        "validation_size": 128,
        "step_size": 128,
        "promotion_gates": {
            "aggregate_paired_delta_log_loss": "> 0",
            "positive_fold_fraction": "> 0.5",
            "minimum_independent_calendar_blocks": 2,
            "minimum_valid_symbols": 2,
            "maximum_top_symbol_concentration": 0.8,
            "maximum_s0_survivors": 8,
            "deterministic_rerun_parity": "required for any survivor",
        },
        "source_identity": source_identity,
        "archive_manifests": manifests,
        "trade_rows": 0,
        "outcome_access": "NONE",
        "final_holdout": "UNTOUCHED",
    }
    (root / "PREREGISTRATION.json").write_text(json.dumps(prereg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    policy = {
        "policy_id": "FAST_DISCOVERY_V2_1_BROAD_S0_V1",
        "s0_max_survivors": 8,
        "s1_max_combinations": 6,
        "s1_max_survivors": 3,
        "s2_max_finalists": 3,
        "early_stop_if_broad_s0_survivors_zero": True,
        "no_trade_rows_before_s1_s2": True,
        "final_holdout": "UNTOUCHED",
    }
    (root / "SCREENING_POLICY.json").write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def freeze_manifest(raw_root: Path, universe_path: Path, root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    membership = cohort_membership(universe_path)
    cohort_sha = hashlib.sha256(universe_path.read_bytes()).hexdigest()
    registry_path = Path("campaigns/fast_discovery_v2/FEATURE_REGISTRY_V3.csv")
    registry_sha = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    manifests: dict[str, dict[str, object]] = {}
    for timeframe in ("1h", "4h", "15m"):
        rows, missing = discover_archives(raw_root / "um" / "klines", membership, timeframe)
        manifest_path = root / f"SOURCE_ARCHIVE_MANIFEST_{timeframe}.csv"
        with manifest_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["symbol", "timeframe", "universe_month", "selected_top50", "relative_path", "size_bytes"])
            writer.writeheader()
            writer.writerows(rows)
        manifests[timeframe] = {
            "path": str(manifest_path),
            "rows": len(rows),
            "archive_list_sha256": archive_list_sha256(rows),
            "missing_selected_archives": missing,
            "missing_count": len(missing),
        }
    split_path = root / "SPLIT_MANIFEST.json"
    source_identity = _source_identity()
    write_preregistration(root, cohort_path=universe_path, cohort_sha256=cohort_sha, registry_sha256=registry_sha, manifests=manifests, source_identity=source_identity)
    registry_rows = [{"feature_id": feature, "horizon": horizon, "family": "pilot_survivor_15m", "source": "development_screen_um_15m_2024q1_v3"} for feature, horizon in PILOT_PAIRS]
    with (root / "REPLICATION_REGISTRY.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(registry_rows[0]))
        writer.writeheader()
        writer.writerows(registry_rows)
    prereg = json.loads((root / "PREREGISTRATION.json").read_text(encoding="utf-8"))
    prereg["replication_registry_sha256"] = hashlib.sha256((root / "REPLICATION_REGISTRY.csv").read_bytes()).hexdigest()
    prereg["split_manifest_sha256"] = hashlib.sha256(split_path.read_bytes()).hexdigest()
    (root / "PREREGISTRATION.json").write_text(json.dumps(prereg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return prereg


def _read_manifest(path: Path) -> list[dict[str, object]]:
    return [dict(row) for row in csv.DictReader(path.open(encoding="utf-8"))]


def run_lane(raw_root: Path, universe_path: Path, root: Path, timeframe: str) -> dict[str, object]:
    prereg = json.loads((root / "PREREGISTRATION.json").read_text(encoding="utf-8"))
    membership = cohort_membership(universe_path)
    manifest_rows = _read_manifest(root / f"SOURCE_ARCHIVE_MANIFEST_{timeframe}.csv")
    started = time.perf_counter()
    cutoff = CUTOFFS[timeframe]
    frames: dict[str, list[pd.DataFrame]] = {}
    excluded_non_top50_rows = 0
    loaded_rows = 0
    validation_errors: list[dict[str, object]] = []
    missing_files: list[str] = []
    phase = time.perf_counter()
    for row in manifest_rows:
        archive = raw_root / "um" / "klines" / str(row["relative_path"]).replace("/", "\\")
        if not archive.is_file():
            missing_files.append(str(archive))
            continue
        frame = deduplicate_klines(load_kline_archive(archive))
        errors = [issue for issue in validate_klines(frame, timeframe) if issue.severity == "ERROR"]
        if errors:
            validation_errors.append({"path": str(archive), "code": errors[0].code, "count": errors[0].count})
            continue
        frame = frame.loc[(frame["open_time"] >= DEVELOPMENT_START) & (frame["open_time"] < cutoff)].copy()
        if frame.empty:
            continue
        symbol = str(row["symbol"])
        month = str(row["universe_month"])
        selected = bool(str(row["selected_top50"]).lower() == "true") and membership.get((symbol, month), False)
        loaded_rows += int(len(frame))
        if not selected:
            excluded_non_top50_rows += int(len(frame))
            continue
        frame["symbol"] = symbol
        frame["market"] = "um"
        frame["timeframe"] = timeframe
        frame["universe_month"] = month
        frames.setdefault(symbol, []).append(frame)
    source_discovery_seconds = time.perf_counter() - phase
    phase = time.perf_counter()
    enriched_parts: list[pd.DataFrame] = []
    engine = CoreFeatureEngine()
    gap_segments = 0
    symbol_months = 0
    for symbol in sorted(frames):
        bars = pd.concat(frames[symbol], ignore_index=True).sort_values("open_time", kind="stable")
        bars = bars.drop_duplicates("open_time", keep="first").reset_index(drop=True)
        symbol_months += int(bars["universe_month"].nunique())
        features = compute_gap_safe_features(engine, bars, timeframe)
        gap_segments += int(features["segment_id"].nunique()) if "segment_id" in features else 0
        enriched_parts.append(pd.concat([bars, features], axis=1))
    if not enriched_parts:
        raise RuntimeError(f"no selected bars available for {timeframe}")
    enriched = pd.concat(enriched_parts, ignore_index=True)
    feature_seconds = time.perf_counter() - phase
    phase = time.perf_counter()
    if timeframe == "15m":
        primitives = sorted({feature for feature, _ in PILOT_PAIRS})
    else:
        primitives = list(V3_FEATURES)
    complete, rejected, cache = screen_s0_panel(
        enriched,
        timeframe=timeframe,
        horizons=HORIZONS[timeframe],
        primitives=primitives,
        minimum_train=int(prereg["minimum_train"]),
        validation_size=int(prereg["validation_size"]),
        step_size=int(prereg["step_size"]),
        market="um",
        require_multi_symbol=True,
        model_types=("I",),
    )
    scoring_seconds = time.perf_counter() - phase
    if timeframe == "15m":
        allowed = set(PILOT_PAIRS)
        complete = complete.loc[complete.apply(lambda row: (str(row.feature_id), str(row.horizon)) in allowed, axis=1)].copy()
        rejected = complete.loc[complete["status"].ne("S0_SURVIVOR")].copy()
    else:
        rejected = complete.loc[complete["status"].ne("S0_SURVIVOR")].copy()
    lane_root = root / f"broad_{timeframe}"
    lane_root.mkdir(parents=True, exist_ok=True)
    complete.to_csv(lane_root / "S0_BROAD_RESULTS.csv", index=False)
    rejected.to_csv(lane_root / "S0_BROAD_REJECTIONS.csv", index=False)
    complete.to_json(lane_root / "S0_BROAD_RESULTS.json", orient="records", indent=2)
    survivor_count = int((complete["status"] == "S0_SURVIVOR").sum())
    receipt = {
        "campaign_id": CAMPAIGN_ID,
        "scope": "DEVELOPMENT_ONLY",
        "market": "um",
        "timeframe": timeframe,
        "development_start_utc": DEVELOPMENT_START.isoformat(),
        "first_holdout_open_utc": cutoff.isoformat(),
        "rows_loaded_before_cohort_filter": loaded_rows,
        "rows_scored_after_cohort_filter": int(len(enriched)),
        "excluded_non_top50_rows": excluded_non_top50_rows,
        "unique_symbols": int(enriched["symbol"].nunique()),
        "months": sorted(enriched["universe_month"].astype(str).unique().tolist()),
        "symbol_month_count": symbol_months,
        "gap_segments": gap_segments,
        "missing_archive_count": len(missing_files),
        "validation_error_count": len(validation_errors),
        "validation_errors": validation_errors[:20],
        "result_rows": int(len(complete)),
        "rejection_rows": int(len(rejected)),
        "s0_survivors": survivor_count,
        "trade_rows": 0,
        "cache_hits": int(cache.hits),
        "cache_misses": int(cache.misses),
        "benchmark_seconds": {
            "source_discovery_and_load": source_discovery_seconds,
            "feature_compute": feature_seconds,
            "s0_scoring": scoring_seconds,
            "total": time.perf_counter() - started,
        },
        "archive_list_sha256": prereg["archive_manifests"][timeframe]["archive_list_sha256"],
        "cohort_sha256": prereg["cohort_sha256"],
        "registry_sha256": prereg["v3_feature_registry_sha256"],
        "evaluation_model_types": ["I"],
        "evaluation_comparator": "B1 baseline retained internally; I-only rows emitted with exact S0 metric semantics",
        "final_holdout": "UNTOUCHED",
        "historical_r2b_r3_outcomes": "NOT_RUN",
    }
    (lane_root / "DEVELOPMENT_RECEIPT.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("freeze", "run"), required=True)
    parser.add_argument("--raw-root", type=Path, default=Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/raw"))
    parser.add_argument("--universe", type=Path, default=Path("campaigns/r1_gap_safe_cohort_v1/universe_monthly.csv"))
    parser.add_argument("--output", type=Path, default=Path("campaigns/fast_discovery_v2/broad_replication_v1"))
    parser.add_argument("--timeframe", choices=("15m", "1h", "4h"))
    args = parser.parse_args()
    if args.mode == "freeze":
        print(json.dumps(freeze_manifest(args.raw_root, args.universe, args.output), indent=2, sort_keys=True))
        return
    if not args.timeframe:
        raise SystemExit("--timeframe is required with --mode run")
    print(json.dumps(run_lane(args.raw_root, args.universe, args.output, args.timeframe), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()



