from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.r3 import r3_ops
from ops.r3 import r3_v8_authorization as auth
from ops.r3.r3_v8_guardian import (
    GuardianError,
    GuardianConfig,
    _read_roster_expiry,
    assess_snapshot,
    run_persistent,
    run_once,
)
from ops.r3.verify_r3_v8_guardian_receipt import verify


def _identity(tmp_path: Path) -> dict[str, object]:
    return {
        "root": str((tmp_path / "scientific_raw_v8").resolve()),
        "implementation_commit": "e" * 40,
        "source_tree_sha256": "a" * 64,
        "registry_sha256": "b" * 64,
        "roster_sha256": "c" * 64,
        "roster_file_sha256": "1" * 64,
        "manifest_sha256": "d" * 64,
        "seal_sha256": "f" * 64,
        "seal_status": "SEALED",
        "manifest_chain_verification": True,
        "scientific_scope_status": "clean",
        "outcomes_accessed": False,
    }


def _zero_writer() -> dict[str, object]:
    return {"lock_pid": None, "lock_alive": False, "authorized_writer_count": 0, "duplicate_writers": [], "process_tree": []}


def _live_writer() -> dict[str, object]:
    return {"lock_pid": 101, "lock_alive": True, "authorized_writer_count": 1, "duplicate_writers": [], "process_tree": [{"pid": 101}]}


def _snapshot(tmp_path: Path, *, writer: dict[str, object] | None = None, census: list[dict[str, object]] | None = None, lock_exists: bool = False, chain_ok: bool = True, seal_ok: bool = True, identity_ok: bool = True, disk_state: str = "GREEN", expiry: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "identity": _identity(tmp_path),
        "identity_ok": identity_ok,
        "control_identity_sha256": "9" * 64,
        "writer": writer or _zero_writer(),
        "collector_candidate_census": census or [],
        "collector_lock_path": str((tmp_path / "scientific_raw_v8" / "control" / "collector.lock").resolve()),
        "collector_lock_path_exists": lock_exists,
        "chain_ok": chain_ok,
        "seal_ok": seal_ok,
        "disk_state": disk_state,
        "roster_expiry": expiry or {"known": True, "expired": False, "field": "effective_end"},
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
    }


def _config(tmp_path: Path, *, authorization: Path | None = None, preflight_receipt: Path | None = None) -> GuardianConfig:
    return GuardianConfig(
        root=tmp_path / "scientific_raw_v8",
        manifest=tmp_path / "manifest.json",
        seal=tmp_path / "seal.json",
        roster=tmp_path / "roster.json",
        launcher=tmp_path / "launch_r3_v8_resume.ps1",
        guardian_lock=tmp_path / "guardian.lock",
        receipt_root=tmp_path / "receipts",
        authorization=authorization,
        preflight_receipt=preflight_receipt,
        allow_test_overrides=True,
    )


def _authorization(tmp_path: Path, identity: dict[str, object], now: datetime) -> Path:
    preflight = tmp_path / "preflight.json"
    preflight.write_text("canonical preflight fixture\n", encoding="utf-8")
    value = {
        "record_type": r3_ops.RESUME_AUTHORIZATION_RECORD_TYPE,
        "authorization_id": "12345678-1234-5678-1234-567812345678",
        "authorized_by": "synthetic-test",
        "issued_at_utc": (now - timedelta(minutes=1)).isoformat(),
        "expires_at_utc": (now + timedelta(minutes=9)).isoformat(),
        "consumed_at_utc": None,
        "mode": "EXISTING_SEALED_V8_ONLY",
        "root": identity["root"],
        "implementation_commit": identity["implementation_commit"],
        "source_tree_sha256": identity["source_tree_sha256"],
        "registry_sha256": identity["registry_sha256"],
        "roster_sha256": identity["roster_sha256"],
        "launch_manifest_sha256": identity["manifest_sha256"],
        "launch_seal_sha256": identity["seal_sha256"],
        "preflight_receipt_path": str(preflight.resolve()),
        "preflight_receipt_sha256": r3_ops._sha256(preflight),
        "preflight_exit_code": 0,
        "preflight_writer": _zero_writer(),
    }
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_live_writer_is_no_action_and_never_launches(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, writer=_live_writer(), census=[{"pid": 101, "candidate": True, "in_authorized_collector_tree": True} ], lock_exists=True)
    assert assess_snapshot(snapshot)["decision"] == "NO_ACTION_LIVE"
    calls: list[str] = []
    result = run_once(_config(tmp_path), now=datetime(2026, 9, 7, tzinfo=UTC), snapshot_provider=lambda *_: snapshot, launcher_runner=lambda *_: calls.append("launch") or {"exit_code": 0})
    assert result["receipt"]["decision"] == "NO_ACTION_LIVE"
    assert calls == []


def test_live_writer_allows_authorized_descendant_but_not_external_candidate(tmp_path: Path) -> None:
    snapshot = _snapshot(
        tmp_path,
        writer={
            "lock_pid": 101,
            "lock_alive": True,
            "authorized_writer_count": 1,
            "duplicate_writers": [],
            "process_tree": [{"pid": 101}, {"pid": 102}],
        },
        census=[
            {"pid": 101, "candidate": True, "in_authorized_collector_tree": True},
            {"pid": 102, "candidate": True, "in_authorized_collector_tree": True},
        ],
        lock_exists=True,
    )
    assert assess_snapshot(snapshot)["decision"] == "NO_ACTION_LIVE"


def test_duplicate_outside_candidate_blocks(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, writer=_live_writer(), census=[{"pid": 101, "candidate": True, "in_authorized_collector_tree": True}, {"pid": 202, "candidate": True, "in_authorized_collector_tree": False}], lock_exists=True)
    assert assess_snapshot(snapshot)["decision"] == "BLOCKED_DUPLICATE_WRITER"


def test_zero_writer_without_authorization_records_blocker(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    result = run_once(_config(tmp_path), now=datetime(2026, 9, 7, tzinfo=UTC), snapshot_provider=lambda *_: snapshot)
    assert result["receipt"]["decision"] == "AUTHORIZATION_REQUIRED"
    assert result["receipt"]["outcomes_accessed"] is False


def test_production_cli_paths_cannot_be_redirected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config = GuardianConfig(
        root=config.root,
        manifest=config.manifest,
        seal=config.seal,
        roster=config.roster,
        launcher=config.launcher,
        guardian_lock=config.guardian_lock,
        receipt_root=config.receipt_root,
    )
    with pytest.raises(GuardianError, match="path override"):
        run_once(config, snapshot_provider=lambda *_: pytest.fail("must reject before inspection"))


def test_authorized_resume_runs_preflight_then_launcher_once(tmp_path: Path) -> None:
    now = datetime(2026, 9, 7, 3, 0, tzinfo=UTC)
    snapshot = _snapshot(tmp_path)
    auth = _authorization(tmp_path, snapshot["identity"], now)
    config = _config(tmp_path, authorization=auth)
    calls: list[str] = []

    def preflight(*_: object) -> dict[str, object]:
        calls.append("preflight")
        return {"command": ["canonical", "-PreflightOnly"], "exit_code": 0, "output": "PASS"}

    def launcher(*_: object) -> dict[str, object]:
        calls.append("launcher")
        return {"command": ["canonical", "-AuthorizationReceipt"], "exit_code": 0, "output": "started"}

    result = run_once(config, now=now, snapshot_provider=lambda *_: snapshot, preflight_runner=preflight, launcher_runner=launcher)
    assert result["receipt"]["decision"] == "RESUME_STARTED"
    assert calls == ["preflight", "launcher"]
    assert verify(Path(result["receipt_path"]))["status"] == "PASS"


def test_preflight_failure_never_launches(tmp_path: Path) -> None:
    now = datetime(2026, 9, 7, 3, 0, tzinfo=UTC)
    snapshot = _snapshot(tmp_path)
    auth = _authorization(tmp_path, snapshot["identity"], now)
    calls: list[str] = []
    result = run_once(_config(tmp_path, authorization=auth), now=now, snapshot_provider=lambda *_: snapshot, preflight_runner=lambda *_: {"exit_code": 9, "output": "blocked"}, launcher_runner=lambda *_: calls.append("launcher") or {"exit_code": 0})
    assert result["receipt"]["decision"] == "BLOCKED_PREFLIGHT"
    assert calls == []


def test_relative_authorization_path_is_rejected_before_resolution(tmp_path: Path) -> None:
    now = datetime(2026, 9, 7, 3, 0, tzinfo=UTC)
    snapshot = _snapshot(tmp_path)
    config = _config(tmp_path, authorization=Path("relative-auth.json"))
    result = run_once(config, now=now, snapshot_provider=lambda *_: snapshot)
    assert result["receipt"]["decision"] == "AUTHORIZATION_REQUIRED"
    assert result["receipt"]["reasons"] == ["authorization_path_not_absolute"]


def test_race_after_preflight_never_launches(tmp_path: Path) -> None:
    now = datetime(2026, 9, 7, 3, 0, tzinfo=UTC)
    before = _snapshot(tmp_path)
    after = _snapshot(tmp_path, writer=_live_writer(), census=[{"pid": 101, "candidate": True, "in_authorized_collector_tree": True}], lock_exists=True)
    auth = _authorization(tmp_path, before["identity"], now)
    values = iter([before, after])
    calls: list[str] = []
    result = run_once(_config(tmp_path, authorization=auth), now=now, snapshot_provider=lambda *_: next(values), preflight_runner=lambda *_: {"exit_code": 0, "output": "PASS"}, launcher_runner=lambda *_: calls.append("launcher") or {"exit_code": 0})
    assert result["receipt"]["decision"] == "BLOCKED_RACE_CHANGED"
    assert calls == []
    assert result["receipt"]["writer_after"]["authorized_writer_count"] == 1


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"lock_exists": True}, "BLOCKED_STALE_OR_UNKNOWN_LOCK"),
        ({"identity_ok": False}, "BLOCKED_IDENTITY"),
        ({"chain_ok": False}, "BLOCKED_CHAIN_OR_SEAL"),
        ({"seal_ok": False}, "BLOCKED_CHAIN_OR_SEAL"),
        ({"disk_state": "RED"}, "BLOCKED_DISK"),
        ({"expiry": {"known": False, "expired": True}}, "BLOCKED_ROSTER_EXPIRY_UNKNOWN"),
        ({"expiry": {"known": True, "expired": True}}, "BLOCKED_ROSTER_EXPIRED"),
    ],
)
def test_zero_writer_fail_closed_gates(tmp_path: Path, kwargs: dict[str, object], expected: str) -> None:
    assert assess_snapshot(_snapshot(tmp_path, **kwargs))["decision"] == expected


def test_unknown_collector_process_without_lock_blocks(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, census=[{"pid": 202, "candidate": True, "in_authorized_collector_tree": False}])
    assert assess_snapshot(snapshot)["decision"] == "BLOCKED_STALE_OR_UNKNOWN_LOCK"


def test_guardian_lock_collision_is_immutable_and_fail_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.guardian_lock.parent.mkdir(parents=True, exist_ok=True)
    config.guardian_lock.write_text(f"{os.getpid()}:existing", encoding="utf-8")
    result = run_once(config, now=datetime(2026, 9, 7, tzinfo=UTC), snapshot_provider=lambda *_: pytest.fail("must not inspect collector"))
    assert result["receipt"]["decision"] == "BLOCKED_GUARDIAN_LOCK_COLLISION"
    assert result["receipt"]["guardian_lock_disposition"] == "COLLISION"
    assert config.guardian_lock.is_file()


def test_stale_or_malformed_guardian_lock_is_not_removed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.guardian_lock.parent.mkdir(parents=True, exist_ok=True)
    config.guardian_lock.write_text("not-a-pid-token", encoding="utf-8")
    result = run_once(config, now=datetime(2026, 9, 7, tzinfo=UTC), snapshot_provider=lambda *_: pytest.fail("must not inspect collector"))
    assert result["receipt"]["decision"] == "BLOCKED_GUARDIAN_LOCK_COLLISION"
    assert result["receipt"]["reasons"] == ["GUARDIAN_LOCK_STALE_OR_MALFORMED"]
    assert config.guardian_lock.read_text(encoding="utf-8") == "not-a-pid-token"


def test_roster_expiry_requires_timezone_aware_effective_end(tmp_path: Path) -> None:
    path = tmp_path / "roster.json"
    now = datetime(2026, 9, 7, tzinfo=UTC)
    path.write_text(json.dumps({"effective_end": "2026-10-01T00:00:00+00:00"}), encoding="utf-8")
    assert _read_roster_expiry(path, now=now)["expired"] is False
    path.write_text(json.dumps({"effective_end": "2026-10-01T00:00:00"}), encoding="utf-8")
    assert _read_roster_expiry(path, now=now)["known"] is False
    path.write_text(json.dumps({}), encoding="utf-8")
    assert _read_roster_expiry(path, now=now)["known"] is False


def test_guardian_receipt_tamper_is_rejected(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    result = run_once(_config(tmp_path), now=datetime(2026, 9, 7, tzinfo=UTC), snapshot_provider=lambda *_: snapshot)
    receipt_path = Path(result["receipt_path"])
    value = json.loads(receipt_path.read_text(encoding="utf-8"))
    value["decision"] = "RESUME_STARTED"
    receipt_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(r3_ops.OperationsAuditError, match="mismatch"):
        verify(receipt_path)


def test_startup_installer_targets_only_guardian() -> None:
    installer = (Path(__file__).parents[1] / "install_r3_v8_startup.ps1").read_text(encoding="utf-8")
    wrapper = (Path(__file__).parents[1] / "run_r3_v8_guardian.ps1").read_text(encoding="utf-8")
    assert "run_r3_v8_guardian.ps1" in installer
    assert "-Persistent -PollSeconds 300" in installer
    assert "launch_r3_v8_resume.ps1" not in installer
    assert "-Persistent" in wrapper and "ops.r3.r3_v8_guardian" in wrapper


def test_persistent_poll_records_error_instead_of_dying(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def stop_after_error(_: float) -> None:
        raise KeyboardInterrupt

    assert run_persistent(
        config,
        snapshot_provider=lambda *_: (_ for _ in ()).throw(RuntimeError("synthetic metadata failure")),
        sleep_fn=stop_after_error,
    ) == 0
    receipts = list((tmp_path / "receipts").glob("R3_V8_GUARDIAN_ATTEMPT_*.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text(encoding="utf-8"))["decision"] == "BLOCKED_GUARDIAN_ERROR"


def test_standing_policy_mints_child_and_launcher_receives_child(tmp_path: Path) -> None:
    now = datetime(2026, 9, 7, 8, 0, tzinfo=UTC)
    identity = dict(auth.EXPECTED_IDENTITY)
    identity.update({"manifest_sha256": identity["launch_manifest_sha256"], "seal_sha256": identity["launch_seal_sha256"], "scientific_scope_status": "clean", "outcomes_accessed": False})
    snapshot = _snapshot(tmp_path)
    snapshot["identity"] = identity
    config = _config(tmp_path)
    config = GuardianConfig(
        root=config.root,
        manifest=config.manifest,
        seal=config.seal,
        roster=config.roster,
        launcher=config.launcher,
        guardian_lock=config.guardian_lock,
        receipt_root=config.receipt_root,
        standing_policy=auth.STANDING_POLICY_PATH,
        allow_test_overrides=True,
    )
    preflight_path: Path | None = None
    child_path: Path | None = None

    def preflight(_: GuardianConfig, authorization: Path, preflight: Path) -> dict[str, object]:
        nonlocal preflight_path
        preflight_path = preflight
        writer = _zero_writer()
        payload = {"status": "PASS", "identity": identity, "writer": writer}
        value = {
            "record_type": r3_ops.PREFLIGHT_RECEIPT_RECORD_TYPE,
            "recorded_at_utc": now.isoformat(),
            "command": ["r3_ops.py", "preflight"],
            "cwd": str(auth.REPO_ROOT),
            "exit_code": 0,
            "stdout_sha256": "0" * 64,
            "output": payload,
            "identity": identity,
            "writer": writer,
            "no_launch_assertion": True,
            "outcomes_accessed": False,
            "final_holdout": "UNTOUCHED",
            "r2b2": "NOT_ACCESSED",
            "forceorder_v3_migration": "NOT_STARTED",
        }
        preflight.parent.mkdir(parents=True, exist_ok=True)
        preflight.write_text(json.dumps(value), encoding="utf-8")
        assert not authorization.exists()
        return {"exit_code": 0, "output": "PASS"}

    def launcher(_: GuardianConfig, authorization: Path, __: Path) -> dict[str, object]:
        nonlocal child_path
        child_path = authorization
        return {"exit_code": 0, "command": ["canonical", "-AuthorizationReceipt", str(authorization)]}

    result = run_once(config, now=now, snapshot_provider=lambda *_: snapshot, preflight_runner=preflight, launcher_runner=launcher)
    assert result["receipt"]["decision"] == "RESUME_STARTED"
    assert preflight_path is not None and preflight_path.is_file()
    assert child_path is not None and child_path.is_file()
    child = json.loads(child_path.read_text(encoding="utf-8"))
    assert child["authorization_kind"] == auth.CHILD_AUTHORIZATION_KIND
    assert child["parent_policy_sha256"] == auth.EXPECTED_POLICY_FILE_SHA256


def test_persistent_unchanged_state_is_receipt_throttled(tmp_path: Path) -> None:
    config = _config(tmp_path)
    values = iter([_snapshot(tmp_path), _snapshot(tmp_path), _snapshot(tmp_path)])
    calls = {"sleep": 0}

    def stop_after_three(_: float) -> None:
        calls["sleep"] += 1
        if calls["sleep"] >= 3:
            raise KeyboardInterrupt

    assert run_persistent(
        config,
        snapshot_provider=lambda *_: next(values),
        sleep_fn=stop_after_three,
    ) == 0
    receipts = list((tmp_path / "receipts").glob("R3_V8_GUARDIAN_ATTEMPT_*.json"))
    assert len(receipts) == 1
    state = json.loads((tmp_path / "receipts" / "R3_V8_GUARDIAN_STATE.json").read_text(encoding="utf-8"))
    assert state["poll_count"] == 3
    assert state["emission_count"] == 1


def test_persistent_guardian_reenters_after_launcher_returns(tmp_path: Path) -> None:
    identity = dict(auth.EXPECTED_IDENTITY)
    identity.update({"manifest_sha256": identity["launch_manifest_sha256"], "seal_sha256": identity["launch_seal_sha256"], "scientific_scope_status": "clean", "outcomes_accessed": False})
    eligible = _snapshot(tmp_path)
    eligible["identity"] = identity
    live = _snapshot(
        tmp_path,
        writer={"lock_pid": 101, "lock_alive": True, "authorized_writer_count": 1, "duplicate_writers": [], "process_tree": [{"pid": 101}]},
        census=[{"pid": 101, "candidate": True, "in_authorized_collector_tree": True}],
        lock_exists=True,
    )
    live["identity"] = identity
    config = GuardianConfig(
        root=tmp_path / "scientific_raw_v8", manifest=tmp_path / "manifest.json", seal=tmp_path / "seal.json", roster=tmp_path / "roster.json",
        launcher=tmp_path / "launch_r3_v8_resume.ps1", guardian_lock=tmp_path / "guardian.lock", receipt_root=tmp_path / "receipts",
        standing_policy=auth.STANDING_POLICY_PATH, allow_test_overrides=True,
    )
    values = iter([eligible, eligible, live])
    launcher_calls: list[Path] = []

    def preflight(_: GuardianConfig, authorization: Path, preflight: Path) -> dict[str, object]:
        writer = _zero_writer()
        payload = {"status": "PASS", "identity": identity, "writer": writer}
        value = {
            "record_type": r3_ops.PREFLIGHT_RECEIPT_RECORD_TYPE, "recorded_at_utc": datetime.now(UTC).isoformat(),
            "command": ["r3_ops.py", "preflight"], "cwd": str(auth.REPO_ROOT), "exit_code": 0, "stdout_sha256": "0" * 64,
            "output": payload, "identity": identity, "writer": writer, "no_launch_assertion": True,
            "outcomes_accessed": False, "final_holdout": "UNTOUCHED", "r2b2": "NOT_ACCESSED", "forceorder_v3_migration": "NOT_STARTED",
        }
        preflight.parent.mkdir(parents=True, exist_ok=True)
        preflight.write_text(json.dumps(value), encoding="utf-8")
        assert not authorization.exists()
        return {"exit_code": 0, "output": "PASS"}

    def launcher(_: GuardianConfig, authorization: Path, __: Path) -> dict[str, object]:
        launcher_calls.append(authorization)
        return {"exit_code": 0, "output": "collector child exited cleanly"}

    sleeps = {"count": 0}

    def stop_after_second_poll(_: float) -> None:
        sleeps["count"] += 1
        if sleeps["count"] >= 2:
            raise KeyboardInterrupt

    assert run_persistent(
        config,
        snapshot_provider=lambda *_: next(values),
        preflight_runner=preflight,
        launcher_runner=launcher,
        sleep_fn=stop_after_second_poll,
    ) == 0
    assert len(launcher_calls) == 1
    receipts = list((tmp_path / "receipts").glob("R3_V8_GUARDIAN_ATTEMPT_*.json"))
    decisions = [json.loads(path.read_text(encoding="utf-8"))["decision"] for path in receipts]
    assert decisions == ["RESUME_STARTED", "NO_ACTION_LIVE"]
