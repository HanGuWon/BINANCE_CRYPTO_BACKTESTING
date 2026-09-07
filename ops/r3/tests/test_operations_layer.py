from __future__ import annotations

import json
import os
import subprocess
import shutil
import sys
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
        "root": "C:\\fixture\\scientific_raw_v8",
        "implementation_commit": "e" * 40,
        "source_tree_sha256": "a" * 64,
        "registry_sha256": "b" * 64,
        "roster_sha256": "c" * 64,
        "roster_file_sha256": "1" * 64,
        "manifest_sha256": "d" * 64,
        "seal_sha256": "f" * 64,
        "seal_status": "SEALED",
        "manifest_chain_verification": True,
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


def _zero_writer() -> dict[str, object]:
    return {
        "lock_pid": None,
        "lock_alive": False,
        "authorized_writer_count": 0,
        "duplicate_writers": [],
        "process_tree": [],
    }


def _resume_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object], datetime]:
    root = tmp_path / "scientific_raw_v8"
    root.mkdir(parents=True)
    identity = _identity()
    identity["root"] = str(root.resolve())
    writer = _zero_writer()
    issued = datetime(2026, 9, 7, 2, 0, tzinfo=UTC)
    recorded = issued - timedelta(seconds=5)
    payload = {"status": "PASS", "identity": identity, "writer": writer}
    preflight = operations.build_preflight_receipt(
        payload,
        command=["python", "r3_ops.py", "preflight"],
        cwd=tmp_path,
        recorded_at=recorded,
    )
    preflight_path = tmp_path / "preflight.json"
    preflight_path.write_text(operations._canonical_json(preflight) + "\n", encoding="utf-8")
    authorization = {
        "record_type": operations.RESUME_AUTHORIZATION_RECORD_TYPE,
        "authorization_id": "12345678-1234-5678-1234-567812345678",
        "issued_at_utc": issued.isoformat(),
        "expires_at_utc": (issued + timedelta(minutes=10)).isoformat(),
        "consumed_at_utc": None,
        "authorized_by": "test-authorized-user",
        "mode": "SCIENTIFIC_RESUME_EXISTING_V8",
        "root": str(root.resolve()),
        "implementation_commit": identity["implementation_commit"],
        "source_tree_sha256": identity["source_tree_sha256"],
        "registry_sha256": identity["registry_sha256"],
        "roster_sha256": identity["roster_sha256"],
        "launch_manifest_sha256": identity["manifest_sha256"],
        "launch_seal_sha256": identity["seal_sha256"],
        "preflight_receipt_path": str(preflight_path.resolve()),
        "preflight_receipt_sha256": operations._sha256(preflight_path),
        "preflight_exit_code": 0,
        "preflight_writer": writer,
    }
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(operations._canonical_json(authorization) + "\n", encoding="utf-8")
    return authorization_path, preflight_path, identity, issued + timedelta(minutes=1)


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


def test_resume_authorization_validates_and_consumes_atomically(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    authorization_path, preflight_path, identity, now = _resume_fixture(tmp_path)
    monkeypatch.setattr(operations, "RESUME_AUTHORIZATION_LOCK", tmp_path / "authorization.lock")
    monkeypatch.setattr(operations, "audit_writer", lambda *args, **kwargs: _zero_writer())

    checked = operations.verify_resume_authorization(
        authorization_path,
        preflight_receipt_path=preflight_path,
        identity=identity,
        writer=_zero_writer(),
        now=now,
    )
    assert checked["consumed_at_utc"] is None
    consumed = operations.verify_resume_authorization(
        authorization_path,
        preflight_receipt_path=preflight_path,
        identity=identity,
        now=now,
        consume=True,
    )
    assert consumed["consumed_at_utc"] == now.isoformat()
    assert json.loads(authorization_path.read_text(encoding="utf-8"))["consumed_at_utc"] == now.isoformat()
    with pytest.raises(operations.OperationsAuditError, match="already been consumed"):
        operations.verify_resume_authorization(
            authorization_path,
            preflight_receipt_path=preflight_path,
            identity=identity,
            now=now,
            consume=True,
        )


def test_resume_authorization_rejects_missing_or_mismatched_preflight(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    authorization_path, preflight_path, identity, now = _resume_fixture(tmp_path)
    monkeypatch.setattr(operations, "RESUME_AUTHORIZATION_LOCK", tmp_path / "authorization.lock")
    monkeypatch.setattr(operations, "audit_writer", lambda *args, **kwargs: _zero_writer())
    preflight_path.unlink()
    with pytest.raises(operations.OperationsAuditError, match="preflight receipt is missing"):
        operations.verify_resume_authorization(
            authorization_path,
            preflight_receipt_path=preflight_path,
            identity=identity,
            now=now,
            consume=True,
        )
    authorization_path, preflight_path, identity, now = _resume_fixture(tmp_path / "mismatch")
    altered = json.loads(preflight_path.read_text(encoding="utf-8"))
    altered["identity"]["registry_sha256"] = "9" * 64
    altered["output"]["identity"]["registry_sha256"] = "9" * 64
    preflight_path.write_text(operations._canonical_json(altered) + "\n", encoding="utf-8")
    with pytest.raises(operations.OperationsAuditError, match="preflight receipt SHA mismatch"):
        operations.verify_resume_authorization(
            authorization_path,
            preflight_receipt_path=preflight_path,
            identity=identity,
            writer=_zero_writer(),
            now=now,
        )


def test_resume_authorization_rejects_identity_drift_and_active_writer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    authorization_path, preflight_path, identity, now = _resume_fixture(tmp_path)
    monkeypatch.setattr(operations, "RESUME_AUTHORIZATION_LOCK", tmp_path / "authorization.lock")
    drifted = dict(identity)
    drifted["registry_sha256"] = "9" * 64
    with pytest.raises(operations.OperationsAuditError, match="identity mismatch"):
        operations.verify_resume_authorization(
            authorization_path,
            preflight_receipt_path=preflight_path,
            identity=drifted,
            writer=_zero_writer(),
            now=now,
        )
    with pytest.raises(operations.OperationsAuditError, match="current collector lock is active"):
        operations.verify_resume_authorization(
            authorization_path,
            preflight_receipt_path=preflight_path,
            identity=identity,
            writer={**_zero_writer(), "lock_alive": True, "lock_pid": 99, "authorized_writer_count": 1},
            now=now,
        )


def test_preflight_receipt_is_immutable_and_schema_strict(tmp_path: Path) -> None:
    identity = _identity()
    writer = _zero_writer()
    receipt = operations.build_preflight_receipt(
        {"status": "PASS", "identity": identity, "writer": writer},
        command=["python", "r3_ops.py", "preflight"],
        cwd=tmp_path,
    )
    destination = tmp_path / "preflight.json"
    operations._write_json_exclusive(destination, receipt)
    with pytest.raises(operations.OperationsAuditError, match="already exists"):
        operations._write_json_exclusive(destination, receipt)
    malformed = dict(receipt)
    malformed["extra"] = True
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text(operations._canonical_json(malformed), encoding="utf-8")
    with pytest.raises(operations.OperationsAuditError, match="schema drift"):
        operations._validate_resume_authorization(
            {},
            authorization_path=malformed_path,
            preflight_receipt_path=None,
            identity=identity,
            writer=writer,
            now=datetime.now(UTC),
        )


def test_launcher_authorization_gate_behavior(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("Windows PowerShell is unavailable")
    repo = tmp_path / "repo"
    (repo / "ops" / "r3").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "campaigns" / "r3_prospective_context_v1" / "rosters").mkdir(parents=True)
    (repo / "root").mkdir()
    for path in (
        repo / "root",
        repo / "campaigns" / "r3_prospective_context_v1" / "rosters" / "2026-09.json",
        repo / "manifest.json",
        repo / "seal.json",
    ):
        if path.suffix:
            path.write_text("{}", encoding="utf-8")
    log = tmp_path / "launcher.log"
    fake_ops = '''
import json, os, sys
from pathlib import Path
log = Path(os.environ["FAKE_LOG"])
args = sys.argv[1:]
with log.open("a", encoding="utf-8") as handle:
    handle.write("ops:" + " ".join(args) + "\\n")
if args and args[0] == "verify-resume-authorization" and os.environ.get("FAKE_VERIFY_EXIT") == "1":
    raise SystemExit(1)
print(json.dumps({"status": "PASS"}))
'''
    fake_collector = '''
import os
from pathlib import Path
with Path(os.environ["FAKE_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write("collector\\n")
'''
    (repo / "ops" / "r3" / "r3_ops.py").write_text(fake_ops, encoding="utf-8")
    (repo / "scripts" / "run_r3_prospective_collector.py").write_text(fake_collector, encoding="utf-8")
    launcher = Path(__file__).parents[1] / "launch_r3_v8_resume.ps1"
    text = launcher.read_text(encoding="utf-8")
    text = text.replace("$RepoRoot = 'C:\\Users\\user\\Documents\\ChatGPT\\BINANCE 지표용 테스트'", f"$RepoRoot = '{repo}'")
    text = text.replace("$Python = 'C:\\Users\\user\\AppData\\Roaming\\uv\\python\\cpython-3.11-windows-x86_64-none\\python.exe'", f"$Python = '{Path(sys.executable)}'")
    text = text.replace("$ScientificRoot = 'D:\\BINANCE_CRYPTO_BACKTESTING_DATA\\r3_prospective_context_v1\\scientific_raw_v8'", f"$ScientificRoot = '{repo / 'root'}'")
    text = text.replace("$Roster = Join-Path $RepoRoot 'campaigns\\r3_prospective_context_v1\\rosters\\2026-09.json'", f"$Roster = '{repo / 'campaigns' / 'r3_prospective_context_v1' / 'rosters' / '2026-09.json'}'")
    text = text.replace("$LaunchManifest = 'D:\\BINANCE_CRYPTO_BACKTESTING_DATA\\r3_prospective_context_v1\\launch_control\\2026-09-production-v8\\R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json'", f"$LaunchManifest = '{repo / 'manifest.json'}'")
    text = text.replace("$LaunchSeal = 'D:\\BINANCE_CRYPTO_BACKTESTING_DATA\\r3_prospective_context_v1\\launch_control\\2026-09-production-v8\\R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json'", f"$LaunchSeal = '{repo / 'seal.json'}'")
    launcher_path = repo / "launch.ps1"
    launcher_path.write_text(text, encoding="utf-8")

    def run(auth: Path | None, *, verify_exit: bool = False) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "FAKE_LOG": str(log), "FAKE_VERIFY_EXIT": "1" if verify_exit else "0"}
        command = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(launcher_path)]
        if auth is not None:
            command += ["-AuthorizationReceipt", str(auth)]
        return subprocess.run(command, capture_output=True, text=True, env=env, timeout=30)

    missing = run(None)
    assert missing.returncode == 74
    assert not log.exists()
    preflight = tmp_path / "preflight.json"
    preflight.write_text("{}", encoding="utf-8")
    invalid = tmp_path / "invalid-auth.json"
    invalid.write_text(json.dumps({"preflight_receipt_path": str(preflight)}), encoding="utf-8")
    failed = run(invalid, verify_exit=True)
    assert failed.returncode != 0
    assert "collector" not in log.read_text(encoding="utf-8")
    log.unlink(missing_ok=True)
    valid = tmp_path / "valid-auth.json"
    valid.write_text(json.dumps({"preflight_receipt_path": str(preflight)}), encoding="utf-8")
    passed = run(valid)
    assert passed.returncode == 0
    rows = log.read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("ops:preflight ")
    assert rows[1].startswith("ops:verify-resume-authorization ")
    assert rows[2].startswith("ops:preflight ")
    assert rows[3] == "collector"
