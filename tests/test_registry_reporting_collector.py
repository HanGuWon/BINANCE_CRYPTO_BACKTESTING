from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from binance_research.collector import AppendOnlyEventStore, ContinuityTracker, ForwardCollector
from binance_research.data import RestResponseMetadata
from binance_research.registry import ExperimentRecord, ExperimentRegistry
from binance_research.reporting import REQUIRED_ARTIFACTS, ArtifactWriter


def _record(identifier: str) -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id=identifier, feature_id="x", code_hash="c", dataset_hash="d", market="spot",
        symbol_universe=("BTCUSDT",), timeframe="1h", date_range=("a", "b"), parameters={},
        target_horizon="1h", execution_assumptions={}, fee_model={}, slippage_model={}, funding_model={},
        split_boundaries={}, timestamp="2024-01-01T00:00:00+00:00", result_artifact_paths=(), final_holdout_accessed=False,
    )


def test_registry_is_append_only(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "registry.jsonl")
    registry.append(_record("one"))
    registry.append(_record("two"))
    assert [record.experiment_id for record in registry.read()] == ["one", "two"]
    assert len((tmp_path / "registry.jsonl").read_text().splitlines()) == 2


def test_reporter_always_emits_required_machine_artifacts(tmp_path: Path) -> None:
    writer = ArtifactWriter(tmp_path)
    paths = writer.write_tables({"indicator_summary.csv": pd.DataFrame([{"trade_count": 0}])})
    assert {path.name for path in paths} == set(REQUIRED_ARTIFACTS)
    assert (tmp_path / "final_holdout.csv").read_text().find("INSUFFICIENT EVIDENCE") >= 0


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def get(self, market: str, path: str, params: dict):
        self.calls.append((market, path, params))
        return {"ok": True, "path": path}


def test_forward_collector_keeps_raw_streams_append_only(tmp_path: Path) -> None:
    fake = FakeClient()
    collector = ForwardCollector(AppendOnlyEventStore(tmp_path), fake)  # type: ignore[arg-type]
    paths = collector.collect_um_snapshot("BTCUSDT")
    assert len(paths) == len(collector.UM_ENDPOINTS)
    collector.store.append("depth", "um", "BTCUSDT", {"second": True})
    lines = (tmp_path / "um" / "BTCUSDT" / "depth.jsonl").read_text().splitlines()
    assert len(lines) == 2
    envelope = json.loads(lines[0])
    assert envelope["schema_version"] == 2
    assert envelope["source_kind"] == "rest_snapshot"
    assert envelope["source_time_available"] is False
    assert envelope["continuity_state"] == "SOURCE_TIME_UNAVAILABLE"
    assert all(call[0] == "um" and call[2]["symbol"] == "BTCUSDT" for call in fake.calls)


def test_event_and_receipt_time_are_distinct_and_exchange_time_is_preserved(tmp_path: Path) -> None:
    path = AppendOnlyEventStore(tmp_path).append("depth", "um", "BTCUSDT", {"E": 1700000000000}, source_kind="websocket_event", endpoint="wss://example")
    envelope = json.loads(path.read_text().splitlines()[0])
    assert envelope["exchange_event_time"].startswith("2023-11-14T22:13:20")
    assert envelope["collector_receipt_time"] != envelope["exchange_event_time"]
    assert envelope["source_time_available"] is True
    assert envelope["continuity_state"] == "COMPLETE"


def test_continuity_tracker_fails_closed_on_restart_and_sequence_gap() -> None:
    tracker = ContinuityTracker()
    assert tracker.observe(10) == "RESTART_GAP"
    assert tracker.observe(11) == "COMPLETE"
    assert tracker.observe(13) == "SEQUENCE_GAP"
    assert tracker.restart() == "RESTART_GAP"
    assert tracker.observe(None) == "SOURCE_TIME_UNAVAILABLE"


def test_r3_snapshot_excludes_api_key_streams(tmp_path: Path) -> None:
    fake = FakeClient()
    collector = ForwardCollector(AppendOnlyEventStore(tmp_path), fake)  # type: ignore[arg-type]
    paths = collector.collect_r3_um_snapshot("BTCUSDT")
    assert len(paths) == len(collector.R3_PUBLIC_STREAMS)
    assert "top_position_ratio" not in collector.R3_PUBLIC_STREAMS
    assert "top_account_ratio" not in collector.R3_PUBLIC_STREAMS
    assert all("topLongShort" not in call[1] for call in fake.calls)


def test_r3_endpoint_weights_are_explicit_and_cover_public_streams() -> None:
    assert set(ForwardCollector.R3_ENDPOINT_WEIGHTS) == set(ForwardCollector.R3_PUBLIC_STREAMS)
    assert ForwardCollector.R3_ENDPOINT_WEIGHTS == {
        "open_interest": 1, "premium": 1, "book_ticker": 2,
        "klines_15m": 1, "premium_klines_15m": 1,
    }


def test_shadow_and_scientific_primary_stream_sets_are_identical() -> None:
    assert ForwardCollector.R3_SHADOW_STREAMS == ForwardCollector.R3_PRIMARY_STREAMS
    assert ForwardCollector.R3_PUBLIC_STREAMS == ForwardCollector.R3_PRIMARY_STREAMS
    assert ForwardCollector.R3_PRIMARY_STREAMS.isdisjoint(ForwardCollector.R3_DIAGNOSTIC_STREAMS)


def test_scientific_cli_rejects_manual_symbol_authority() -> None:
    from scripts.run_r3_prospective_collector import main
    import sys
    old = sys.argv
    try:
        sys.argv = ["collector", "--mode", "SCIENTIFIC", "--root", "D:/r3", "--symbols", "BTCUSDT", "--roster-sha256", "a" * 64]
        with pytest.raises(SystemExit):
            main()
    finally:
        sys.argv = old


def test_r3_collector_persists_response_metadata(tmp_path: Path) -> None:
    class MetadataClient(FakeClient):
        def get_with_metadata(self, market: str, path: str, params: dict):
            self.calls.append((market, path, params))
            return {"symbol": params["symbol"], "time": 1_700_000_000_000}, RestResponseMetadata(
                200, {"x-mbx-used-weight-1m": "11"}, "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00.100000+00:00", 0.1, "https://fapi.binance.com" + path
            )

    path = ForwardCollector(AppendOnlyEventStore(tmp_path), MetadataClient()).collect_r3_um_snapshot("BTCUSDT")[0]
    envelope = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert envelope["http_status"] == 200
    assert envelope["response_headers"]["x-mbx-used-weight-1m"] == "11"
    assert envelope["latency_seconds"] == 0.1
