from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import ops.r3.r3_ops as operations
from binance_research.r3_operations import append_manifest, build_manifest, write_health_receipt


def _fixture_root(tmp_path: Path, *, cycles: int = 3, gap_count: int = 0) -> Path:
    root = tmp_path / "scientific_raw_v8"
    stream = root / "raw_v1" / "um" / "ALL"
    stream.mkdir(parents=True)
    start = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    lines = []
    for index in range(cycles):
        target = start + timedelta(minutes=15 * index)
        payload = {
            "cycle_id": f"cycle-{index}",
            "target_bar_open": target.isoformat(),
            "target_bar_close": (target + timedelta(minutes=15)).isoformat(),
            "scheduled_collection_time": (target + timedelta(minutes=15, seconds=5)).isoformat(),
            "actual_collection_start": (target + timedelta(minutes=15, seconds=1)).isoformat(),
            "cycle_completed_at": (target + timedelta(minutes=15, seconds=2)).isoformat(),
            "clock_calibration_id": f"cal-{index}",
            "eligible_next_execution_time": (target + timedelta(minutes=30)).isoformat(),
        }
        lines.append(json.dumps({"stream": "cycle_metadata", "evidence_mode": "SCIENTIFIC", "payload": payload}))
    (stream / "cycle_metadata.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = build_manifest(root / "raw_v1", manifest_id="fixture-1")
    append_manifest(root / "raw_v1", manifest)
    write_health_receipt(
        root,
        campaign_id="r3_prospective_context_v1",
        manifest_sha256=manifest["manifest_sha256"],
        roster_sha256="b" * 64,
        stream_state={"status": "CYCLE_COMPLETE"},
        raw_root=root / "raw_v1",
        gap_count=gap_count,
        restart_count=gap_count,
        evidence_mode="SCIENTIFIC",
    )
    return root


def _identity() -> dict[str, object]:
    return {
        "implementation_commit": "e" * 40,
        "source_tree_sha256": "a" * 64,
        "registry_sha256": "b" * 64,
        "roster_sha256": "c" * 64,
        "manifest_sha256": "d" * 64,
        "seal_sha256": "f" * 64,
        "seal_status": "SEALED",
        "outcomes_accessed": False,
    }


def _writer() -> dict[str, object]:
    return {
        "lock_pid": 11,
        "lock_alive": True,
        "authorized_writer_count": 1,
        "duplicate_writers": [],
        "process_tree": [],
    }


def test_cycle_and_health_metadata_are_outcome_blind(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    cycles = operations._cycle_records(root)
    health = operations._health_records(root)
    assert len(cycles) == 3
    assert health[-1]["evidence_mode"] == "SCIENTIFIC"
    assert "gross_return" not in cycles[-1]


def test_watchdog_green_and_yellow_staleness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    monkeypatch.setattr(operations, "verify_identity", lambda *args, **kwargs: _identity())
    monkeypatch.setattr(operations, "audit_writer", lambda *args, **kwargs: _writer())
    monkeypatch.setattr(
        operations,
        "storage_metrics",
        lambda *args, **kwargs: {"disk_state": "GREEN", "free_disk_bytes": 10_000_000_000},
    )
    latest_eligible = datetime(2026, 9, 2, 13, 0, tzinfo=UTC)
    green = operations.watchdog_snapshot(root, now=latest_eligible + timedelta(seconds=30))
    assert green["state"] == "GREEN"
    yellow = operations.watchdog_snapshot(root, now=latest_eligible + timedelta(seconds=1_100))
    assert yellow["state"] == "YELLOW"
    assert "one_or_more_expected_cycles_late" in yellow["reasons"]


def test_watchdog_red_on_duplicate_writer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    monkeypatch.setattr(operations, "verify_identity", lambda *args, **kwargs: _identity())
    monkeypatch.setattr(
        operations,
        "audit_writer",
        lambda *args, **kwargs: {**_writer(), "duplicate_writers": [{"pid": 22}]},
    )
    monkeypatch.setattr(operations.shutil, "disk_usage", lambda _path: shutil._ntuple_diskusage(10_000, 1, 9_999))
    snapshot = operations.watchdog_snapshot(root, now=datetime(2026, 9, 2, 12, 45, 30, tzinfo=UTC))
    assert snapshot["state"] == "RED"
    assert "duplicate_writer" in snapshot["reasons"]


def test_writer_audit_counts_only_lock_owner_and_finds_external_writer(tmp_path: Path) -> None:
    root = tmp_path / "scientific_raw_v8"
    (root / "control").mkdir(parents=True)
    (root / "control" / "collector.lock").write_text("11", encoding="utf-8")
    command = "run_r3_prospective_collector.py --mode SCIENTIFIC --persistent --root D:\\BINANCE_CRYPTO_BACKTESTING_DATA\\r3_prospective_context_v1\\scientific_raw_v8 --roster-artifact 2026-09.json --launch-manifest R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json"
    rows = [
        {"pid": 11, "parent_pid": 12, "name": "python.exe", "executable": "C:\\Python\\python.exe", "command_line": command, "create_time": None},
        {"pid": 12, "parent_pid": 0, "name": "python.exe", "executable": "C:\\Hermes\\python.exe", "command_line": command, "create_time": None},
        {"pid": 22, "parent_pid": 0, "name": "python.exe", "executable": "C:\\Python\\python.exe", "command_line": command, "create_time": None},
    ]
    result = operations.audit_writer(root, snapshot=rows)
    assert result["authorized_writer_count"] == 1
    assert [item["pid"] for item in result["duplicate_writers"]] == [22]
    assert {item["pid"] for item in result["process_tree"]} == {11, 12}


def test_daily_receipt_is_append_only_and_duplicate_day_rejected(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    snapshot = {"identity": _identity(), "writer": _writer(), "first_cycle": None, "last_cycle": None, "expected_cycle_count": 0, "cycle_count": 0, "missing_cycle_count": 0, "latest_health": {"gap_count": 0, "restart_count": 0}, "manifest_chain_verification": True, "launch_seal_verification": True, "storage": {"bytes_deltas": [], "free_disk_bytes": 123}, "state": "GREEN"}
    receipt = operations.build_daily_receipt(snapshot, day="2026-09-02")
    destination = tmp_path / "daily.jsonl"
    lock = tmp_path / "daily.lock"
    operations.append_daily_receipt(receipt, destination=destination, lock_path=lock)
    with pytest.raises(operations.OperationsAuditError, match="already exists"):
        operations.append_daily_receipt(receipt, destination=destination, lock_path=lock)
    assert json.loads(destination.read_text(encoding="utf-8"))["outcomes_accessed"] is False
    assert not operations.FORBIDDEN_FIELDS.intersection(json.loads(destination.read_text(encoding="utf-8")))


def test_forbidden_outcome_field_fails_closed(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    path = root / "raw_v1" / "um" / "ALL" / "cycle_metadata.jsonl"
    value = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    value["payload"]["gross_return"] = 0.1
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(operations.OperationsAuditError, match="forbidden outcome"):
        operations._cycle_records(root)


def test_launcher_and_task_template_are_absolute_and_v8_only() -> None:
    launcher = (Path(__file__).parents[1] / "launch_r3_v8_resume.ps1").read_text(encoding="utf-8")
    template = (Path(__file__).parents[1] / "R3-Prospective-Scientific-v8.xml").read_text(encoding="utf-8")
    assert "D:\\BINANCE_CRYPTO_BACKTESTING_DATA\\r3_prospective_context_v1\\scientific_raw_v8" in launcher
    assert "--mode SCIENTIFIC --persistent" in launcher
    assert "Start-Process" not in launcher
    assert "new root" not in launcher.lower()
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in template
    assert "<RestartOnFailure>" in template
    assert "Password" not in template and "S-1-" not in template
