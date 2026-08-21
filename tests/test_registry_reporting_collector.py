from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from binance_research.collector import AppendOnlyEventStore, ForwardCollector
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
    assert json.loads(lines[0])["schema_version"] == 1
    assert all(call[0] == "um" and call[2]["symbol"] == "BTCUSDT" for call in fake.calls)

