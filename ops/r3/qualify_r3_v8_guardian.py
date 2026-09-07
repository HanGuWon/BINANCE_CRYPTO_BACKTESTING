"""Run the outcome-blind synthetic qualification matrix for the v8 guardian."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from ops.r3 import r3_ops
from ops.r3 import r3_v8_authorization as auth
from ops.r3.r3_v8_guardian import GuardianConfig, _publish_receipt, assess_snapshot, run_persistent


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECEIPT = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations" / "R3_V8_GUARDIAN_SYNTHETIC_QUALIFICATION_20260907_V1.json"


def _zero_writer() -> dict[str, Any]:
    return {"lock_pid": None, "lock_alive": False, "authorized_writer_count": 0, "duplicate_writers": [], "process_tree": []}


def _identity() -> dict[str, Any]:
    value = dict(auth.EXPECTED_IDENTITY)
    value.update({"manifest_sha256": value["launch_manifest_sha256"], "seal_sha256": value["launch_seal_sha256"], "scientific_scope_status": "clean", "outcomes_accessed": False})
    return value


def _snapshot(*, writer: dict[str, Any] | None = None, census: list[dict[str, Any]] | None = None, lock_exists: bool = False, identity_ok: bool = True, chain_ok: bool = True, seal_ok: bool = True, disk_state: str = "GREEN", expiry: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "identity": _identity(), "identity_ok": identity_ok, "control_identity_sha256": "a" * 64,
        "writer": writer or _zero_writer(), "collector_candidate_census": census or [],
        "collector_lock_path": "C:\\synthetic\\collector.lock", "collector_lock_path_exists": lock_exists,
        "chain_ok": chain_ok, "seal_ok": seal_ok, "disk_state": disk_state,
        "roster_expiry": expiry or {"known": True, "expired": False}, "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED", "r2b2": "NOT_ACCESSED", "forceorder_v3_migration": "NOT_STARTED",
    }


def _write_preflight(path: Path, identity: dict[str, Any]) -> None:
    writer = _zero_writer()
    output = {"status": "PASS", "identity": identity, "writer": writer}
    value = {
        "record_type": r3_ops.PREFLIGHT_RECEIPT_RECORD_TYPE, "recorded_at_utc": datetime.now(UTC).isoformat(),
        "command": ["r3_ops.py", "preflight"], "cwd": str(auth.REPO_ROOT), "exit_code": 0,
        "stdout_sha256": "0" * 64, "output": output, "identity": identity, "writer": writer,
        "no_launch_assertion": True, "outcomes_accessed": False, "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED", "forceorder_v3_migration": "NOT_STARTED",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _case_persistent_reentry() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config = GuardianConfig(
            root=root / "scientific_raw_v8", manifest=root / "manifest.json", seal=root / "seal.json", roster=root / "roster.json",
            launcher=root / "launch.ps1", guardian_lock=root / "guardian.lock", receipt_root=root / "receipts",
            standing_policy=auth.STANDING_POLICY_PATH, allow_test_overrides=True,
        )
        identity = _identity()
        eligible = _snapshot(); eligible["identity"] = identity
        live = _snapshot(
            writer={"lock_pid": 101, "lock_alive": True, "authorized_writer_count": 1, "duplicate_writers": [], "process_tree": [{"pid": 101}]},
            census=[{"pid": 101, "candidate": True, "in_authorized_collector_tree": True}], lock_exists=True,
        ); live["identity"] = identity
        values = iter([eligible, eligible, live]); launches: list[Path] = []

        def preflight(_: GuardianConfig, authorization: Path, preflight_path: Path) -> dict[str, Any]:
            _write_preflight(preflight_path, identity)
            if authorization.exists():
                raise AssertionError("pending child path already exists")
            return {"exit_code": 0, "output": "PASS"}

        def launcher(_: GuardianConfig, authorization: Path, __: Path) -> dict[str, Any]:
            launches.append(authorization)
            return {"exit_code": 0, "output": "child exited"}

        sleeps = {"count": 0}

        def stop(_: float) -> None:
            sleeps["count"] += 1
            if sleeps["count"] >= 2:
                raise KeyboardInterrupt

        result = run_persistent(config, snapshot_provider=lambda *_: next(values), preflight_runner=preflight, launcher_runner=launcher, sleep_fn=stop)
        if result != 0 or len(launches) != 1:
            raise AssertionError(f"persistent re-entry failed: result={result}, launches={len(launches)}")
        receipts = sorted((root / "receipts").glob("R3_V8_GUARDIAN_ATTEMPT_*.json"))
        decisions = [json.loads(path.read_text(encoding="utf-8")).get("decision") for path in receipts]
        if decisions != ["RESUME_STARTED", "NO_ACTION_LIVE"]:
            raise AssertionError(f"unexpected re-entry decisions: {decisions}")


def _case_throttle() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config = GuardianConfig(receipt_root=root / "receipts", guardian_lock=root / "guardian.lock", allow_test_overrides=True)
        now = datetime(2026, 9, 7, 8, 0, tzinfo=UTC)
        snapshot = _snapshot()
        from ops.r3.r3_v8_guardian import _base_receipt
        receipt = _base_receipt(config, now=now, decision="NO_ACTION_LIVE", reasons=[], snapshot=snapshot, lock_disposition="ACQUIRED_RELEASED")
        first = _publish_receipt(config, receipt, now=now, throttle=True)
        second = _publish_receipt(config, receipt, now=now, throttle=True)
        if not first.get("emitted") or second.get("emitted"):
            raise AssertionError("unchanged receipt was not throttled")
        if len(list((root / "receipts").glob("R3_V8_GUARDIAN_ATTEMPT_*.json"))) != 1:
            raise AssertionError("receipt throttle emitted more than one immutable receipt")


def run_matrix() -> list[dict[str, Any]]:
    live = {"lock_pid": 101, "lock_alive": True, "authorized_writer_count": 1, "duplicate_writers": [], "process_tree": [{"pid": 101}]}
    cases: list[tuple[str, Callable[[], None]]] = [
        ("live_writer_no_action", lambda: _assert(assess_snapshot(_snapshot(writer=live, census=[{"pid": 101, "candidate": True, "in_authorized_collector_tree": True}], lock_exists=True))["decision"] == "NO_ACTION_LIVE")),
        ("external_duplicate_blocks", lambda: _assert(assess_snapshot(_snapshot(writer=live, census=[{"pid": 101, "candidate": True, "in_authorized_collector_tree": True}, {"pid": 202, "candidate": True, "in_authorized_collector_tree": False}], lock_exists=True))["decision"] == "BLOCKED_DUPLICATE_WRITER")),
        ("zero_writer_without_policy_requires_authorization", lambda: _assert(assess_snapshot(_snapshot())["decision"] == "RESUME_ELIGIBLE")),
        ("identity_gate", lambda: _assert(assess_snapshot(_snapshot(identity_ok=False))["decision"] == "BLOCKED_IDENTITY")),
        ("chain_gate", lambda: _assert(assess_snapshot(_snapshot(chain_ok=False))["decision"] == "BLOCKED_CHAIN_OR_SEAL")),
        ("seal_gate", lambda: _assert(assess_snapshot(_snapshot(seal_ok=False))["decision"] == "BLOCKED_CHAIN_OR_SEAL")),
        ("disk_gate", lambda: _assert(assess_snapshot(_snapshot(disk_state="RED"))["decision"] == "BLOCKED_DISK")),
        ("roster_unknown_gate", lambda: _assert(assess_snapshot(_snapshot(expiry={"known": False, "expired": True}))["decision"] == "BLOCKED_ROSTER_EXPIRY_UNKNOWN")),
        ("roster_expired_gate", lambda: _assert(assess_snapshot(_snapshot(expiry={"known": True, "expired": True}))["decision"] == "BLOCKED_ROSTER_EXPIRED")),
        ("stale_lock_gate", lambda: _assert(assess_snapshot(_snapshot(lock_exists=True))["decision"] == "BLOCKED_STALE_OR_UNKNOWN_LOCK")),
        ("standing_policy_identity_and_expiry", lambda: _assert(auth.load_standing_policy(now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC))["policy"]["expires_at_utc"] == "2026-10-01T00:00:00Z")),
        ("child_mint_atomic", lambda: _case_child()),
        ("child_wrong_parent_rejected", lambda: _case_child_wrong_parent()),
        ("child_expiry_rejected", lambda: _case_child_expiry()),
        ("child_issuer_rejected", lambda: _case_child_issuer()),
        ("persistent_reentry_after_child_exit", _case_persistent_reentry),
        ("unchanged_state_receipt_throttle", _case_throttle),
    ]
    results: list[dict[str, Any]] = []
    for name, function in cases:
        try:
            function()
            results.append({"case": name, "status": "PASS"})
        except Exception as exc:
            results.append({"case": name, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
    return results


def _assert(condition: bool) -> None:
    if not condition:
        raise AssertionError("synthetic assertion failed")


def _new_child() -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    directory = Path(tempfile.mkdtemp(prefix="r3-v8-auth-"))
    identity = _identity(); preflight = directory / "preflight.json"; _write_preflight(preflight, identity)
    binding = auth.load_standing_policy(now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC))
    child = auth.mint_child_authorization(binding, identity=identity, preflight_path=preflight, now=datetime(2026, 9, 7, 8, 0, tzinfo=UTC), destination_root=directory / "children")
    return identity, binding, Path(child["path"]), directory


def _case_child() -> None:
    identity, binding, path, directory = _new_child()
    try:
        _assert(auth.verify_child_metadata(path, policy_binding=binding, identity=identity, now=datetime(2026, 9, 7, 8, 1, tzinfo=UTC))["status"] == "PASS")
    finally:
        import shutil
        shutil.rmtree(directory, ignore_errors=True)


def _case_child_wrong_parent() -> None:
    identity, binding, path, directory = _new_child()
    try:
        forged = dict(binding); forged["policy_sha256"] = "f" * 64
        try:
            auth.verify_child_metadata(path, policy_binding=forged, identity=identity, now=datetime(2026, 9, 7, 8, 1, tzinfo=UTC))
        except auth.AuthorizationError:
            return
        raise AssertionError("wrong parent accepted")
    finally:
        import shutil
        shutil.rmtree(directory, ignore_errors=True)


def _case_child_expiry() -> None:
    identity, binding, path, directory = _new_child()
    try:
        try:
            auth.verify_child_metadata(path, policy_binding=binding, identity=identity, now=datetime(2026, 9, 7, 8, 10, tzinfo=UTC))
        except auth.AuthorizationError:
            return
        raise AssertionError("expired child accepted")
    finally:
        import shutil
        shutil.rmtree(directory, ignore_errors=True)


def _case_child_issuer() -> None:
    identity, binding, path, directory = _new_child()
    try:
        value = json.loads(path.read_text(encoding="utf-8")); value["authorized_by"] = "forged"; path.write_text(json.dumps(value), encoding="utf-8")
        try:
            auth.verify_child_metadata(path, policy_binding=binding, identity=identity, now=datetime(2026, 9, 7, 8, 1, tzinfo=UTC))
        except auth.AuthorizationError:
            return
        raise AssertionError("forged issuer accepted")
    finally:
        import shutil
        shutil.rmtree(directory, ignore_errors=True)


def _body_sha(value: dict[str, Any]) -> str:
    body = dict(value); body.pop("body_sha256", None)
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def publish(path: Path, matrix: list[dict[str, Any]]) -> None:
    receipt = {
        "schema_version": 1,
        "record_type": "R3_V8_GUARDIAN_SYNTHETIC_QUALIFICATION",
        "receipt_path": str(path.resolve()),
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "matrix": matrix,
        "safe_skip_destructive_live_crash_test": "SAFE_SKIP_DESTRUCTIVE_LIVE_CRASH_TEST",
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
        "write_contract": {"write_once": True, "atomic_publish_required": True, "create_mode": "O_CREAT|O_EXCL", "overwrite": False, "flush_fsync_before_publish": True},
        "body_sha256": "",
    }
    receipt["status"] = "PASS" if all(item["status"] == "PASS" for item in matrix) else "FAIL"
    receipt["body_sha256"] = _body_sha(receipt)
    r3_ops._write_json_exclusive(path, receipt)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args(argv)
    matrix = run_matrix()
    if all(item["status"] == "PASS" for item in matrix):
        publish(args.receipt.resolve(), matrix)
    print(json.dumps({"status": "PASS" if all(item["status"] == "PASS" for item in matrix) else "FAIL", "matrix": matrix, "receipt": str(args.receipt.resolve())}, sort_keys=True))
    return 0 if all(item["status"] == "PASS" for item in matrix) else 1


if __name__ == "__main__":
    raise SystemExit(main())
