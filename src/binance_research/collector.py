from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncIterator

from .data import BinanceRestClient, IPBanFatalError, RateLimitGapError, RestResponseMetadata
from .r3_streams import normalize_stream_payload


class AppendOnlyEventStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def append(self, stream: str, market: str, symbol: str, payload: Any, *, source_kind: str = "rest_snapshot", endpoint: str | None = None, request_params: dict[str, Any] | None = None, continuity_state: str = "COMPLETE", sequence_id: int | str | None = None, response_metadata: RestResponseMetadata | dict[str, Any] | None = None, evidence_mode: str | None = None) -> Path:
        if continuity_state not in {"COMPLETE", "RESTART_GAP", "POLL_GAP", "SOURCE_TIME_UNAVAILABLE", "SEQUENCE_GAP", "SCHEMA_ERROR", "RATE_LIMIT_GAP", "CLOCK_UNCERTAINTY_GAP"}:
            raise ValueError(f"unknown continuity state: {continuity_state}")
        receipt_time = datetime.now(UTC).isoformat()
        event_time = _extract_exchange_event_time(payload)
        effective_state = continuity_state if event_time is not None or continuity_state != "COMPLETE" else "SOURCE_TIME_UNAVAILABLE"
        destination = self.root / market / symbol / f"{stream.replace('/', '_')}.jsonl"
        destination.parent.mkdir(parents=True, exist_ok=True)
        envelope = {"schema_version": 2, "source": "binance", "market_type": market,
                    "symbol": symbol, "stream": stream, "endpoint": endpoint,
                    "source_kind": source_kind, "exchange_event_time": event_time,
                    "source_time_available": event_time is not None,
                    "collector_receipt_time": receipt_time, "request_params": request_params,
                    "sequence_id": sequence_id, "continuity_state": effective_state,
                    "payload": payload}
        if evidence_mode is not None:
            envelope["evidence_mode"] = evidence_mode
        if response_metadata is not None:
            metadata = response_metadata if isinstance(response_metadata, dict) else response_metadata.__dict__
            envelope.update({"http_status": metadata.get("http_status"),
                             "response_headers": metadata.get("headers", {}),
                             "request_started_at": metadata.get("request_started_at"),
                             "response_received_at": metadata.get("response_received_at"),
                             "corrected_response_receipt_time": metadata.get("corrected_response_receipt_time"),
                             "clock_offset_ms": metadata.get("clock_offset_ms"),
                             "clock_round_trip_ms": metadata.get("clock_round_trip_ms"),
                             "clock_uncertainty_ms": metadata.get("clock_uncertainty_ms"),
                             "clock_calibration_id": metadata.get("clock_calibration_id"),
                             "latency_seconds": metadata.get("latency_seconds"),
                             "request_url": metadata.get("url")})
        descriptor = os.open(destination, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            os.write(descriptor, (json.dumps(envelope, separators=(",", ":")) + "\n").encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return destination


def _extract_exchange_event_time(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for value in (payload.get("E"), payload.get("T"), payload.get("eventTime"), payload.get("timestamp"), payload.get("time"), payload.get("observation_time")):
        if value is None:
            continue
        try:
            number = float(value)
            if number > 1e11:
                return datetime.fromtimestamp(number / 1000, UTC).isoformat()
            if number > 1e9:
                return datetime.fromtimestamp(number, UTC).isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            if isinstance(value, str) and value:
                return value
    return None


class ContinuityTracker:
    """Fail-closed sequence/restart tracking for forward streams."""

    def __init__(self) -> None:
        self.previous_sequence: int | None = None
        self.restarted = True

    def restart(self) -> str:
        self.previous_sequence = None
        self.restarted = True
        return "RESTART_GAP"

    def observe(self, sequence_id: int | None) -> str:
        if sequence_id is None:
            return "SOURCE_TIME_UNAVAILABLE"
        state = "COMPLETE"
        if self.previous_sequence is not None and sequence_id != self.previous_sequence + 1:
            state = "SEQUENCE_GAP"
        elif self.restarted:
            state = "RESTART_GAP"
        self.previous_sequence = sequence_id
        self.restarted = False
        return state


def route_liquidation_event(payload: dict[str, Any], requested_symbol: str = "ALL", *, endpoint: str | None = None) -> tuple[str, str]:
    """Return explicit market/symbol provenance for a raw liquidation payload."""
    order = payload.get("o") if isinstance(payload.get("o"), dict) else {}
    symbol = str(order.get("s") or payload.get("s") or requested_symbol)
    raw_discriminators = []
    if order.get("st") is not None:
        raw_discriminators.append(order["st"])
    for key in ("market_type", "marketType", "st"):
        if payload.get(key) is not None:
            raw_discriminators.append(payload[key])
    normalized = [{1: "um", 2: "cm", "1": "um", "2": "cm", "um": "um", "cm": "cm"}.get(value) for value in raw_discriminators]
    known = {value for value in normalized if value is not None}
    if len(known) > 1:
        raise ValueError("contradictory forceOrder market discriminators")
    market = next(iter(known), None)
    stream = str(payload.get("stream", "")).lower()
    if market is None and ("@cm" in stream or "coin" in stream):
        market = "cm"
    if market is None and endpoint and "fstream.binance.com" in endpoint:
        market = "um"
    if market is None and requested_symbol != "ALL":
        market = "um"
    return market or "unknown", symbol


def observed_forceorder_pressure(payload: dict[str, Any], *, endpoint: str | None = None) -> dict[str, Any]:
    """Create the frozen observable; forced SELL is positive pressure."""
    order = payload.get("o") if isinstance(payload.get("o"), dict) else {}
    side = str(order.get("S") or payload.get("S") or "").upper()
    qty = float(order.get("l") or 0.0)
    avg_price = float(order.get("ap") or order.get("p") or 0.0)
    signed = qty * avg_price if side == "SELL" else -qty * avg_price if side == "BUY" else None
    market, symbol = route_liquidation_event(payload, endpoint=endpoint)
    return {
        "observable": "observed_forceorder_pressure",
        "status": "OBSERVED_FORCEORDER_EVENT",
        "market": market,
        "symbol": symbol,
        "exchange_event_time": payload.get("E"),
        "trade_order_time": order.get("T") or order.get("t"),
        "side": side or None,
        "original_quantity": order.get("q"),
        "last_filled_quantity": order.get("l"),
        "accumulated_filled_quantity": order.get("z"),
        "order_price": order.get("p"),
        "average_fill_price": order.get("ap"),
        "position_side": order.get("ps"),
        "subtype": order.get("st") or payload.get("st"),
        "signed_observed_notional": signed,
        "raw_payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }


def liquidation_stream_url(symbol: str = "ALL") -> str:
    """Return the current Binance Futures raw market-stream liquidation URL."""
    stream = "!forceOrder@arr" if symbol == "ALL" else f"{symbol.lower()}@forceOrder"
    return f"wss://fstream.binance.com/market/ws/{stream}"


class ForwardCollector:
    """Forward-only public market-data collector; no trading methods exist."""

    UM_ENDPOINTS: dict[str, tuple[str, dict[str, Any]]] = {
        "open_interest": ("/fapi/v1/openInterest", {}),
        "premium": ("/fapi/v1/premiumIndex", {}),
        "book_ticker": ("/fapi/v1/ticker/bookTicker", {}),
        "depth": ("/fapi/v1/depth", {"limit": 100}),
        "agg_trades": ("/fapi/v1/aggTrades", {"limit": 1000}),
        "oi_history": ("/futures/data/openInterestHist", {"period": "5m", "limit": 500}),
        "taker_ratio": ("/futures/data/takerlongshortRatio", {"period": "5m", "limit": 500}),
        "klines_15m": ("/fapi/v1/klines", {"interval": "15m", "limit": 3}),
        "premium_klines_15m": ("/fapi/v1/premiumIndexKlines", {"interval": "15m", "limit": 3}),
        "top_position_ratio": ("/futures/data/topLongShortPositionRatio", {"period": "5m", "limit": 500}),
        "top_account_ratio": ("/futures/data/topLongShortAccountRatio", {"period": "5m", "limit": 500}),
    }
    REQUIRES_API_KEY = frozenset({"top_position_ratio", "top_account_ratio"})
    R3_PRIMARY_STREAMS = frozenset({"open_interest", "premium", "book_ticker", "klines_15m", "premium_klines_15m"})
    R3_DIAGNOSTIC_STREAMS = frozenset({"depth", "agg_trades", "oi_history", "taker_ratio"})
    R3_PUBLIC_STREAMS = R3_PRIMARY_STREAMS
    R3_SHADOW_STREAMS = R3_PRIMARY_STREAMS
    # USD-M REST reference weights for the exact request shapes above.  The
    # two /futures/data endpoints are documented as IP weight 0; telemetry is
    # still retained and any contradictory header fails the launch gate.
    R3_ENDPOINT_WEIGHTS = {
        "open_interest": 1,
        "premium": 1,
        "book_ticker": 2,
        "klines_15m": 1,
        "premium_klines_15m": 1,
    }

    def __init__(self, store: AppendOnlyEventStore, client: BinanceRestClient | None = None) -> None:
        self.store, self.client = store, client or BinanceRestClient()
        self.clock_calibration = None

    def collect_um_snapshot(self, symbol: str) -> list[Path]:
        paths: list[Path] = []
        for stream, (endpoint, defaults) in self.UM_ENDPOINTS.items():
            if stream in self.REQUIRES_API_KEY and not os.getenv("BINANCE_API_KEY"):
                paths.append(self.store.append("collector_status", "um", symbol, {"stream": stream, "status": "SKIPPED_API_KEY_REQUIRED", "endpoint": endpoint}))
                continue
            params = {"symbol": symbol, **defaults}
            paths.append(self.store.append(stream, "um", symbol, self.client.get("um", endpoint, params), source_kind="rest_snapshot", endpoint=endpoint, request_params=params))
        return paths

    def collect_r3_um_snapshot(self, symbol: str, *, evidence_mode: str | None = None) -> list[Path]:
        """Collect only the explicitly public R3 v1 streams."""
        return self._collect_snapshot(symbol, self.R3_PUBLIC_STREAMS, evidence_mode=evidence_mode)

    def collect_engineering_shadow_snapshot(self, symbol: str, *, evidence_mode: str = "ENGINEERING_SHADOW") -> list[Path]:
        """Collect roster-required primary sources with explicit evidence mode."""
        return self._collect_snapshot(symbol, self.R3_SHADOW_STREAMS, evidence_mode=evidence_mode)

    def _collect_snapshot(self, symbol: str, streams: frozenset[str], *, evidence_mode: str | None = None) -> list[Path]:
        paths: list[Path] = []
        for stream in sorted(streams):
            endpoint, defaults = self.UM_ENDPOINTS[stream]
            params = {"symbol": symbol, **defaults}
            try:
                response_metadata = None
                if hasattr(self.client, "get_with_metadata"):
                    payload, response_metadata = self.client.get_with_metadata("um", endpoint, params)
                else:
                    payload = self.client.get("um", endpoint, params)
            except IPBanFatalError as exc:
                paths.append(self.store.append("collector_status", "um", symbol, {"stream": stream, "error": type(exc).__name__, "fatal": True}, source_kind="collector_control", endpoint=endpoint, request_params=params, continuity_state="POLL_GAP", evidence_mode=evidence_mode))
                raise
            except RateLimitGapError as exc:
                paths.append(self.store.append("collector_status", "um", symbol, {"stream": stream, "error": type(exc).__name__, "retry_after": exc.retry_after}, source_kind="collector_control", endpoint=endpoint, request_params=params, continuity_state="RATE_LIMIT_GAP", response_metadata={"headers": exc.headers}, evidence_mode=evidence_mode))
                continue
            except Exception as exc:
                state = "RATE_LIMIT_GAP" if "429" in str(exc) or "rate" in str(exc).lower() else "POLL_GAP"
                paths.append(self.store.append("collector_status", "um", symbol, {"stream": stream, "error": type(exc).__name__}, source_kind="collector_control", endpoint=endpoint, request_params=params, continuity_state=state, evidence_mode=evidence_mode))
                continue
            if response_metadata is not None and self.clock_calibration is not None:
                received = datetime.fromisoformat(response_metadata.response_received_at.replace("Z", "+00:00"))
                corrected = received.timestamp() + float(self.clock_calibration.offset_ms) / 1000.0
                response_metadata = {
                    "http_status": response_metadata.http_status,
                    "headers": response_metadata.headers,
                    "request_started_at": response_metadata.request_started_at,
                    "response_received_at": response_metadata.response_received_at,
                    "corrected_response_receipt_time": datetime.fromtimestamp(corrected, UTC).isoformat(),
                    "clock_offset_ms": float(self.clock_calibration.offset_ms),
                    "clock_round_trip_ms": int(self.clock_calibration.round_trip_ms),
                    "clock_uncertainty_ms": float(self.clock_calibration.round_trip_ms) / 2.0 + 1.0,
                    "clock_calibration_id": self.clock_calibration.calibration_id,
                    "latency_seconds": response_metadata.latency_seconds,
                    "url": response_metadata.url,
                }
            if stream in {"klines_15m", "premium_klines_15m"}:
                receipt_time = (response_metadata.get("corrected_response_receipt_time") or response_metadata.get("response_received_at")) if isinstance(response_metadata, dict) else (getattr(response_metadata, "response_received_at", None) if response_metadata is not None else None)
                receipt_time = receipt_time or datetime.now(UTC).isoformat()
                try:
                    normalized = normalize_stream_payload(stream, symbol, payload, receipt_time=receipt_time)
                except Exception as exc:
                    paths.append(self.store.append("collector_status", "um", symbol, {"stream": stream, "error": type(exc).__name__}, source_kind="collector_control", endpoint=endpoint, request_params=params, response_metadata=response_metadata, continuity_state="SCHEMA_ERROR", evidence_mode=evidence_mode))
                    continue
                if not normalized:
                    paths.append(self.store.append("collector_status", "um", symbol, {"stream": stream, "status": "NO_COMPLETED_ROWS"}, source_kind="collector_control", endpoint=endpoint, request_params=params, response_metadata=response_metadata, continuity_state="POLL_GAP", evidence_mode=evidence_mode))
                for row in normalized:
                    paths.append(self.store.append(stream, "um", symbol, row, source_kind="rest_snapshot_normalized", endpoint=endpoint, request_params=params, response_metadata=response_metadata, evidence_mode=evidence_mode))
            else:
                paths.append(self.store.append(stream, "um", symbol, payload, source_kind="rest_snapshot", endpoint=endpoint, request_params=params, response_metadata=response_metadata, evidence_mode=evidence_mode))
        return paths

    async def stream_liquidations(self, symbol: str = "ALL", *, evidence_mode: str | None = None) -> AsyncIterator[dict[str, Any]]:
        """Yield and persist raw USD-M force-order stream events."""
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("install the streaming extra: pip install -e '.[streaming]'") from exc
        # Liquidations are MARKET streams; all-market payloads may contain UM/CM.
        # Binance appends st=1 (UM) or st=2 (CM) after the CM migration.
        url = liquidation_stream_url(symbol)
        backoff = 1
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2**22) as socket:
                    backoff = 1
                    async for message in socket:
                        decoded = json.loads(message)
                        events = decoded if isinstance(decoded, list) else [decoded]
                        for payload in events:
                            market, event_symbol = route_liquidation_event(payload, symbol, endpoint=url)
                            response_metadata = None
                            if self.clock_calibration is not None:
                                response_metadata = {"corrected_response_receipt_time": datetime.now(UTC).isoformat(), "clock_offset_ms": float(self.clock_calibration.offset_ms), "clock_round_trip_ms": int(self.clock_calibration.round_trip_ms), "clock_uncertainty_ms": float(self.clock_calibration.round_trip_ms) / 2.0 + 1.0, "clock_calibration_id": self.clock_calibration.calibration_id}
                            self.store.append("liquidation", market, event_symbol, payload, source_kind="websocket_event", endpoint=url, sequence_id=payload.get("u") or payload.get("U"), response_metadata=response_metadata, evidence_mode=evidence_mode)
                            yield payload
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.store.append("collector_status", "um", symbol, {"error": type(exc).__name__}, source_kind="collector_control", endpoint=url, continuity_state="RESTART_GAP", evidence_mode=evidence_mode)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
