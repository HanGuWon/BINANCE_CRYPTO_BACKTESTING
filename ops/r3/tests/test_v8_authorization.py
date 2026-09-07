from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.r3 import r3_ops, r3_v8_authorization as auth


def _preflight(tmp_path: Path, identity: dict[str, object]) -> Path:
    writer = {"lock_pid": None, "lock_alive": False, "authorized_writer_count": 0, "duplicate_writers": [], "process_tree": []}
    payload = {"status": "PASS", "identity": identity, "writer": writer}
    value = {
        "record_type": r3_ops.PREFLIGHT_RECEIPT_RECORD_TYPE,
        "recorded_at_utc": "2026-09-07T08:00:00+00:00",
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
    path = tmp_path / "preflight.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_standing_policy_is_identity_bound_and_expiry_bounded() -> None:
    binding = auth.load_standing_policy(now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC))
    assert binding["policy_sha256"] == auth.EXPECTED_POLICY_FILE_SHA256
    assert binding["policy"]["expires_at_utc"] == "2026-10-01T00:00:00Z"
    assert binding["policy"]["credentials"] is False


def test_child_authorization_binds_parent_identity_and_preflight(tmp_path: Path) -> None:
    identity = dict(auth.EXPECTED_IDENTITY)
    preflight = _preflight(tmp_path, identity)
    binding = auth.load_standing_policy(now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC))
    child = auth.mint_child_authorization(
        binding,
        identity=identity,
        preflight_path=preflight,
        now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC),
        destination_root=tmp_path / "children",
    )
    checked = auth.verify_child_metadata(
        Path(child["path"]),
        policy_binding=binding,
        identity=identity,
        now=datetime(2026, 9, 7, 8, 1, tzinfo=UTC),
    )
    assert checked["status"] == "PASS"
    assert child["parent_policy_sha256"] == binding["policy_sha256"]
    value = json.loads(Path(child["path"]).read_text(encoding="utf-8"))
    assert set(value) == r3_ops.CHILD_RESUME_AUTHORIZATION_FIELDS
    assert value["preflight_receipt_sha256"] == r3_ops._sha256(preflight)


def test_child_replay_expiry_and_wrong_parent_fail_closed(tmp_path: Path) -> None:
    identity = dict(auth.EXPECTED_IDENTITY)
    preflight = _preflight(tmp_path, identity)
    binding = auth.load_standing_policy(now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC))
    child = auth.mint_child_authorization(
        binding, identity=identity, preflight_path=preflight,
        now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC), destination_root=tmp_path / "children",
    )
    with pytest.raises(auth.AuthorizationError, match="expired"):
        auth.verify_child_metadata(Path(child["path"]), policy_binding=binding, identity=identity, now=datetime(2026, 9, 7, 8, 10, tzinfo=UTC))
    wrong_binding = dict(binding)
    wrong_binding["policy_sha256"] = "f" * 64
    with pytest.raises(auth.AuthorizationError, match="parent policy mismatch"):
        auth.verify_child_metadata(Path(child["path"]), policy_binding=wrong_binding, identity=identity, now=datetime(2026, 9, 7, 8, 1, tzinfo=UTC))
    forged_binding = dict(binding)
    forged_binding["policy_sha256"] = "e" * 64
    with pytest.raises(auth.AuthorizationError, match="does not match"):
        auth.mint_child_authorization(
            forged_binding, identity=identity, preflight_path=preflight,
            now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC), destination_root=tmp_path / "forged",
        )
    value = json.loads(Path(child["path"]).read_text(encoding="utf-8"))
    value["consumed_at_utc"] = datetime(2026, 9, 7, 8, 2, tzinfo=UTC).isoformat()
    Path(child["path"]).write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(auth.AuthorizationError, match="already been consumed"):
        auth.verify_child_metadata(Path(child["path"]), policy_binding=binding, identity=identity, now=datetime(2026, 9, 7, 8, 3, tzinfo=UTC))


def test_child_issuer_is_exactly_guardian(tmp_path: Path) -> None:
    identity = dict(auth.EXPECTED_IDENTITY)
    preflight = _preflight(tmp_path, identity)
    binding = auth.load_standing_policy(now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC))
    child = auth.mint_child_authorization(
        binding, identity=identity, preflight_path=preflight,
        now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC), destination_root=tmp_path / "children",
    )
    value = json.loads(Path(child["path"]).read_text(encoding="utf-8"))
    value["authorized_by"] = "forged"
    Path(child["path"]).write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(auth.AuthorizationError, match="issuer"):
        auth.verify_child_metadata(Path(child["path"]), policy_binding=binding, identity=identity, now=datetime(2026, 9, 7, 8, 1, tzinfo=UTC))


def test_canonical_consumer_rejects_wrong_parent_and_issuer(tmp_path: Path) -> None:
    import hashlib

    base = dict(auth.EXPECTED_IDENTITY)
    identity = {
        **base,
        "manifest_sha256": base["launch_manifest_sha256"],
        "seal_sha256": base["launch_seal_sha256"],
        "roster_file_sha256": "1" * 64,
        "seal_status": "SEALED",
        "manifest_chain_verification": True,
        "outcomes_accessed": False,
    }
    writer = {"lock_pid": None, "lock_alive": False, "authorized_writer_count": 0, "duplicate_writers": [], "process_tree": []}
    issued = datetime(2026, 9, 7, 8, 0, tzinfo=UTC)
    preflight_path = tmp_path / "canonical_preflight.json"
    output = {"status": "PASS", "identity": identity, "writer": writer}
    command = [
        "r3_ops.py", "preflight", "--exact-v8", "--root", identity["root"],
        "--roster", str((tmp_path / "roster.json").resolve()),
        "--manifest", str((tmp_path / "manifest.json").resolve()),
        "--seal", str((tmp_path / "seal.json").resolve()),
        "--receipt", str(preflight_path.resolve()),
    ]
    preflight = {
        "record_type": r3_ops.PREFLIGHT_RECEIPT_RECORD_TYPE,
        "recorded_at_utc": issued.isoformat(), "command": command,
        "cwd": str(r3_ops.REPO_ROOT), "exit_code": 0,
        "stdout_sha256": hashlib.sha256(r3_ops._canonical_json(output).encode()).hexdigest(),
        "output": output, "identity": identity, "writer": writer,
        "no_launch_assertion": True, "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED", "r2b2": "NOT_ACCESSED", "forceorder_v3_migration": "NOT_STARTED",
    }
    preflight_path.write_text(r3_ops._canonical_json(preflight) + "\n", encoding="utf-8")
    binding = auth.load_standing_policy(now=issued)
    child = auth.mint_child_authorization(binding, identity=identity, preflight_path=preflight_path, now=issued, destination_root=tmp_path / "children")
    value = dict(child["authorization"])
    with pytest.raises(r3_ops.OperationsAuditError, match="canonical standing policy"):
        r3_ops._validate_resume_authorization(
            {**value, "parent_policy_sha256": "f" * 64},
            root=Path(identity["root"]), manifest=tmp_path / "manifest.json", seal=tmp_path / "seal.json", roster=tmp_path / "roster.json",
            preflight_receipt_path=preflight_path, identity=identity, writer=writer, now=issued + timedelta(minutes=1), consume=True,
        )
    with pytest.raises(r3_ops.OperationsAuditError, match="issuer"):
        r3_ops._validate_resume_authorization(
            {**value, "authorized_by": "forged"},
            root=Path(identity["root"]), manifest=tmp_path / "manifest.json", seal=tmp_path / "seal.json", roster=tmp_path / "roster.json",
            preflight_receipt_path=preflight_path, identity=identity, writer=writer, now=issued + timedelta(minutes=1), consume=True,
        )
