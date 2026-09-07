"""Collection-only smoke evidence; never computes returns or strategy metrics."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from binance_research.collector import AppendOnlyEventStore, ForwardCollector


class _SmokeClient:
    def get(self, market: str, path: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"symbol": params["symbol"], "eventTime": 1_700_000_000_000, "endpoint": path, "value": "0.5"}


def run_smoke(symbol: str = "BTCUSDT") -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="r3-collection-smoke-") as directory:
        store = AppendOnlyEventStore(Path(directory))
        collector = ForwardCollector(store, _SmokeClient())  # type: ignore[arg-type]
        paths = collector.collect_r3_um_snapshot(symbol)
        envelopes = [json.loads(path.read_text(encoding="utf-8").splitlines()[-1]) for path in paths]
        bytes_written = sum(path.stat().st_size for path in paths)
        return {
            "status": "PASS",
            "symbol": symbol,
            "streams": sorted({str(item["stream"]) for item in envelopes}),
            "stream_count": len(envelopes),
            "bytes_written": bytes_written,
            "continuity_states": sorted({str(item["continuity_state"]) for item in envelopes}),
            "source_time_available_count": sum(bool(item["source_time_available"]) for item in envelopes),
            "api_key_streams_present": sorted(set(collector.R3_PUBLIC_STREAMS) & collector.REQUIRES_API_KEY),
            "outcome_fields_present": sorted(set().union(*(item.keys() for item in envelopes)) & {"gross_return", "net_return", "pnl", "sharpe", "hit_rate"}),
            # Engineering-only estimate using the verified USD-M weights for
            # this exact request set; this is not real storage evidence.
            "request_weight_budget_per_minute_upper_bound": 50 * sum(collector.R3_ENDPOINT_WEIGHTS.values()) / 15,
            "endpoint_weights": dict(sorted(collector.R3_ENDPOINT_WEIGHTS.items())),
        }


if __name__ == "__main__":
    print(json.dumps(run_smoke(), sort_keys=True))
