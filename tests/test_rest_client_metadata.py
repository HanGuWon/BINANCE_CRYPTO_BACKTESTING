from __future__ import annotations

import io
import json
import urllib.error

import pytest

from binance_research.data import IPBanFatalError, BinanceRestClient, DataIntegrityError, RateLimitGapError, parse_rate_limits


class _Response:
    status = 200

    def __init__(self, body: object) -> None:
        self.headers = {"X-MBX-USED-WEIGHT-1M": "7"}
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_get_with_metadata_preserves_http_headers_and_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: _Response({"ok": True}))
    payload, metadata = BinanceRestClient().get_with_metadata("um", "/fapi/v1/time")
    assert payload == {"ok": True}
    assert metadata.http_status == 200
    assert metadata.headers["x-mbx-used-weight-1m"] == "7"
    assert metadata.request_started_at and metadata.response_received_at
    assert metadata.latency_seconds >= 0


def test_429_honors_retry_after_then_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.HTTPError("https://fapi.binance.com/x", 429, "limited", {"Retry-After": "2"}, io.BytesIO(b"{}"))
    calls = iter([error, _Response({"ok": True})])
    sleeps: list[float] = []
    def _next(request, timeout):
        value = next(calls)
        if isinstance(value, BaseException):
            raise value
        return value
    monkeypatch.setattr("urllib.request.urlopen", _next)
    monkeypatch.setattr("time.sleep", sleeps.append)
    payload, _ = BinanceRestClient(max_retries=1).get_with_metadata("um", "/fapi/v1/time")
    assert payload["ok"] is True
    assert sleeps == [2.0]


def test_429_exhaustion_is_rate_limit_gap_and_418_is_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    error429 = urllib.error.HTTPError("https://fapi.binance.com/x", 429, "limited", {"Retry-After": "3"}, io.BytesIO(b"{}"))
    def _raise429(request, timeout):
        raise error429
    monkeypatch.setattr("urllib.request.urlopen", _raise429)
    with pytest.raises(RateLimitGapError) as raised:
        BinanceRestClient(max_retries=0).get_with_metadata("um", "/fapi/v1/time")
    assert raised.value.retry_after == 3
    error418 = urllib.error.HTTPError("https://fapi.binance.com/x", 418, "banned", {}, io.BytesIO(b"{}"))
    def _raise418(request, timeout):
        raise error418
    monkeypatch.setattr("urllib.request.urlopen", _raise418)
    with pytest.raises(IPBanFatalError):
        BinanceRestClient(max_retries=3).get_with_metadata("um", "/fapi/v1/time")


def test_parse_rate_limits_fails_closed() -> None:
    assert parse_rate_limits({"rateLimits": [{"rateLimitType": "REQUEST_WEIGHT", "limit": 2400}]})[0]["limit"] == 2400
    with pytest.raises(DataIntegrityError):
        parse_rate_limits({})
