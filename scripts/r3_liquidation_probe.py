"""Short outcome-blind connectivity probe for the public forceOrder stream."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from binance_research.collector import liquidation_stream_url


async def probe(seconds: int = 5) -> dict[str, object]:
    import websockets
    url = liquidation_stream_url("ALL")
    try:
        async with websockets.connect(url, open_timeout=10, close_timeout=2, ping_interval=20, ping_timeout=20) as socket:
            try:
                message = await asyncio.wait_for(socket.recv(), timeout=seconds)
                return {"connected": True, "received": True, "message_bytes": len(message), "url": url}
            except asyncio.TimeoutError:
                return {"connected": True, "received": False, "url": url}
    except Exception as exc:
        return {"connected": False, "received": False, "error": type(exc).__name__, "url": url}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(probe(args.seconds)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
