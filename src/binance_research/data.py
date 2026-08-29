from __future__ import annotations

import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

import numpy as np
import pandas as pd

from .models import CoverageStatus, DatasetManifest, IntegrityIssue
from .r3_timing import ClockCalibration, calibrate_server_clock

KLINE_COLUMNS = ("open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trade_count", "taker_buy_volume", "taker_buy_quote_volume", "ignore")
INTERVAL_MS = {"1s": 1_000, "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000, "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000}
SHORT_RETENTION = {"openInterestHist": "REST retains the latest one month only", "takerlongshortRatio": "REST retains the latest 30 days only", "topLongShortAccountRatio": "REST retains the latest 30 days only", "topLongShortPositionRatio": "REST retains the latest 30 days only"}
SHORT_RETENTION_MONTHS = {"openInterestHist": 1}
SHORT_RETENTION_DAYS = {"takerlongshortRatio": 30, "topLongShortAccountRatio": 30, "topLongShortPositionRatio": 30}

class DataIntegrityError(RuntimeError):
    pass


class RateLimitGapError(RuntimeError):
    """HTTP 429 remained after the bounded retry/backoff budget."""

    def __init__(self, retry_after: float, *, headers: dict[str, str] | None = None) -> None:
        self.retry_after = retry_after
        self.headers = headers or {}
        super().__init__(f"Binance HTTP 429; retry_after={retry_after:g}s")


class IPBanFatalError(RuntimeError):
    """Binance HTTP 418 is fatal and must never be retried."""


@dataclass(frozen=True)
class RestResponseMetadata:
    http_status: int
    headers: dict[str, str]
    request_started_at: str
    response_received_at: str
    latency_seconds: float
    url: str


def parse_rate_limits(payload: Any) -> tuple[dict[str, Any], ...]:
    """Return the exchangeInfo rateLimits without inventing a local limit."""
    if not isinstance(payload, dict) or not isinstance(payload.get("rateLimits"), list):
        raise DataIntegrityError("exchangeInfo response lacks rateLimits")
    limits = tuple(item for item in payload["rateLimits"] if isinstance(item, dict))
    if len(limits) != len(payload["rateLimits"]):
        raise DataIntegrityError("exchangeInfo rateLimits contains a malformed entry")
    return limits


@dataclass(frozen=True)
class ArchiveObject:
    """Metadata returned by the Binance Vision S3 listing."""

    key: str
    size: int | None = None
    last_modified: str | None = None
    etag: str | None = None

def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()

def infer_timestamp_unit(values: pd.Series) -> str:
    finite = pd.to_numeric(values, errors="coerce").dropna()
    if finite.empty:
        raise DataIntegrityError("cannot infer timestamp unit from empty values")
    magnitude = float(finite.abs().min())
    if magnitude >= 1e17: return "ns"
    if magnitude >= 1e14: return "us"
    if magnitude >= 1e11: return "ms"
    if magnitude >= 1e8: return "s"
    raise DataIntegrityError(f"implausible epoch timestamp magnitude: {magnitude}")

def normalize_timestamp(values: pd.Series) -> pd.Series:
    result = pd.to_datetime(pd.to_numeric(values, errors="raise"), unit=infer_timestamp_unit(values), utc=True).astype("datetime64[ns, UTC]")
    if result.isna().any(): raise DataIntegrityError("timestamp normalization produced NaT")
    return result

def normalize_klines(rows: Iterable[Iterable[Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows), columns=KLINE_COLUMNS)
    if frame.empty: return frame.astype({"open_time": "datetime64[ns, UTC]", "close_time": "datetime64[ns, UTC]"})
    # Monthly UM/CM archives may include a CSV header while Spot archives
    # typically do not.  Remove that transport header before numeric parsing;
    # any remaining malformed timestamps are still fail-closed below.
    timestamp_numeric = pd.to_numeric(frame["open_time"], errors="coerce")
    if timestamp_numeric.isna().any():
        header_rows = timestamp_numeric.isna() & frame["open_time"].astype(str).eq("open_time")
        if not header_rows.any() or int(header_rows.sum()) != 1:
            raise DataIntegrityError("non-numeric kline timestamp outside a single archive header row")
        frame = frame.loc[~header_rows].reset_index(drop=True)
    frame["open_time"], frame["close_time"] = normalize_timestamp(frame["open_time"]), normalize_timestamp(frame["close_time"])
    numeric = [c for c in KLINE_COLUMNS if c not in {"open_time", "close_time", "ignore"}]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    frame["trade_count"] = frame["trade_count"].astype("Int64")
    return frame.drop(columns=["ignore"]).sort_values("open_time", kind="stable").reset_index(drop=True)

def normalize_archive_rows(rows: pd.DataFrame, dataset: str, market: str) -> pd.DataFrame:
    key, frame = dataset.lower(), rows.copy()
    if key.endswith("klines") or key == "klines": return normalize_klines(rows.itertuples(index=False, name=None))
    if key == "aggtrades":
        columns = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "timestamp", "is_buyer_maker"]
        if frame.shape[1] == 8: columns.append("is_best_match")
        frame.columns = columns[:frame.shape[1]]
    elif key == "trades":
        if market == "spot" and frame.shape[1] == 7: frame.columns = ["trade_id", "price", "quantity", "quote_quantity", "timestamp", "is_buyer_maker", "is_best_match"]
        elif frame.shape[1] == 6: frame.columns = ["trade_id", "price", "quantity", "quote_or_base_quantity", "timestamp", "is_buyer_maker"]
    elif key == "fundingrate" and frame.shape[1] >= 3:
        frame, frame.columns = frame.iloc[:, :3], ["timestamp", "funding_interval_hours", "funding_rate"]
    if "timestamp" in frame:
        ts = pd.to_numeric(frame["timestamp"], errors="coerce")
        frame = frame.loc[ts.notna()].copy(); frame["timestamp"] = normalize_timestamp(ts.loc[ts.notna()])
        frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    return frame

def validate_klines(frame: pd.DataFrame, interval: str, *, allow_negative: bool = False) -> list[IntegrityIssue]:
    missing = sorted((set(KLINE_COLUMNS) - {"ignore"}) - set(frame.columns))
    if missing: return [IntegrityIssue("MISSING_COLUMNS", "ERROR", ", ".join(missing), len(missing))]
    issues: list[IntegrityIssue] = []
    duplicates = int(frame["open_time"].duplicated(keep=False).sum())
    if duplicates: issues.append(IntegrityIssue("DUPLICATE_TIMESTAMP", "ERROR", "duplicate open times", duplicates))
    numeric = frame[["open", "high", "low", "close", "volume", "quote_volume"]]
    malformed = int(numeric.isna().any(axis=1).sum())
    if malformed: issues.append(IntegrityIssue("MALFORMED_CANDLE", "ERROR", "non-numeric or missing candle fields", malformed))
    negative = (numeric < 0).any(axis=1) if not allow_negative else pd.Series(False, index=frame.index)
    impossible = ((frame["high"] < frame[["open", "close", "low"]].max(axis=1)) | (frame["low"] > frame[["open", "close", "high"]].min(axis=1)) | negative)
    if int(impossible.sum()): issues.append(IntegrityIssue("IMPOSSIBLE_OHLC", "ERROR", "OHLC ordering or non-negative invariant failed", int(impossible.sum())))
    if interval in INTERVAL_MS and len(frame) > 1:
        expected = pd.Timedelta(milliseconds=INTERVAL_MS[interval]); deltas = frame["open_time"].drop_duplicates().sort_values().diff().dropna()
        stamps = frame["open_time"].drop_duplicates().sort_values()
        phase_ns = stamps.astype("datetime64[ns, UTC]").astype("int64") % expected.value
        off_grid = int((phase_ns != 0).sum())
        if off_grid:
            issues.append(IntegrityIssue("OFF_GRID_PHASE", "ERROR", "timestamps are not aligned to the absolute UTC interval phase", off_grid))
        gaps, irregular = deltas[deltas > expected], deltas[(deltas < expected) | ((deltas % expected) != pd.Timedelta(0))]
        if len(gaps): issues.append(IntegrityIssue("MISSING_INTERVAL", "WARN", "gaps in candle grid", int(sum(max(0, int(delta / expected) - 1) for delta in gaps))))
        if len(irregular): issues.append(IntegrityIssue("IRREGULAR_INTERVAL", "ERROR", "timestamps are off the requested grid", len(irregular)))
    return issues

def deduplicate_klines(frame: pd.DataFrame) -> pd.DataFrame:
    for timestamp, group in frame[frame["open_time"].duplicated(keep=False)].groupby("open_time", sort=False):
        if len(group.drop_duplicates()) != 1: raise DataIntegrityError(f"conflicting candles at {timestamp}")
    return frame.drop_duplicates().sort_values("open_time").reset_index(drop=True)

def resample_klines(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate only complete fixed-duration buckets from a regular source grid."""
    if len(frame) < 2: return frame.iloc[0:0].copy()
    ordered = frame.sort_values("open_time", kind="stable"); deltas = ordered["open_time"].diff().dropna(); source_step = deltas.iloc[0]
    if (deltas != source_step).any(): raise DataIntegrityError("source bars must have one regular interval before resampling")
    # Some pandas builds no longer accept lowercase interval aliases such as
    # "15m"; canonical INTERVAL_MS values are unambiguous Timedeltas.
    target_step = pd.Timedelta(milliseconds=INTERVAL_MS[rule]) if rule in INTERVAL_MS else pd.Timedelta(rule)
    if target_step < source_step or target_step <= pd.Timedelta(0): raise ValueError("target resample rule must be no shorter than source bars")
    ratio, expected_count = target_step / source_step, int(round(float(target_step / source_step)))
    if not np.isclose(float(ratio), expected_count): raise ValueError("target resample rule must be an integer multiple of source bars")
    indexed = ordered.set_index("open_time")
    aggregation = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", "close_time": "last", "quote_volume": "sum", "trade_count": "sum", "taker_buy_volume": "sum", "taker_buy_quote_volume": "sum"}
    available = {key: value for key, value in aggregation.items() if key in indexed.columns}
    result = indexed.resample(target_step, label="left", closed="left").agg(available)
    counts = indexed["close"].resample(target_step, label="left", closed="left").count()
    return result.loc[counts == expected_count].dropna(subset=["open", "close"]).reset_index()


def load_kline_archive(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise DataIntegrityError(f"expected one archive member, found {len(names)}")
        with archive.open(names[0]) as handle:
            rows = pd.read_csv(handle, header=None)
    return normalize_klines(rows.itertuples(index=False, name=None))

@dataclass(frozen=True)
class ArchiveRequest:
    market: str; dataset: str; symbol: str; year: int; month: int; interval: str | None = None; cadence: str = "monthly"; day: int | None = None
    def __post_init__(self) -> None:
        if self.market not in {"spot", "um", "cm"}: raise ValueError(f"unsupported market: {self.market}")
        if self.cadence not in {"daily", "monthly"}: raise ValueError("cadence must be daily or monthly")
        if self.month not in range(1, 13): raise ValueError("month must be 1..12")
        if self.cadence == "daily":
            if self.day is None: raise ValueError("daily archive requests require day")
            datetime(self.year, self.month, self.day, tzinfo=UTC)
        elif self.day is not None: raise ValueError("day is only valid for daily archive requests")
    def url(self) -> str:
        market_path = {"spot": "spot", "um": "futures/um", "cm": "futures/cm"}[self.market]
        suffix = f"{self.year:04d}-{self.month:02d}-{self.day:02d}" if self.cadence == "daily" else f"{self.year:04d}-{self.month:02d}"
        base = f"https://data.binance.vision/data/{market_path}/{self.cadence}/{self.dataset}/{self.symbol}"
        if self.interval:
            base += f"/{self.interval}"; filename = f"{self.symbol}-{self.interval}-{suffix}.zip"
        else: filename = f"{self.symbol}-{self.dataset}-{suffix}.zip"
        return f"{base}/{filename}"

class BinanceArchiveClient:
    def __init__(self, raw_root: Path, timeout: float = 60.0, max_retries: int = 3) -> None: self.raw_root, self.timeout, self.max_retries = Path(raw_root), timeout, max_retries
    def _fetch(self, url: str) -> bytes:
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "binance-indicator-research/0.1"}), timeout=self.timeout) as response: return response.read()
            except (urllib.error.URLError, TimeoutError, ConnectionResetError):
                if attempt == self.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 8))
        raise AssertionError("archive fetch retry loop exhausted")
    def download(self, request: ArchiveRequest) -> tuple[Path, DatasetManifest]:
        url, payload = request.url(), self._fetch(request.url()); published = self._fetch(url + ".CHECKSUM").decode("utf-8").strip().split()[0].lower(); computed = sha256_bytes(payload)
        if published != computed: raise DataIntegrityError(f"checksum mismatch for {url}: published={published}, computed={computed}")
        relative = Path(request.market) / request.dataset / request.symbol / (request.interval or "")
        destination = self.raw_root / relative / Path(urllib.parse.urlparse(url).path).name; destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha256_bytes(destination.read_bytes()) != computed: raise DataIntegrityError(f"immutable raw object differs: {destination}")
        if not destination.exists(): destination.write_bytes(payload)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            if len(names) != 1: raise DataIntegrityError(f"expected one archive member, found {len(names)}")
            with archive.open(names[0]) as handle: rows = pd.read_csv(handle, header=None)
        allow_negative = request.dataset.lower() in {"premiumindexklines", "premiumpriceklines"}
        frame = normalize_archive_rows(rows, request.dataset, request.market); issues = validate_klines(frame, request.interval, allow_negative=allow_negative) if request.interval and "open_time" in frame else []
        timestamp_column = "open_time" if "open_time" in frame else "timestamp" if "timestamp" in frame else None
        manifest = DatasetManifest(schema_version=1, source="data.binance.vision", market_type=request.market, dataset=request.dataset, symbol=request.symbol, interval=request.interval, first_timestamp=(frame[timestamp_column].min().isoformat() if timestamp_column and len(frame) else None), last_timestamp=(frame[timestamp_column].max().isoformat() if timestamp_column and len(frame) else None), row_count=len(frame), downloaded_at=datetime.now(UTC).isoformat(), computed_sha256=computed, published_sha256=published, coverage_status=CoverageStatus.PARTIAL if issues else CoverageStatus.AVAILABLE, coverage_note=SHORT_RETENTION.get(request.dataset, "archive object verified"), issues=issues, archive_url=url)
        manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
        if not manifest_path.exists(): manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
        return destination, manifest
    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def _list_objects_v2_page(self, prefix: str, delimiter: str | None, continuation_token: str | None) -> tuple[list[str], list[ArchiveObject], bool, str | None]:
        params: dict[str, str] = {"list-type": "2", "prefix": prefix}
        if delimiter is not None:
            params["delimiter"] = delimiter
        if continuation_token is not None:
            params["continuation-token"] = continuation_token
        query = urllib.parse.urlencode(params)
        try:
            root = ElementTree.fromstring(self._fetch(f"https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?{query}"))
        except (ElementTree.ParseError, ValueError) as exc:
            raise DataIntegrityError("malformed Binance Vision S3 listing XML") from exc
        if self._local_name(root.tag) != "ListBucketResult":
            raise DataIntegrityError("unexpected Binance Vision S3 listing root")
        prefixes: list[str] = []
        objects: list[ArchiveObject] = []
        for node in root:
            name = self._local_name(node.tag)
            if name == "CommonPrefixes":
                values = {self._local_name(child.tag): (child.text or "") for child in node}
                if values.get("Prefix"):
                    prefixes.append(values["Prefix"])
            elif name == "Contents":
                values = {self._local_name(child.tag): (child.text or "") for child in node}
                size = values.get("Size")
                try:
                    parsed_size = int(size) if size not in {None, ""} else None
                except ValueError as exc:
                    raise DataIntegrityError("non-numeric object size in S3 listing") from exc
                objects.append(ArchiveObject(values.get("Key", ""), parsed_size, values.get("LastModified"), values.get("ETag")))
        truncated_text = next((child.text or "" for child in root if self._local_name(child.tag) == "IsTruncated"), "false").lower()
        if truncated_text not in {"true", "false"}:
            raise DataIntegrityError("invalid IsTruncated value in S3 listing")
        token = next((child.text or "" for child in root if self._local_name(child.tag) == "NextContinuationToken"), None)
        truncated = truncated_text == "true"
        if truncated and not token:
            raise DataIntegrityError("truncated S3 listing omitted NextContinuationToken")
        return prefixes, objects, truncated, token

    def list_objects_v2(self, prefix: str, *, delimiter: str | None = None) -> tuple[list[str], list[ArchiveObject], int]:
        """Return all paginated prefixes/objects with deterministic de-duplication."""
        prefixes: set[str] = set()
        objects: dict[str, ArchiveObject] = {}
        token: str | None = None
        seen_tokens: set[str] = set()
        pages = 0
        while True:
            page_prefixes, page_objects, truncated, next_token = self._list_objects_v2_page(prefix, delimiter, token)
            pages += 1
            prefixes.update(page_prefixes)
            for obj in page_objects:
                if obj.key:
                    existing = objects.get(obj.key)
                    if existing is not None and existing != obj:
                        raise DataIntegrityError(f"conflicting duplicate S3 listing object: {obj.key}")
                    objects[obj.key] = obj
            if not truncated:
                break
            if next_token in seen_tokens:
                raise DataIntegrityError("S3 listing continuation token repeated")
            seen_tokens.add(next_token or "")
            token = next_token
        return sorted(prefixes), [objects[key] for key in sorted(objects)], pages

    def discover_prefixes(self, prefix: str) -> list[str]:
        prefixes, _, _ = self.list_objects_v2(prefix, delimiter="/")
        return prefixes

class BinanceRestClient:
    """Read-only public market-data client. No order or account methods exist."""
    BASE_URLS = {"spot": "https://data-api.binance.vision", "um": "https://fapi.binance.com", "cm": "https://dapi.binance.com"}
    MAX_RETRY_AFTER_SECONDS = 60.0
    def __init__(self, timeout: float = 15.0, max_retries: int = 3) -> None: self.timeout, self.max_retries = timeout, max_retries

    def calibrate_server_clock(self, market: str = "um") -> ClockCalibration:
        """Measure exchange-vs-local clock offset using a request midpoint."""
        before = int(datetime.now(UTC).timestamp() * 1000)
        payload, _ = self.get_with_metadata(market, "/fapi/v1/time" if market == "um" else "/api/v3/time")
        after = int(datetime.now(UTC).timestamp() * 1000)
        if not isinstance(payload, dict) or "serverTime" not in payload:
            raise DataIntegrityError("Binance time response lacks serverTime")
        return calibrate_server_clock(local_before_ms=before, server_ms=int(payload["serverTime"]), local_after_ms=after)

    def get_with_metadata(self, market: str, path: str, params: dict[str, Any] | None = None) -> tuple[Any, RestResponseMetadata]:
        if market not in self.BASE_URLS: raise ValueError(f"unsupported market: {market}")
        url = self.BASE_URLS[market] + path + (("?" + urllib.parse.urlencode(params)) if params else ""); headers = {"User-Agent": "binance-indicator-research/0.1"}
        if api_key := os.getenv("BINANCE_API_KEY"): headers["X-MBX-APIKEY"] = api_key
        for attempt in range(self.max_retries + 1):
            started = datetime.now(UTC)
            started_clock = time.perf_counter()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=self.timeout) as response:
                    body = response.read()
                    received = datetime.now(UTC)
                    response_headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
                    metadata = RestResponseMetadata(response.status, response_headers, started.isoformat(), received.isoformat(), time.perf_counter() - started_clock, url)
                    return json.loads(body), metadata
            except urllib.error.HTTPError as exc:
                error_headers = {str(key).lower(): str(value) for key, value in exc.headers.items()}
                if exc.code == 418:
                    raise IPBanFatalError("Binance HTTP 418 IP ban; collection is stopped") from exc
                if exc.code == 429:
                    retry_after = float(error_headers.get("retry-after", 0) or 0)
                    if attempt == self.max_retries:
                        raise RateLimitGapError(retry_after, headers=error_headers) from exc
                elif exc.code not in {500, 502, 503, 504} or attempt == self.max_retries:
                    raise
                else:
                    retry_after = 0.0
            except (TimeoutError, urllib.error.URLError):
                if attempt == self.max_retries: raise
                retry_after = 0
            # Honor the server delay while bounding a single blocked request;
            # the original Retry-After remains in RateLimitGapError telemetry.
            time.sleep(min(max(retry_after, min(2 ** attempt, 8)), self.MAX_RETRY_AFTER_SECONDS))
        raise AssertionError("retry loop exhausted")

    def get(self, market: str, path: str, params: dict[str, Any] | None = None) -> Any:
        """Backward-compatible payload-only API; use get_with_metadata for R3."""
        payload, _ = self.get_with_metadata(market, path, params)
        return payload

def dataset_hash(frame: pd.DataFrame) -> str:
    normalized = frame.reindex(sorted(frame.columns), axis=1)
    return hashlib.sha256(pd.util.hash_pandas_object(normalized, index=True).values.tobytes()).hexdigest()

def rest_coverage_status(dataset: str, requested_start: datetime | pd.Timestamp, now: datetime | pd.Timestamp | None = None) -> CoverageStatus:
    current = pd.Timestamp(now if now is not None else datetime.now(UTC)); current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    start = pd.Timestamp(requested_start); start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    if dataset in SHORT_RETENTION_MONTHS:
        cutoff = current - pd.DateOffset(months=SHORT_RETENTION_MONTHS[dataset])
    elif retention_days := SHORT_RETENTION_DAYS.get(dataset):
        cutoff = current - pd.Timedelta(days=retention_days)
    else:
        return CoverageStatus.AVAILABLE
    return CoverageStatus.HISTORICAL_UNAVAILABLE if start < cutoff else CoverageStatus.PARTIAL

def symbol_lifecycle_table(frame: pd.DataFrame, interval: str, symbol_column: str = "symbol", timestamp_column: str = "open_time") -> pd.DataFrame:
    if interval not in INTERVAL_MS: raise ValueError(f"unsupported fixed interval: {interval}")
    if missing := {symbol_column, timestamp_column} - set(frame.columns): raise ValueError(f"missing lifecycle columns: {', '.join(sorted(missing))}")
    expected = pd.Timedelta(milliseconds=INTERVAL_MS[interval]); records: list[dict[str, object]] = []
    for symbol, group in frame.groupby(symbol_column, sort=True):
        timestamps = pd.to_datetime(group[timestamp_column], utc=True).drop_duplicates().sort_values(); deltas = timestamps.diff().dropna(); gaps = int(sum(max(0, int(delta / expected) - 1) for delta in deltas[deltas > expected]))
        records.append({"symbol": symbol, "first_observed": timestamps.min(), "last_observed": timestamps.max(), "observed_rows": len(timestamps), "missing_intervals_inside_lifecycle": gaps})
    return pd.DataFrame.from_records(records)
