from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from binance_research.provenance import append_archive_revision
from binance_research.registry import ExperimentRecord, ExperimentRegistry, canonical_experiment_identity
from binance_research.reporting import ArtifactWriter, write_immutable_bytes


def _record(identifier: str, *, timestamp: str = "2024-01-01T00:00:00Z") -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id=identifier,
        feature_id="feature",
        code_hash="code",
        dataset_hash="dataset",
        market="um",
        symbol_universe=("BTCUSDT",),
        timeframe="15m",
        date_range=("2024-01-01", "2024-01-02"),
        parameters={"threshold": 1},
        target_horizon="15m",
        execution_assumptions={"next_open": True},
        fee_model={},
        slippage_model={},
        funding_model={"enabled": True},
        split_boundaries={},
        timestamp=timestamp,
        result_artifact_paths=("summary.csv",),
        final_holdout_accessed=False,
    )


def _revision(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "archive_url": "https://example/archive.zip",
        "old_sha256": "old",
        "new_sha256": "new",
        "old_last_modified": "1",
        "new_last_modified": "2",
        "detected_at": "2024-01-03T00:00:00Z",
        "revision_status": "DETECTED_VALID_REVISION",
        "campaigns_using_old_revision": "r1",
        "campaigns_using_new_revision": "r3",
    }
    result.update(overrides)
    return result


def test_registry_duplicate_is_idempotent_and_collision_preserves_bytes(tmp_path: Path) -> None:
    path = tmp_path / "registry.jsonl"
    registry = ExperimentRegistry(path)
    record = _record("one")
    registry.append(record)
    before = path.read_bytes()
    registry.append(record)
    assert path.read_bytes() == before
    assert canonical_experiment_identity(record) == canonical_experiment_identity(_record("one", timestamp="2024-01-02T00:00:00Z"))
    with pytest.raises(ValueError, match="immutable experiment identity collision"):
        registry.append(_record("one", timestamp="2024-01-02T00:00:00Z"))
    assert path.read_bytes() == before


def test_reporting_artifacts_are_immutable_and_report_is_clock_free(tmp_path: Path) -> None:
    writer = ArtifactWriter(tmp_path)
    writer.write_tables({"indicator_summary.csv": pd.DataFrame([{"trade_count": 1}])})
    before = (tmp_path / "indicator_summary.csv").read_bytes()
    writer.write_tables({"indicator_summary.csv": pd.DataFrame([{"trade_count": 1}])})
    assert (tmp_path / "indicator_summary.csv").read_bytes() == before
    with pytest.raises(ValueError, match="immutable collision"):
        writer.write_tables({"indicator_summary.csv": pd.DataFrame([{"trade_count": 2}])})
    assert (tmp_path / "indicator_summary.csv").read_bytes() == before
    report = writer.write_report({"verification_status": "PASS"})
    assert "NOT_SPECIFIED" in report.read_text(encoding="utf-8")
    report_before = report.read_bytes()
    writer.write_report({"verification_status": "PASS"})
    assert report.read_bytes() == report_before


def test_immutable_writer_rejects_symlink_without_following(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this Windows runner")
    with pytest.raises(ValueError, match="symlink"):
        write_immutable_bytes(link, b"payload")
    assert not target.exists()


def test_archive_revision_appends_without_rewriting_prefix_and_rejects_conflict(tmp_path: Path) -> None:
    path = tmp_path / "archive_revisions.csv"
    revision = _revision()
    append_archive_revision(path, revision)
    before = path.read_bytes()
    append_archive_revision(path, revision)
    assert path.read_bytes() == before
    append_archive_revision(path, _revision(archive_url="https://example/other.zip", new_sha256="other"))
    after_append = path.read_bytes()
    assert after_append.startswith(before)
    with pytest.raises(ValueError, match="immutable archive revision collision"):
        append_archive_revision(path, _revision(old_sha256="changed"))
    assert path.read_bytes() == after_append
