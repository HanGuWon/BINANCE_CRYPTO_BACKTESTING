"""Causal multi-symbol panel assembly for Fast Discovery V2.

This module materializes feature inputs and provenance metadata only. It does
not score predictors, create trades, or access a holdout partition.
"""
from __future__ import annotations

import hashlib

import pandas as pd

from .data import INTERVAL_MS

_BASE_COLUMNS = {"open_time", "close_time", "open", "high", "low", "close", "volume", "symbol"}


def _utc(values: pd.Series, name: str) -> pd.Series:
    result = pd.to_datetime(values, utc=True, errors="raise")
    if result.isna().any():
        raise ValueError(f"{name} cannot contain NaT")
    return result


def _source_hash(frame: pd.DataFrame) -> str:
    ordered = frame.reindex(columns=sorted(frame.columns))
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=True).values.tobytes()).hexdigest()


def _segment_ids(open_time: pd.Series, timeframe: str) -> pd.Series:
    step = pd.Timedelta(milliseconds=INTERVAL_MS[timeframe])
    return (open_time.diff().fillna(step).ne(step).cumsum() + 1).map(lambda value: f"segment-{int(value):04d}")


def _validate_membership(membership: pd.DataFrame) -> pd.DataFrame:
    required = {"market", "universe_month", "symbol", "selected_top50"}
    missing = required - set(membership.columns)
    if missing:
        raise ValueError(f"membership missing columns: {', '.join(sorted(missing))}")
    result = membership.copy()
    result["universe_month"] = pd.to_datetime(result["universe_month"], utc=True, errors="raise").dt.strftime("%Y-%m")
    result["symbol"] = result["symbol"].astype(str)
    result["market"] = result["market"].astype(str)
    if result["selected_top50"].dtype == bool:
        selected = result["selected_top50"]
    else:
        selected = result["selected_top50"].astype(str).str.strip().str.lower().map({"true": True, "false": False, "1": True, "0": False})
    if selected.isna().any():
        raise ValueError("membership selected_top50 contains non-boolean values")
    result["selected_top50"] = selected.astype(bool)
    if result.duplicated(["market", "universe_month", "symbol"]).any():
        raise ValueError("membership contains duplicate market-month-symbol rows")
    if not result["selected_top50"].any():
        raise ValueError("membership has no selected Top50 rows")
    return result


def _join_one_group(left: pd.DataFrame, right: pd.DataFrame, value_columns: list[str], name: str) -> pd.DataFrame:
    merged = pd.merge_asof(
        left.sort_values("close_time", kind="stable"),
        right.sort_values("timestamp", kind="stable"),
        left_on="close_time", right_on="timestamp", direction="backward", allow_exact_matches=True,
    )
    available = merged["timestamp"].where(merged["timestamp"] < merged["next_open_time"])
    for column in value_columns:
        merged[column] = merged[column].where(available.notna())
    merged[f"{name}_source_available_time"] = available
    merged[f"{name}_coverage"] = available.notna().map({True: "AVAILABLE", False: "NO_PRIOR_OBSERVATION"})
    return merged


def _strict_context_join(panel: pd.DataFrame, source: pd.DataFrame, name: str) -> pd.DataFrame:
    if "timestamp" not in source:
        raise ValueError(f"{name} source must contain timestamp")
    keyed = "symbol" in source.columns
    value_columns = [column for column in source.columns if column not in {"timestamp", "symbol"}]
    if not value_columns:
        raise ValueError(f"{name} source has no value columns")
    right = source[["timestamp", *(["symbol"] if keyed else []), *value_columns]].copy()
    right["timestamp"] = _utc(right["timestamp"], f"{name}.timestamp")
    if keyed:
        right["symbol"] = right["symbol"].astype(str)
        if right.duplicated(["symbol", "timestamp"]).any():
            raise ValueError(f"{name} source symbol/timestamps must be unique")
        chunks = []
        for symbol, group in panel.groupby("symbol", sort=False):
            source_group = right[right["symbol"] == symbol].drop(columns="symbol")
            chunk = group.copy()
            if source_group.empty:
                for column in value_columns:
                    chunk[column] = pd.NA
                chunk[f"{name}_source_available_time"] = pd.NaT
                chunk[f"{name}_coverage"] = "NO_PRIOR_OBSERVATION"
            else:
                chunks.append(_join_one_group(chunk, source_group, value_columns, name))
                continue
            chunks.append(chunk)
        return pd.concat(chunks, ignore_index=True).sort_values("__row_id")
    if right["timestamp"].duplicated().any():
        raise ValueError(f"{name} source timestamps must be unique")
    return _join_one_group(panel.copy(), right, value_columns, name).sort_values("__row_id")


def assemble_causal_panel(
    bars: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    market: str,
    timeframe: str,
    premium: pd.DataFrame | None = None,
    funding: pd.DataFrame | None = None,
    holdout_start: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Assemble one symbol panel using frozen monthly Top50 membership.

    Context observations are backward-as-of joined to completed bars and are
    accepted only when their source timestamp is strictly before the next
    executable open. Gaps create new per-symbol segment identities and are
    never filled.
    """
    if market not in {"spot", "um"}:
        raise ValueError("market must be spot or um")
    if timeframe not in INTERVAL_MS:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    missing = _BASE_COLUMNS - set(bars.columns)
    if missing:
        raise ValueError(f"bars missing columns: {', '.join(sorted(missing))}")
    panel = bars.copy().reset_index(drop=True)
    panel["open_time"] = _utc(panel["open_time"], "open_time")
    panel["close_time"] = _utc(panel["close_time"], "close_time")
    panel["symbol"] = panel["symbol"].astype(str)
    panel = panel.sort_values(["symbol", "open_time"], kind="stable").reset_index(drop=True)
    if panel.duplicated(["symbol", "open_time"]).any():
        raise ValueError("bars must have unique symbol/open_time values")
    panel["market"] = market
    panel["timeframe"] = timeframe
    panel["universe_month"] = panel["open_time"].dt.strftime("%Y-%m")
    panel["next_open_time"] = panel["open_time"] + pd.Timedelta(milliseconds=INTERVAL_MS[timeframe])
    panel["segment_id"] = panel.groupby("symbol", sort=False)["open_time"].transform(lambda values: _segment_ids(values, timeframe))
    panel["__row_id"] = range(len(panel))
    if holdout_start is not None:
        cutoff = pd.Timestamp(holdout_start)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        if (panel["open_time"] >= cutoff).any():
            raise ValueError("bars include final holdout rows")
    cohort = _validate_membership(membership)
    cohort_columns = ["market", "universe_month", "symbol", "selected_top50"]
    if "cohort_source_sha256" in cohort:
        cohort_columns.append("cohort_source_sha256")
    panel = panel.merge(cohort[cohort_columns], on=["market", "universe_month", "symbol"], how="left", validate="many_to_one")
    if panel["selected_top50"].isna().any() or (~panel["selected_top50"]).any():
        raise ValueError("no point-in-time Top50 membership for one or more bars")
    panel["selected_top50"] = panel["selected_top50"].astype(bool)
    if "cohort_source_sha256" not in panel:
        panel["cohort_source_sha256"] = "UNSPECIFIED"
    panel["source_available_time"] = pd.NaT
    panel["source_availability_status"] = "BASE_OHLCV"
    for name, source in (("premium", premium), ("funding", funding)):
        if source is not None:
            panel = _strict_context_join(panel, source, name)
    panel = panel.sort_values("__row_id").drop(columns="__row_id").reset_index(drop=True)
    panel.attrs["source_sha256"] = _source_hash(panel)
    panel.attrs["holdout_status"] = "UNTOUCHED"
    panel.attrs["cohort_source_sha256"] = ",".join(sorted(panel["cohort_source_sha256"].astype(str).unique()))
    return panel

