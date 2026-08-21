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

# These sets are intentionally conservative.  A symbol not present in the
# frozen lists remains UNKNOWN rather than being promoted by its spelling.
STABLECOIN_BASES = {
    "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI", "USDP", "USDE",
    "USDD", "UST", "FRAX", "LUSD", "PYUSD", "EURC", "EURS", "GUSD",
}
FIAT_OR_TOKENIZED_FIAT_BASES = {
    "EUR", "AEUR", "GBP", "TRY", "BRL", "RUB", "AUD", "PLN", "NGN",
    "ZAR", "JPY", "ARS", "BIDR", "UAH", "RON", "MXN", "COP", "CZK",
}


@dataclass(frozen=True)
class EligibilityRecord:
    market: str
    symbol: str
    eligible: bool
    instrument_class: str
    exclusion_reason: str
    evidence: str


@dataclass(frozen=True)
class AssetTaxonomyRecord:
    market: str
    symbol: str
    asset_base: str
    classification: str
    evidence: str
    evidence_source: str
    classification_version: str = "r1.6-taxonomy-v1"
    primary_crypto_eligible: bool = False
    all_tradable_usdt_diagnostic: bool = False


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


def _usdt_base(symbol: str) -> str:
    value = symbol.upper()
    if value.endswith("USDT"):
        value = value[:-4]
    # Binance quantity multipliers do not change the underlying asset class.
    return re.sub(r"^\d{3,7}", "", value)


def classify_asset(
    market: str,
    symbol: str,
    *,
    funding_verified_symbols: set[str] | None = None,
) -> AssetTaxonomyRecord:
    """Classify a USDT instrument without using returns or current survivorship.

    UM perpetual verification is evidence-based: a funding archive observation
    upgrades a suffix-free symbol to ``PERPETUAL_VERIFIED``; spelling alone is
    retained as ``PERPETUAL_STYLE_UNVERIFIED``.
    """
    symbol = symbol.upper()
    funding_verified_symbols = {item.upper() for item in (funding_verified_symbols or set())}
    base = _usdt_base(symbol)
    diagnostic = symbol.endswith("USDT") or bool(market == "um" and DELIVERY_RE.search(symbol))
    if market not in {"spot", "um"}:
        return AssetTaxonomyRecord(market, symbol, base, "UNKNOWN", "market outside frozen scope", "scope policy", primary_crypto_eligible=False, all_tradable_usdt_diagnostic=False)
    if market == "um" and DELIVERY_RE.search(symbol):
        return AssetTaxonomyRecord(market, symbol, base, "DATED_DELIVERY", "dated delivery suffix", "archive symbol policy", primary_crypto_eligible=False, all_tradable_usdt_diagnostic=True)
    if not diagnostic:
        return AssetTaxonomyRecord(market, symbol, base, "UNKNOWN", "non-USDT quote", "archive symbol spelling", primary_crypto_eligible=False, all_tradable_usdt_diagnostic=False)
    if DELIVERY_RE.search(symbol):
        return AssetTaxonomyRecord(market, symbol, base, "DATED_DELIVERY", "dated delivery suffix", "archive symbol policy", primary_crypto_eligible=False, all_tradable_usdt_diagnostic=True)
    if LEVERAGED_RE.search(symbol):
        return AssetTaxonomyRecord(market, symbol, base, "LEVERAGED_OR_SYNTHETIC", "leveraged-token suffix", "archive symbol policy", primary_crypto_eligible=False, all_tradable_usdt_diagnostic=True)
    if base in STABLECOIN_BASES:
        return AssetTaxonomyRecord(market, symbol, base, "STABLECOIN", "base asset in frozen stablecoin list", "r1.6 taxonomy v1", primary_crypto_eligible=False, all_tradable_usdt_diagnostic=True)
    if base in FIAT_OR_TOKENIZED_FIAT_BASES:
        return AssetTaxonomyRecord(market, symbol, base, "FIAT_OR_TOKENIZED_FIAT", "base asset in frozen fiat/tokenized-fiat list", "r1.6 taxonomy v1", primary_crypto_eligible=False, all_tradable_usdt_diagnostic=True)
    if market == "spot":
        return AssetTaxonomyRecord(market, symbol, base, "CRYPTO", "USDT quote and base not in excluded taxonomy", "r1.6 taxonomy v1", primary_crypto_eligible=True, all_tradable_usdt_diagnostic=True)
    if symbol in funding_verified_symbols:
        return AssetTaxonomyRecord(market, symbol, base, "PERPETUAL_VERIFIED", "historical fundingRate archive presence", "Binance Vision fundingRate census", primary_crypto_eligible=True, all_tradable_usdt_diagnostic=True)
    return AssetTaxonomyRecord(market, symbol, base, "PERPETUAL_STYLE_UNVERIFIED", "suffix-free USDT contract without verified funding evidence", "symbol spelling only", primary_crypto_eligible=False, all_tradable_usdt_diagnostic=True)


def asset_taxonomy_table(
    symbols: Iterable[tuple[str, str]],
    *,
    funding_verified_symbols: set[str] | None = None,
) -> pd.DataFrame:
    """Return frozen taxonomy rows for primary and diagnostic cohorts."""
    return pd.DataFrame([
        record.__dict__
        for record in (
            classify_asset(market, symbol, funding_verified_symbols=funding_verified_symbols)
            for market, symbol in symbols
        )
    ])
