from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncIterator

from .data import BinanceRestClient


class AppendOnlyEventStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def append(self, stream: str, market: str, symbol: str, payload: Any) -> Path:
        destination = self.root / market / symbol / f"{stream.replace('/', '_')}.jsonl"
        destination.parent.mkdir(parents=True, exist_ok=True)
        envelope = {"schema_version": 1, "source": "binance", "market_type": market,
                    "symbol": symbol, "stream": stream, "collected_at": datetime.now(UTC).isoformat(), "payload": payload}
        descriptor = os.open(destination, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            os.write(descriptor, (json.dumps(envelope, separators=(",", ":")) + "\n").encode())
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return destination


def route_liquidation_event(payload: dict[str, Any], requested_symbol: str = "ALL") -> tuple[str, str]:
    """Return explicit market/symbol provenance for a raw liquidation payload."""
    order = payload.get("o") if isinstance(payload.get("o"), dict) else {}
    symbol = str(order.get("s") or payload.get("s") or requested_symbol)
    discriminator = payload.get("market_type", payload.get("marketType", payload.get("st")))
    market = {1: "um", 2: "cm", "1": "um", "2": "cm", "um": "um", "cm": "cm"}.get(discriminator)
    stream = str(payload.get("stream", "")).lower()
    if market is None and ("@cm" in stream or "coin" in stream):
        market = "cm"
    if market is None and requested_symbol != "ALL":
        market = "um"
    return market or "unknown", symbol


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
        "top_position_ratio": ("/futures/data/topLongShortPositionRatio", {"period": "5m", "limit": 500}),
        "top_account_ratio": ("/futures/data/topLongShortAccountRatio", {"period": "5m", "limit": 500}),
    }
    REQUIRES_API_KEY = frozenset({"top_position_ratio", "top_account_ratio"})

    def __init__(self, store: AppendOnlyEventStore, client: BinanceRestClient | None = None) -> None:
        self.store, self.client = store, client or BinanceRestClient()

    def collect_um_snapshot(self, symbol: str) -> list[Path]:
        paths: list[Path] = []
        for stream, (endpoint, defaults) in self.UM_ENDPOINTS.items():
            if stream in self.REQUIRES_API_KEY and not os.getenv("BINANCE_API_KEY"):
                paths.append(self.store.append("collector_status", "um", symbol, {"stream": stream, "status": "SKIPPED_API_KEY_REQUIRED", "endpoint": endpoint}))
                continue
            paths.append(self.store.append(stream, "um", symbol, self.client.get("um", endpoint, {"symbol": symbol, **defaults})))
        return paths

    async def stream_liquidations(self, symbol: str = "ALL") -> AsyncIterator[dict[str, Any]]:
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
                            market, event_symbol = route_liquidation_event(payload, symbol)
                            self.store.append("liquidation", market, event_symbol, payload)
                            yield payload
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
