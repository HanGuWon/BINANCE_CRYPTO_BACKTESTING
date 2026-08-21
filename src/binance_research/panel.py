"""Causal historical-panel utilities for the R1 research campaign.

The module deliberately contains metadata and panel-construction primitives only.
It does not compute returns, rank indicators, or access a final holdout.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from .data import INTERVAL_MS, resample_klines
from .features import CORE_FEATURE_SPECS

PANEL_COVERAGE_STATUSES = (
    "AVAILABLE",
    "PARTIAL",
    "STALE",
    "NO_PRIOR_OBSERVATION",
    "HISTORICAL_UNAVAILABLE",
)


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
