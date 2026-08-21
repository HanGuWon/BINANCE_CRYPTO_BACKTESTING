"""Metadata-only Binance Vision archive census and eligibility policy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from .data import ArchiveObject

MONTH_RE = re.compile(r"-(?P<year>\d{4})-(?P<month>\d{2})\.zip$")
DELIVERY_RE = re.compile(r"_[0-9]{6}$")
LEVERAGED_RE = re.compile(r"(?:UP|DOWN|BULL|BEAR)USDT$")


@dataclass(frozen=True)
class EligibilityRecord:
    market: str
    symbol: str
    eligible: bool
    instrument_class: str
    exclusion_reason: str
    evidence: str


def _month_from_key(key: str) -> str | None:
    match = MONTH_RE.search(Path(key).name)
    return f"{match.group('year')}-{match.group('month')}" if match else None


def object_census_rows(objects: Iterable[ArchiveObject], *, market: str, symbol_prefix: str | None = None, interval: str = "15m") -> pd.DataFrame:
    """Normalize listed monthly 15m kline objects without downloading content."""
    rows: list[dict[str, object]] = []
    for obj in objects:
        if not obj.key.endswith(".zip") or f"/{interval}/" not in obj.key:
            continue
        parts = obj.key.split("/")
        if len(parts) < 2:
            continue
        symbol = parts[-3] if parts[-2] == interval else parts[-2]
        if symbol_prefix and symbol != symbol_prefix:
            continue
        month = _month_from_key(obj.key)
        if month is None:
            continue
        rows.append({
            "market": market,
            "symbol": symbol,
            "archive_dataset": "klines",
            "interval": interval,
            "archive_month": month,
            "key": obj.key,
            "size": obj.size,
            "last_modified": obj.last_modified,
            "etag": obj.etag,
        })
    return pd.DataFrame(rows, columns=["market", "symbol", "archive_dataset", "interval", "archive_month", "key", "size", "last_modified", "etag"])


def symbol_census(object_rows: pd.DataFrame) -> pd.DataFrame:
    """Aggregate object metadata by symbol and expose internal month gaps."""
    required = {"market", "symbol", "archive_month", "key", "size"}
    missing = required - set(object_rows.columns)
    if missing:
        raise ValueError(f"missing census columns: {', '.join(sorted(missing))}")
    records: list[dict[str, object]] = []
    for (market, symbol), group in object_rows.groupby(["market", "symbol"], sort=True):
        months = pd.PeriodIndex(group["archive_month"].astype(str), freq="M").sort_values().unique()
        expected = pd.period_range(months.min(), months.max(), freq="M") if len(months) else pd.PeriodIndex([], freq="M")
        missing_months = expected.difference(months)
        records.append({
            "market": market,
            "symbol": symbol,
            "archive_dataset": "klines",
            "interval": str(group["interval"].iloc[0]) if "interval" in group else "15m",
            "first_archive_month": str(months.min()) if len(months) else None,
            "last_archive_month": str(months.max()) if len(months) else None,
            "available_month_count": int(len(months)),
            "missing_month_count_inside_observed_span": int(len(missing_months)),
            "object_count": int(len(group)),
            "compressed_bytes_from_s3_listing": int(pd.to_numeric(group["size"], errors="coerce").fillna(0).sum()),
            "first_key": sorted(group["key"].astype(str))[0],
            "last_key": sorted(group["key"].astype(str))[-1],
        })
    return pd.DataFrame(records)


def classify_instrument(market: str, symbol: str) -> EligibilityRecord:
    """Apply the frozen return-independent Spot/UM eligibility policy."""
    symbol = symbol.upper()
    if market == "um" and DELIVERY_RE.search(symbol):
        if "USDT_" in symbol:
            return EligibilityRecord(market, symbol, False, "DATED_DELIVERY", "DATED_CONTRACT_EXCLUDED", "delivery suffix policy")
    if not symbol.endswith("USDT"):
        return EligibilityRecord(market, symbol, False, "UNKNOWN", "QUOTE_NOT_USDT", "archive symbol spelling")
    if market == "spot":
        if LEVERAGED_RE.search(symbol):
            return EligibilityRecord(market, symbol, False, "SYNTHETIC_OR_LEVERAGED", "LEVERAGED_TOKEN_SUFFIX", "symbol naming policy")
        return EligibilityRecord(market, symbol, True, "SPOT_ORDINARY_USDT", "", "USDT quote plus non-leveraged symbol policy")
    if market == "um":
        return EligibilityRecord(market, symbol, True, "USD_M_PERPETUAL_COHORT", "", "USDT symbol without dated-delivery suffix")
    return EligibilityRecord(market, symbol, False, "UNKNOWN", "MARKET_NOT_IN_R1_SCOPE", "scope policy")


def eligibility_table(symbols: Iterable[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame([record.__dict__ for record in (classify_instrument(market, symbol) for market, symbol in symbols)])
