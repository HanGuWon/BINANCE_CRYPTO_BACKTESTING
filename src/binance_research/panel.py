"""Causal historical-panel utilities for the R1 research campaign.

The module deliberately contains metadata and panel-construction primitives only.
It does not compute returns, rank indicators, or access a final holdout.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from .data import DataIntegrityError, INTERVAL_MS, resample_klines
from .features import CORE_FEATURE_SPECS

PANEL_COVERAGE_STATUSES = (
    "AVAILABLE",
    "PARTIAL",
    "STALE",
    "NO_PRIOR_OBSERVATION",
    "HISTORICAL_UNAVAILABLE",
)


def select_verified_causal_liquidity_universe(
    monthly_volume: pd.DataFrame,
    *,
    top_n: int = 50,
    minimum_coverage_ratio: float = 1.0,
) -> pd.DataFrame:
    """Validate prior-month provenance and rank independently by market.

    R1.6+ cohort construction should use this wrapper rather than relying on a
    column merely named ``prior_month_quote_volume``. ``volume_month`` must be
    exactly one calendar month before ``universe_month`` for every row.
    """
    required = {"market", "universe_month", "volume_month", "symbol", "prior_month_quote_volume", "first_observed"}
    missing = required - set(monthly_volume.columns)
    if missing:
        raise ValueError(f"missing verified-universe columns: {', '.join(sorted(missing))}")
    if not 0 < minimum_coverage_ratio <= 1:
        raise ValueError("minimum_coverage_ratio must be in (0, 1]")
    frame = monthly_volume.copy()
    if frame["market"].isna().any() or frame["market"].astype(str).str.len().eq(0).any():
        raise ValueError("market must be explicit for every liquidity-universe row")
    universe_period = pd.to_datetime(frame["universe_month"], utc=True).dt.tz_convert(None).dt.to_period("M")
    volume_period = pd.to_datetime(frame["volume_month"], utc=True).dt.tz_convert(None).dt.to_period("M")
    if not volume_period.eq(universe_period - 1).all():
        raise ValueError("volume_month must be the immediately preceding calendar month")
    frame["universe_month"] = universe_period.astype(str)
    frame["volume_month"] = volume_period.astype(str)
    volume_start = pd.to_datetime(frame["volume_month"] + "-01", utc=True)
    first_observed = pd.to_datetime(frame["first_observed"], utc=True, errors="coerce")
    if first_observed.isna().any():
        raise ValueError("first_observed must be a valid UTC timestamp")
    frame["first_observed"] = first_observed
    if "coverage_ratio" in frame.columns:
        coverage = pd.to_numeric(frame["coverage_ratio"], errors="coerce")
        if coverage.isna().any() or ((coverage < 0) | (coverage > 1)).any():
            raise ValueError("coverage_ratio must be finite and between zero and one")
        frame["coverage_ratio"] = coverage
    else:
        if {"prior_month_observed_days", "prior_month_expected_days"}.issubset(frame.columns):
            observed = pd.to_numeric(frame["prior_month_observed_days"], errors="coerce")
            expected = pd.to_numeric(frame["prior_month_expected_days"], errors="coerce")
            frame["coverage_ratio"] = observed.div(expected.replace(0, pd.NA))
        else:
            frame["coverage_ratio"] = 1.0
    frame["eligible_before_volume_month"] = frame["first_observed"] < volume_start
    frame["eligibility_reason"] = "ELIGIBLE_COMPLETE_PRIOR_MONTH"
    frame.loc[~frame["eligible_before_volume_month"], "eligibility_reason"] = "NOT_OBSERVED_BEFORE_VOLUME_MONTH"
    frame.loc[frame["coverage_ratio"] < minimum_coverage_ratio, "eligibility_reason"] = "PARTIAL_PRIOR_MONTH_EXCLUDED"
    frame.loc[frame["prior_month_quote_volume"].isna(), "eligibility_reason"] = "NO_PRIOR_COMPLETED_MONTH_VOLUME"
    frame.loc[pd.to_numeric(frame["prior_month_quote_volume"], errors="coerce") < 0, "eligibility_reason"] = "INVALID_NEGATIVE_VOLUME"
    eligible = (
        frame["eligible_before_volume_month"]
        & frame["coverage_ratio"].ge(minimum_coverage_ratio)
        & pd.to_numeric(frame["prior_month_quote_volume"], errors="coerce").ge(0)
        & pd.to_numeric(frame["prior_month_quote_volume"], errors="coerce").notna()
    )
    frame["prior_month_quote_volume"] = pd.to_numeric(frame["prior_month_quote_volume"], errors="coerce")
    frame["rank"] = pd.NA
    for (_, month), index in frame.loc[eligible].groupby(["market", "universe_month"], sort=True).groups.items():
        ordered = frame.loc[index].sort_values(["prior_month_quote_volume", "symbol"], ascending=[False, True])
        frame.loc[ordered.index, "rank"] = range(1, len(ordered) + 1)
    frame["rank"] = frame["rank"].astype("Int64")
    frame["selected_top20"] = eligible & frame["rank"].le(20)
    frame["selected_top50"] = eligible & frame["rank"].le(50)
    frame["selected_top100"] = eligible & frame["rank"].le(100)
    frame["selected_top_n"] = eligible & frame["rank"].le(top_n)
    return frame.sort_values(["market", "universe_month", "rank", "symbol"], na_position="last").reset_index(drop=True)


def completed_cutoff_utc(now: pd.Timestamp | None = None, interval: str = "15m") -> pd.Timestamp:
    """Return the latest fully closed UTC bar boundary for a fixed interval."""
    if interval not in INTERVAL_MS:
        raise ValueError(f"unsupported interval: {interval}")
    current = pd.Timestamp(now if now is not None else pd.Timestamp.now(tz="UTC"))
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    step = pd.Timedelta(milliseconds=INTERVAL_MS[interval])
    return current.floor(step) - step


def causal_resample(frame: pd.DataFrame, target: str) -> pd.DataFrame:
    """Strictly resample a complete source grid, dropping partial buckets."""
    return resample_klines(frame, target)


def resample_contiguous_source(frame: pd.DataFrame, target: str, *, source_interval: str = "15m") -> pd.DataFrame:
    """Split only on aligned gaps, then resample every segment fail-closed."""
    if source_interval not in INTERVAL_MS:
        raise ValueError(f"unsupported source interval: {source_interval}")
    ordered = frame.sort_values("open_time", kind="stable").copy()
    if ordered.empty:
        return ordered
    timestamps = pd.to_datetime(ordered["open_time"], utc=True)
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise DataIntegrityError("source timestamps must be unique and increasing")
    source_step = pd.Timedelta(milliseconds=INTERVAL_MS[source_interval])
    stamps = pd.to_datetime(ordered['open_time'], utc=True)
    phase_ns = stamps.astype('datetime64[ns, UTC]').astype('int64') % source_step.value
    if (phase_ns != 0).any():
        raise DataIntegrityError('source timestamps are not aligned to the canonical UTC grid (OFF_GRID_PHASE)')
    deltas = timestamps.diff().dropna()
    invalid = deltas.lt(source_step) | deltas.mod(source_step).ne(pd.Timedelta(0))
    if invalid.any():
        raise DataIntegrityError("source timestamps are off the declared 15m grid")
    segment_id = timestamps.diff().fillna(source_step).ne(source_step).cumsum()
    parts = []
    for _, segment in ordered.groupby(segment_id, sort=False):
        parts.append(resample_klines(segment, target))
    return pd.concat(parts, ignore_index=True) if parts else ordered.iloc[0:0].copy()


def lifecycle_records(
    frames: Iterable[pd.DataFrame],
    *,
    market: str,
    interval: str,
    source: str = "data.binance.vision",
) -> pd.DataFrame:
    """Build lifecycle rows from observed data, never from today's symbol list."""
    rows: list[dict[str, object]] = []
    expected = pd.Timedelta(milliseconds=INTERVAL_MS[interval])
    for frame in frames:
        if frame.empty:
            continue
        required = {"symbol", "open_time"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"missing lifecycle columns: {', '.join(sorted(missing))}")
        for symbol, group in frame.groupby("symbol", sort=True):
            ts = pd.to_datetime(group["open_time"], utc=True).drop_duplicates().sort_values()
            deltas = ts.diff().dropna()
            gaps = int(sum(max(0, int(delta / expected) - 1) for delta in deltas[deltas > expected]))
            rows.append(
                {
                    "market": market,
                    "symbol": str(symbol),
                    "first_archive_observed": ts.iloc[0].isoformat(),
                    "last_archive_observed": ts.iloc[-1].isoformat(),
                    "listing_effective_start": "UNKNOWN",
                    "listing_evidence": "NO_INDEPENDENT_EVIDENCE; archive presence is first observation only",
                    "delisting_effective_end": "UNKNOWN",
                    "delisting_evidence": "NO_INDEPENDENT_EVIDENCE; bounded archive end is not delisting",
                    "row_count": int(len(ts)),
                    "internal_gap_count": gaps,
                    "coverage_state": "OBSERVED_ARCHIVE_WINDOW_ONLY",
                    "source": source,
                }
            )
    return pd.DataFrame(rows).drop_duplicates(["market", "symbol", "first_archive_observed", "last_archive_observed"])


def select_causal_liquidity_universe(
    monthly_volume: pd.DataFrame,
    *,
    top_n: int = 50,
    market: str | None = None,
) -> pd.DataFrame:
    """Select symbols using only the immediately preceding completed month.

    ``monthly_volume`` must contain ``universe_month``, ``symbol``,
    ``prior_month_quote_volume``, and ``first_observed``.  The output preserves
    diagnostic Top20/50/100 flags and explicit eligibility reasons.
    """
    required = {"universe_month", "symbol", "prior_month_quote_volume", "first_observed"}
    missing = required - set(monthly_volume.columns)
    if missing:
        raise ValueError(f"missing universe columns: {', '.join(sorted(missing))}")
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    frame = monthly_volume.copy()
    frame["universe_month"] = (
        pd.to_datetime(frame["universe_month"], utc=True)
        .dt.tz_convert(None)
        .dt.to_period("M")
        .astype(str)
    )
    frame["first_observed"] = pd.to_datetime(frame["first_observed"], utc=True)
    frame["prior_month_quote_volume"] = pd.to_numeric(frame["prior_month_quote_volume"], errors="coerce")
    frame["eligible_before_month"] = frame["first_observed"] < pd.to_datetime(frame["universe_month"] + "-01", utc=True)
    frame["eligibility_reason"] = frame["eligible_before_month"].map(
        {True: "OBSERVED_BEFORE_UNIVERSE_MONTH", False: "NOT_OBSERVED_BEFORE_UNIVERSE_MONTH"}
    )
    frame.loc[frame["prior_month_quote_volume"].isna(), "eligibility_reason"] = "NO_PRIOR_COMPLETED_MONTH_VOLUME"
    frame.loc[frame["prior_month_quote_volume"] < 0, "eligibility_reason"] = "INVALID_NEGATIVE_VOLUME"
    eligible = frame["eligible_before_month"] & frame["prior_month_quote_volume"].ge(0) & frame["prior_month_quote_volume"].notna()
    frame["rank"] = pd.NA
    for month, index in frame.loc[eligible].groupby("universe_month", sort=True).groups.items():
        ordered = frame.loc[index].sort_values(["prior_month_quote_volume", "symbol"], ascending=[False, True])
        frame.loc[ordered.index, "rank"] = range(1, len(ordered) + 1)
    frame["rank"] = frame["rank"].astype("Int64")
    frame["selected_top20"] = eligible & frame["rank"].le(20)
    frame["selected_top50"] = eligible & frame["rank"].le(50)
    frame["selected_top100"] = eligible & frame["rank"].le(100)
    frame["selected_top_n"] = eligible & frame["rank"].le(top_n)
    if market is not None:
        frame["market"] = market
    return frame.sort_values(["universe_month", "rank", "symbol"], na_position="last").reset_index(drop=True)


_LONG_KLINE = "official klines archive; completed-bar OHLCV/taker fields"
_FEATURE_SOURCE_OVERRIDES: Mapping[str, dict[str, object]] = {
    "microstructure.spread": {"required_raw_sources": "historical depth/best bid-ask; forward-only collector", "source_capability": "FORWARD_ONLY_OR_UNVERIFIED_ARCHIVE", "market_support": "spot;um", "campaign_coverage": "HISTORICAL_UNAVAILABLE"},
    "microstructure.top_book_imbalance": {"required_raw_sources": "historical depth/best bid-ask; forward-only collector", "source_capability": "FORWARD_ONLY_OR_UNVERIFIED_ARCHIVE", "market_support": "spot;um", "campaign_coverage": "HISTORICAL_UNAVAILABLE"},
    "derivatives.oi_change": {"required_raw_sources": "Binance openInterestHist REST or UM Vision metrics", "source_capability": "SHORT_RETENTION_OR_UNVERIFIED_METRICS", "market_support": "um", "campaign_coverage": "HISTORICAL_UNAVAILABLE", "max_age": "31d"},
    "derivatives.funding_zscore": {"required_raw_sources": "Binance UM fundingRate archive/event history", "source_capability": "EVENT_ARCHIVE_UNVERIFIED", "market_support": "um", "campaign_coverage": "HISTORICAL_UNAVAILABLE"},
    "derivatives.premium_zscore": {"required_raw_sources": "Binance UM premiumIndexKlines archive", "source_capability": "ARCHIVE_PATH_UNVERIFIED", "market_support": "um", "campaign_coverage": "HISTORICAL_UNAVAILABLE"},
    "context.market_breadth": {"required_raw_sources": "observed lifecycle-aware OHLCV universe", "source_capability": "PANEL_DEPENDENT", "market_support": "spot;um", "campaign_coverage": "PARTIAL"},
}


def feature_availability_matrix(*, markets: tuple[str, ...] = ("spot", "um"), timeframes: tuple[str, ...] = ("15m", "1h", "4h"), coverage_overrides: Mapping[str, str] | None = None, capability_overrides: Mapping[str, str] | None = None) -> pd.DataFrame:
    """Return the frozen 22-feature availability classification."""
    rows: list[dict[str, object]] = []
    coverage_overrides = coverage_overrides or {}
    capability_overrides = capability_overrides or {}
    for spec in CORE_FEATURE_SPECS:
        override = dict(_FEATURE_SOURCE_OVERRIDES.get(spec.feature_id, {}))
        source_capability = capability_overrides.get(spec.feature_id, str(override.get("source_capability", "ARCHIVE_CAPABLE")))
        market_support = str(override.get("market_support", ";".join(markets)))
        coverage = coverage_overrides.get(spec.feature_id, str(override.get("campaign_coverage", "PARTIAL")))
        eligible = coverage == "AVAILABLE"
        shadow = not eligible
        market_coverage = ";".join(
            f"{market}={'NOT_APPLICABLE' if market not in market_support.split(';') else coverage}"
            for market in markets
        )
        rows.append(
            {
                "feature_id": spec.feature_id,
                "family": spec.family,
                "required_raw_sources": override.get("required_raw_sources", _LONG_KLINE),
                "source_capability": source_capability,
                "campaign_coverage": coverage,
                "historical_availability": coverage,
                "earliest_usable": "after declared warmup; campaign archive dependent",
                "latest_usable": "acquisition cutoff",
                "market_support": market_support,
                "market_coverage": market_coverage,
                "timeframes": ";".join(timeframes),
                "causal_method": "trailing formula on completed bars; backward as-of for external sources",
                "max_age": override.get("max_age", "bar-close"),
                "coverage_status": coverage,
                "historical_campaign_eligible": eligible,
                "forward_shadow_required": shadow,
                "formula_implemented": True,
                "notes": "missing history is fail-closed; never imputed or substituted from another venue",
            }
        )
    return pd.DataFrame(rows)


def write_partitioned_panel(frame: pd.DataFrame, root: Path, *, provenance: str) -> list[Path]:
    """Write UTC panel partitions by market/symbol/timeframe/year."""
    required = {"timestamp", "market", "symbol", "timeframe"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing panel columns: {', '.join(sorted(missing))}")
    ordered = frame.copy()
    ordered["timestamp"] = pd.to_datetime(ordered["timestamp"], utc=True)
    ordered["provenance"] = provenance
    paths: list[Path] = []
    for keys, group in ordered.groupby(["market", "symbol", "timeframe", ordered["timestamp"].dt.year], sort=True):
        market, symbol, timeframe, year = keys
        destination = Path(root) / f"market={market}" / f"symbol={symbol}" / f"timeframe={timeframe}" / f"year={year}" / "part-000.parquet"
        destination.parent.mkdir(parents=True, exist_ok=True)
        group.sort_values("timestamp").to_parquet(destination, index=False)
        paths.append(destination)
    return paths


def frame_sha256(frame: pd.DataFrame) -> str:
    """Stable hash for a panel partition without float text reformatting."""
    ordered = frame.reindex(sorted(frame.columns), axis=1)
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=True).values.tobytes()).hexdigest()
