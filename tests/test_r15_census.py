from __future__ import annotations

import urllib.parse

import pytest
import pandas as pd

from binance_research.census import classify_instrument, object_census_rows, symbol_census
from binance_research.data import ArchiveObject, BinanceArchiveClient, DataIntegrityError, deduplicate_klines, normalize_klines, validate_klines
from binance_research.panel import completed_cutoff_utc, feature_availability_matrix, lifecycle_records


def _page(prefixes: list[str], objects: list[tuple[str, int]], *, truncated: bool, token: str | None = None) -> bytes:
    common = "".join(f"<CommonPrefixes><Prefix>{p}</Prefix></CommonPrefixes>" for p in prefixes)
    contents = "".join(f"<Contents><Key>{key}</Key><Size>{size}</Size><LastModified>2026-08-21T00:00:00.000Z</LastModified><ETag>\"etag\"</ETag></Contents>" for key, size in objects)
    next_token = f"<NextContinuationToken>{token}</NextContinuationToken>" if token is not None else ""
    return f"<ListBucketResult xmlns=\"http://s3.amazonaws.com/doc/2006-03-01/\"><IsTruncated>{str(truncated).lower()}</IsTruncated>{next_token}{common}{contents}</ListBucketResult>".encode()


def test_s3_list_objects_v2_paginates_and_deduplicates() -> None:
    class FakeClient(BinanceArchiveClient):
        def __init__(self) -> None:
            super().__init__(".")
            self.calls: list[str] = []

        def _fetch(self, url: str) -> bytes:
            self.calls.append(url)
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            if query.get("continuation-token") == ["A"]:
                return _page(["root/B/"], [("root/B/file.zip", 2), ("root/A/file.zip", 1)], truncated=False)
            return _page(["root/A/"], [("root/A/file.zip", 1)] * 1000, truncated=True, token="A")

    prefixes, objects, pages = FakeClient().list_objects_v2("root/", delimiter="/")
    assert pages == 2
    assert prefixes == ["root/A/", "root/B/"]
    assert objects == [ArchiveObject("root/A/file.zip", 1, "2026-08-21T00:00:00.000Z", '"etag"'), ArchiveObject("root/B/file.zip", 2, "2026-08-21T00:00:00.000Z", '"etag"')]


@pytest.mark.parametrize("payload", [
    b"<ListBucketResult><IsTruncated>true</IsTruncated></ListBucketResult>",
    b"<ListBucketResult><IsTruncated>maybe</IsTruncated></ListBucketResult>",
    b"<ListBucketResult>",
])
def test_s3_listing_malformed_or_truncated_fails_closed(payload: bytes) -> None:
    class FakeClient(BinanceArchiveClient):
        def _fetch(self, url: str) -> bytes:
            return payload

    with pytest.raises(DataIntegrityError):
        FakeClient(".").list_objects_v2("root/")


def test_archive_census_deduplicates_months_and_exposes_gaps() -> None:
    objects = [
        ArchiveObject("data/spot/monthly/klines/OLDUSDT/15m/OLDUSDT-15m-2024-01.zip", 10),
        ArchiveObject("data/spot/monthly/klines/OLDUSDT/15m/OLDUSDT-15m-2024-03.zip", 12),
        ArchiveObject("data/spot/monthly/klines/OLDUSDT/15m/OLDUSDT-15m-2024-03.zip.CHECKSUM", 64),
        ArchiveObject("data/spot/monthly/klines/OLDUSDT/1h/OLDUSDT-1h-2024-02.zip", 8),
    ]
    rows = object_census_rows(objects, market="spot")
    census = symbol_census(rows)
    assert len(rows) == 2
    assert census.iloc[0].available_month_count == 2
    assert census.iloc[0].missing_month_count_inside_observed_span == 1


def test_instrument_policy_excludes_dated_um_and_leveraged_spot() -> None:
    assert classify_instrument("um", "BTCUSDT_250627").exclusion_reason == "DATED_CONTRACT_EXCLUDED"
    assert classify_instrument("spot", "BTCUPUSDT").exclusion_reason == "LEVERAGED_TOKEN_SUFFIX"
    assert classify_instrument("um", "BTCUSDT").eligible is True


def test_feature_availability_is_market_specific_and_fail_closed() -> None:
    matrix = feature_availability_matrix()
    funding = matrix[matrix.feature_id == "derivatives.funding_zscore"].iloc[0]
    premium = matrix[matrix.feature_id == "derivatives.premium_zscore"].iloc[0]
    assert funding.market_support == "um"
    assert "spot=NOT_APPLICABLE" in funding.market_coverage
    assert premium.market_support == "um"
    assert "spot=NOT_APPLICABLE" in premium.market_coverage
    assert bool(funding.historical_campaign_eligible) is False


def test_bounded_archive_window_does_not_infer_listing_or_delisting() -> None:
    frame = pd.DataFrame({
        "symbol": ["OLDUSDT", "OLDUSDT"],
        "open_time": pd.to_datetime(["2024-01-01T00:00Z", "2024-01-01T00:15Z"]),
    })
    record = lifecycle_records([frame], market="spot", interval="15m").iloc[0]
    assert record.listing_effective_start == "UNKNOWN"
    assert record.delisting_effective_end == "UNKNOWN"
    assert "bounded" in record.delisting_evidence


def test_signed_premium_validation_and_monthly_daily_overlap_policy() -> None:
    row = [1704067200000, -1.0, -0.5, -2.0, -1.5, 1.0, 1704068099999, 0.0, 1, 0.5, 0.0, 0]
    frame = normalize_klines([row])
    assert any(issue.code == "IMPOSSIBLE_OHLC" for issue in validate_klines(frame, "15m"))
    assert not any(issue.code == "IMPOSSIBLE_OHLC" for issue in validate_klines(frame, "15m", allow_negative=True))
    assert len(deduplicate_klines(normalize_klines([row, row]))) == 1
    assert completed_cutoff_utc(pd.Timestamp("2026-08-21T05:11:00Z"), "15m") == pd.Timestamp("2026-08-21T04:45:00Z")


def test_conflicting_archive_revision_listing_fails_closed() -> None:
    class FakeClient(BinanceArchiveClient):
        def _fetch(self, url: str) -> bytes:
            if "continuation-token" in url:
                return _page([], [("root/A/file.zip", 2)], truncated=False)
            return _page([], [("root/A/file.zip", 1)], truncated=True, token="A")

    with pytest.raises(DataIntegrityError, match="conflicting duplicate"):
        FakeClient(".").list_objects_v2("root/")
