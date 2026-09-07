'''Permanent feature-coverage audit for materialized research panels.

The audit answers one question per exact feature x market x timeframe: how
many RESEARCH_ELIGIBLE rows carry a finite value, and when did finite values
start and end. Denominators and finite counts are restricted to the same row
class, so warmup/context rows can never inflate coverage.
'''
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


# Frozen registry feature IDs mapped to their materialized panel columns.
BASE_FEATURE_COLUMNS = {
    "trend.ema_20_50_spread": "ema20_50_spread",
    "trend.ema_50_200_regime": "ema50_200_regime",
    "trend.ema_slope": "ema20_slope_5",
    "trend.adx_dmi": "adx14",
    "trend.kaufman_er": "kaufman_er10",
    "trend.donchian": "donchian_range_pos20",
    "momentum.roc": "roc24",
    "momentum.rsi": "rsi14",
    "volatility.atr_natr": "natr14",
    "volatility.bollinger_bandwidth": "bb_bandwidth20",
    "volatility.realized_percentile": "realized_vol_percentile100",
    "volume.rvol": "rvol20",
    "volume.vwap_deviation": "vwap_deviation20",
    "orderflow.taker_ratio": "taker_buy_sell_ratio",
    "orderflow.cvd": "cvd_slope6",
    "microstructure.spread": "spread_bps",
    "microstructure.top_book_imbalance": "top_book_imbalance",
    "derivatives.oi_change": "oi_pct_change",
    "context.btc_regime": "btc_regime",
    "context.market_breadth": "market_breadth",
}

# Raw event/series inputs are audited independently from their z-scores.
# UM merge suffix variants are accepted because the final panel stores the
# joined context columns with merge suffixes.
DERIVATIVE_FEATURE_COLUMNS = {
    "derivatives.funding": ("funding_rate",),
    "derivatives.funding_zscore": ("funding_zscore90_y", "funding_zscore90"),
    "derivatives.premium": ("premium",),
    "derivatives.premium_zscore": ("premium_zscore90_y", "premium_zscore90"),
}

UM_ONLY_DERIVATIVES = {
    "derivatives.funding",
    "derivatives.funding_zscore",
    "derivatives.premium",
    "derivatives.premium_zscore",
}

CLASSIFICATION_R2A_PRIMARY = "R2A_PRIMARY"
CLASSIFICATION_R2B_RESTRICTED = "R2B_RESTRICTED"
CLASSIFICATION_FORWARD_SHADOW = "FORWARD_SHADOW"
CLASSIFICATION_NOT_APPLICABLE = "NOT_APPLICABLE"
 
 
def classify_structural_coverage(finite_rows, coverage_fraction, *, primary_threshold=0.80):
    """Classify from structural materialization only, never performance."""
    if finite_rows <= 0:
        return CLASSIFICATION_FORWARD_SHADOW
    if coverage_fraction >= primary_threshold:
        return CLASSIFICATION_R2A_PRIMARY
    return CLASSIFICATION_R2B_RESTRICTED


def candidate_columns(feature_id, market):
    if feature_id in DERIVATIVE_FEATURE_COLUMNS:
        if market != "um" and feature_id in UM_ONLY_DERIVATIVES:
            return ()
        return DERIVATIVE_FEATURE_COLUMNS[feature_id]
    column = BASE_FEATURE_COLUMNS.get(feature_id)
    return (column,) if column else ()


def registered_feature_ids():
    ordered = list(BASE_FEATURE_COLUMNS)
    ordered.extend(DERIVATIVE_FEATURE_COLUMNS)
    return ordered


def audit_feature_coverage(
    root,
    *,
    markets=("spot", "um"),
    timeframes=("15m", "1h", "4h"),
    row_class="RESEARCH_ELIGIBLE",
    primary_threshold=0.80,
    workers=8,
):
    """Audit every registered feature on materialized gap-safe partitions.

    Both the denominator and the finite count use only rows whose
    ``row_class`` equals the requested class. Features whose columns are not
    materialized (or are entirely non-finite inside the class) are reported
    with zero finite rows and classified FORWARD_SHADOW.
    """
    root = Path(root)
    rows = []
    for market in markets:
        for timeframe in timeframes:
            pattern_root = root / ("market=" + market)
            paths = sorted(pattern_root.glob("symbol=*/timeframe=" + timeframe + "/year=*/part-000.parquet"))
            feature_ids = [fid for fid in registered_feature_ids() if candidate_columns(fid, market)]
            totals = {fid: {"finite": 0, "first": pd.NaT, "last": pd.NaT} for fid in feature_ids}
            eligible_total = 0

            def scan(path, _market=market, _feature_ids=tuple(feature_ids), _row_class=row_class):
                parquet = pq.ParquetFile(path)
                schema_names = set(parquet.schema_arrow.names)
                wanted = [
                    fid for fid in _feature_ids
                    if any(column in schema_names for column in candidate_columns(fid, _market))
                ]
                columns = ["timestamp", "row_class"]
                columns.extend(sorted({column for fid in wanted for column in candidate_columns(fid, _market) if column in schema_names}))
                frame = parquet.read(columns=sorted(set(columns))).to_pandas()
                stamps = pd.to_datetime(frame["timestamp"], utc=True)
                eligible_mask = frame["row_class"] == _row_class
                local = {}
                for feature_id in wanted:
                    column = next(column for column in candidate_columns(feature_id, _market) if column in frame.columns)
                    finite_mask = eligible_mask & frame[column].notna()
                    if bool(finite_mask.any()):
                        local[feature_id] = (int(finite_mask.sum()), stamps[finite_mask].min(), stamps[finite_mask].max())
                    else:
                        local[feature_id] = (0, pd.NaT, pd.NaT)
                return int(eligible_mask.sum()), local

            if paths:
                with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
                    for eligible_count, local in pool.map(scan, paths):
                        eligible_total += eligible_count
                        for feature_id, (finite_count, first, last) in local.items():
                            bucket = totals[feature_id]
                            bucket["finite"] += finite_count
                            first = pd.Timestamp(first)
                            last = pd.Timestamp(last)
                            bucket["first"] = first if pd.isna(bucket["first"]) else min(bucket["first"], first)
                            bucket["last"] = last if pd.isna(bucket["last"]) else max(bucket["last"], last)

            for feature_id in feature_ids:
                bucket = totals[feature_id]
                finite_rows = int(bucket["finite"])
                coverage = float(finite_rows / eligible_total) if eligible_total else float("nan")
                rows.append({
                    "feature": feature_id,
                    "market": market,
                    "timeframe": timeframe,
                    "research_eligible_rows": eligible_total,
                    "finite_rows": finite_rows,
                    "coverage_fraction": round(coverage, 6) if np.isfinite(coverage) else np.nan,
                    "first_finite_timestamp": pd.Timestamp(bucket["first"]).isoformat() if not pd.isna(bucket["first"]) else "",
                    "last_finite_timestamp": pd.Timestamp(bucket["last"]).isoformat() if not pd.isna(bucket["last"]) else "",
                    "classification": (
                        classify_structural_coverage(finite_rows, coverage, primary_threshold=primary_threshold)
                        if eligible_total else CLASSIFICATION_NOT_APPLICABLE
                    ),
                    "reason": (
                        "research_eligible_denominator_independent_audit"
                        if finite_rows > 0 else "NOT_MATERIALIZED_FOR_RESEARCH_ROWS"
                    ),
                })
    return pd.DataFrame(rows)
