"""Reusable causal primitive cache for Fast Discovery V2."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from .features import CoreFeatureEngine, compute_gap_safe_features


def frame_sha256(frame: pd.DataFrame) -> str:
    """Hash causal source values while excluding outcome/target columns."""
    excluded = {"target", "label", "future_return", "gross_return", "net_return", "funding_cashflow"}
    columns = [column for column in sorted(frame.columns) if column not in excluded]
    ordered = frame.reindex(columns=columns)
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=True).values.tobytes()).hexdigest()


def primitive_cache_key(*, source_hash: str, market: str, timeframe: str, symbol: str, segment_id: str, feature_id: str, spec_version: str = "core-v1", variant: str = "raw") -> tuple[str, ...]:
    return (source_hash, market, timeframe, symbol, segment_id, feature_id, spec_version, variant)


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    compute_seconds: float = 0.0
    rows: int = 0
    symbols: int = 0
    segments: int = 0


class PrimitiveFeatureCache:
    """Cache primitive output columns by immutable causal segment identity."""

    def __init__(self, engine: CoreFeatureEngine | None = None) -> None:
        self.engine = engine or CoreFeatureEngine()
        self._values: dict[tuple[str, ...], pd.Series] = {}
        self.stats = CacheStats()

    @property
    def keys(self) -> tuple[tuple[str, ...], ...]:
        return tuple(self._values)

    def materialize(
        self,
        panel: pd.DataFrame,
        *,
        market: str,
        timeframe: str,
        feature_ids: Iterable[str],
    ) -> pd.DataFrame:
        required = {"symbol", "segment_id", "open_time"}
        missing = required - set(panel.columns)
        if missing:
            raise ValueError(f"panel missing cache identity columns: {', '.join(sorted(missing))}")
        requested = tuple(dict.fromkeys(str(feature) for feature in feature_ids))
        if not requested:
            return panel.copy()
        result = panel.copy()
        self.stats.rows += len(panel)
        self.stats.symbols += int(panel["symbol"].nunique())
        self.stats.segments += int(panel[["symbol", "segment_id"]].drop_duplicates().shape[0])
        for (symbol, segment_id), positions in panel.groupby(["symbol", "segment_id"], sort=False).groups.items():
            segment = panel.loc[positions].sort_values("open_time", kind="stable")
            source_hash = frame_sha256(segment)
            missing_keys: list[tuple[str, ...]] = []
            for feature_id in requested:
                key = primitive_cache_key(source_hash=source_hash, market=market, timeframe=timeframe, symbol=str(symbol), segment_id=str(segment_id), feature_id=feature_id)
                if key in self._values:
                    self.stats.hits += 1
                    result.loc[segment.index, feature_id] = self._values[key].reindex(segment.index).to_numpy()
                else:
                    missing_keys.append(key)
            if not missing_keys:
                continue
            started = time.perf_counter()
            # compute_gap_safe_features currently indexes positions with iloc; use a
            # zero-based copy so non-contiguous original panel labels remain safe.
            segment_for_compute = segment.reset_index(drop=True)
            computed = compute_gap_safe_features(self.engine, segment_for_compute, timeframe)
            self.stats.compute_seconds += time.perf_counter() - started
            for key in missing_keys:
                feature_id = key[5]
                if feature_id not in computed:
                    raise ValueError(f"CoreFeatureEngine does not provide requested primitive: {feature_id}")
                values = computed[feature_id].copy()
                values.index = segment.index
                self._values[key] = values
                self.stats.misses += 1
                result.loc[segment.index, feature_id] = values.to_numpy()
        return result


