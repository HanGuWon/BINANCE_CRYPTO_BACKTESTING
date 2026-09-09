"""One-shot, outcome-blind OS supervisor for the sealed R3 v8 guardian.

This module is deliberately not a guardian loop and has no collector-launch or
child-authorization capability. Each invocation terminates after one decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ops.r3 import r3_ops
from ops.r3 import r3_v8_authorization
from ops.r3 import r3_v8_guardian

V8_ROOT = r3_ops.V8_ROOT
V8_MANIFEST = r3_ops.V8_MANIFEST
V8_SEAL = r3_ops.V8_SEAL
V8_ROSTER = r3_ops.V8_ROSTER
V8_CONTROL_ROOT = r3_ops.V8_CONTROL_ROOT
GUARDIAN_LOCK_PATH = V8_CONTROL_ROOT / "R3_V8_GUARDIAN.lock"
COLLECTOR_LOCK_PATH = V8_ROOT / "control" / "collector.lock"
SUPERVISOR_LOCK_PATH = V8_CONTROL_ROOT / "R3_V8_EXTERNAL_SUPERVISOR.lock"
RECEIPT_ROOT = r3_ops.OPERATIONS_ROOT / "external_supervisor"
STALE_ARCHIVE_ROOT = r3_ops.OPERATIONS_ROOT / "guardian" / "supervisor_stale_locks"
CANONICAL_GUARDIAN = REPO_ROOT / "ops" / "r3" / "run_r3_v8_guardian.ps1"

EXPECTED_IMPLEMENTATION = "ecebc49dff41eeec33af62c2c85a75c5a0bd2922"
EXPECTED_SOURCE_TREE = "b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688"
EXPECTED_REGISTRY = "c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a"
EXPECTED_ROSTER = "bb05514dfc78cfca3b736488b1454f4cb022da0110e2cbf69f53c505f543ea79"
EXPECTED_MANIFEST = "cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659"
EXPECTED_SEAL = "ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85"
EXPECTED_POLICY = "6a23cf36e00b15ed5e5a46f1273052e946699a8e21a32b56588c4ae4f82e1e7c"
POLICY_EXPIRY = datetime(2026, 10, 1, tzinfo=UTC)

Decision = dict[str, Any]
ProcessRow = Mapping[str, Any]
PidAlive = Callable[[int], bool]
ArchiveHook = Callable[[Path, str, datetime], Mapping[str, Any]]
LaunchHook = Callable[[], Mapping[str, Any]]


class SupervisorBlocked(RuntimeError):
    def __init__(self, decision: str, reason: str) -> None:
        super().__init__(reason)
        self.decision = decision
        self.reason = reason


def _now(value: datetime | None = None) -> datetime:
    return (value or datetime.now(UTC)).astimezone(UTC)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pid_is_alive(pid: int) -> bool:
    try:
        import psutil
        return bool(psutil.pid_exists(int(pid)))
    except Exception:
        if int(pid) == os.getpid():
            return True
        try:
            os.kill(int(pid), 0)
        except OSError:
            return False
        return True


def _canonical_guardian_candidates(rows: Sequence[ProcessRow]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for row in rows:
        executable = Path(str(row.get("executable") or row.get("name") or "")).name.lower()
        command = " ".join(str(row.get("command_line") or "").lower().split())
        if not executable.startswith("python") or not executable.endswith(".exe"):
            continue
        if "-m ops.r3.r3_v8_guardian" not in command:
            continue
        found.append(dict(row))
    return sorted(found, key=lambda item: int(item.get("pid", 0) or 0))


def _read_lock(path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    if not path.is_file():
        return {"path": str(path), "exists": False, "raw": None, "pid": None, "valid": True}
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return {"path": str(path), "exists": True, "raw": None, "pid": None, "valid": False, "error": f"read:{type(exc).__name__}"}
    if path == GUARDIAN_LOCK_PATH:
        token = raw.split(":", 1)
        valid = len(token) == 2 and token[0].isdigit() and int(token[0]) > 0 and bool(token[1])
        return {"path": str(path), "exists": True, "raw": raw, "pid": int(token[0]) if valid else None, "valid": valid}
    valid = raw.isdigit() and int(raw) > 0
    return {"path": str(path), "exists": True, "raw": raw, "pid": int(raw) if valid else None, "valid": valid}


def _identity_summary(identity: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(identity, Mapping):
        return {"ok": False}
    expected = {
        "implementation_commit": EXPECTED_IMPLEMENTATION,
        "source_tree_sha256": EXPECTED_SOURCE_TREE,
        "registry_sha256": EXPECTED_REGISTRY,
        "roster_sha256": EXPECTED_ROSTER,
        "manifest_sha256": EXPECTED_MANIFEST,
        "seal_sha256": EXPECTED_SEAL,
    }
    checks = {field: str(identity.get(field)) == value for field, value in expected.items()}
    checks["scientific_scope_status"] = identity.get("scientific_scope_status") == "clean"
    checks["outcomes_accessed"] = identity.get("outcomes_accessed") is False
    return {"ok": all(checks.values()), "checks": checks, **{field: identity.get(field) for field in expected}}


def collect_state(
    *,
    now: datetime | None = None,
    process_snapshot: Sequence[ProcessRow] | None = None,
    identity_loader: Callable[[], Mapping[str, Any]] | None = None,
    policy_loader: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    current = _now(now)
    rows = list(process_snapshot) if process_snapshot is not None else r3_ops._process_snapshot()
    identity_error: str | None = None
    try:
        identity = dict((identity_loader or (lambda: r3_ops.verify_identity(require_exact_v8=True)))())
    except Exception as exc:
        identity = None
        identity_error = f"{type(exc).__name__}:{exc}"
    policy_error: str | None = None
    try:
        loader = policy_loader or r3_v8_authorization.load_standing_policy
        loaded_policy = dict(loader(now=current))
        policy = dict(loaded_policy.get("policy") or loaded_policy)
        loaded_sha = loaded_policy.get("policy_sha256")
        if loaded_sha is not None and str(loaded_sha) != EXPECTED_POLICY:
            raise ValueError("standing policy SHA does not match the sealed policy")
    except Exception as exc:
        policy = None
        policy_error = f"{type(exc).__name__}:{exc}"
    try:
        watchdog = r3_ops.watchdog_snapshot(
            V8_ROOT,
            manifest=V8_MANIFEST,
            seal=V8_SEAL,
            roster=V8_ROSTER,
            now=current,
            require_exact_v8=True,
            process_snapshot=rows,
        )
    except Exception as exc:
        watchdog = {"writer": {}, "manifest_chain_verification": False, "launch_seal_verification": False, "error": f"{type(exc).__name__}:{exc}"}
    writer = dict(watchdog.get("writer") or {})
    guardian_candidates = _canonical_guardian_candidates(rows)
    collector_candidates = r3_v8_guardian._candidate_census(
        rows,
        root=V8_ROOT,
        roster=V8_ROSTER,
        manifest=V8_MANIFEST,
        writer=writer,
    )
    return {
        "recorded_at_utc": current.isoformat(),
        "process_rows": [dict(row) for row in rows],
        "guardian_candidates": guardian_candidates,
        "collector_candidates": collector_candidates,
        "guardian_lock": _read_lock(GUARDIAN_LOCK_PATH),
        "collector_lock": _read_lock(COLLECTOR_LOCK_PATH),
        "writer": writer,
        "identity": identity,
        "identity_summary": _identity_summary(identity),
        "identity_error": identity_error,
        "policy": policy,
        "policy_sha256": (loaded_sha if "loaded_sha" in locals() else None),
        "policy_error": policy_error,
        "watchdog": watchdog,
        "chain_ok": bool(watchdog.get("manifest_chain_verification")),
        "seal_ok": bool(watchdog.get("launch_seal_verification")),
        "disk_state": (watchdog.get("storage") or {}).get("disk_state"),
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "batch_002": "NOT_STARTED",
        "backfill": False,
    }


def _archive_lock(path: Path, kind: str, now: datetime) -> Mapping[str, Any]:
    path = Path(path).resolve()
    if not path.is_file():
        raise SupervisorBlocked("BLOCK_LOCK_DISAPPEARED", f"{kind} lock disappeared before archive")
    source_sha = _sha256(path)
    STALE_ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    destination = STALE_ARCHIVE_ROOT / f"{kind}_{now.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid.uuid4().hex}.lock"
    data = path.read_bytes()
    with destination.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    copied_sha = _sha256(destination)
    if copied_sha != source_sha:
        raise SupervisorBlocked("BLOCK_LOCK_ARCHIVE_VERIFY", f"{kind} stale-lock archive SHA mismatch")
    reread = destination.read_bytes()
    if hashlib.sha256(reread).hexdigest() != source_sha:
        raise SupervisorBlocked("BLOCK_LOCK_ARCHIVE_VERIFY", f"{kind} stale-lock reread SHA mismatch")
    path.unlink()
    return {
        "kind": kind,
        "original_path": str(path),
        "archive_path": str(destination),
        "original_sha256": source_sha,
        "archive_sha256": copied_sha,
        "removed_after_fsync": True,
    }


def _prove_stale_and_archive(
    lock: Mapping[str, Any],
    *,
    kind: str,
    candidates: Sequence[ProcessRow],
    now: datetime,
    archive_hook: ArchiveHook,
    pid_alive: PidAlive,
) -> Mapping[str, Any] | None:
    if not lock.get("exists"):
        return None
    if not lock.get("valid") or lock.get("pid") is None:
        raise SupervisorBlocked(f"BLOCK_{kind.upper()}_LOCK_AMBIGUOUS", f"{kind} lock is malformed or unreadable")
    pid = int(lock["pid"])
    if pid_alive(pid) or any(int(row.get("pid", 0) or 0) == pid for row in candidates):
        raise SupervisorBlocked(f"BLOCK_{kind.upper()}_LOCK_ACTIVE", f"{kind} lock owner is alive or has a matching candidate")
    return dict(archive_hook(Path(str(lock["path"])), kind.lower(), now))


@contextmanager
def supervisor_lock(path: Path = SUPERVISOR_LOCK_PATH) -> Iterator[str]:
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}:{uuid.uuid4().hex}"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SupervisorBlocked("BLOCK_SUPERVISOR_LOCK_COLLISION", "another external supervisor invocation owns the lock") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token)
            handle.flush()
            os.fsync(handle.fileno())
        yield token
    finally:
        try:
            if path.read_text(encoding="utf-8").strip() == token:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def assess_state(
    state: Mapping[str, Any],
    *,
    now: datetime | None = None,
    archive_hook: ArchiveHook | None = None,
    launch_guardian: LaunchHook | None = None,
    pid_alive: PidAlive = _pid_is_alive,
) -> Decision:
    current = _now(now)
    identity = state.get("identity")
    summary = state.get("identity_summary") or _identity_summary(identity if isinstance(identity, Mapping) else None)
    if not summary.get("ok") or state.get("identity_error"):
        return {"decision": "BLOCK_IDENTITY_DRIFT", "reasons": [str(state.get("identity_error") or "exact sealed-v8 identity failed")]}
    policy = state.get("policy")
    if state.get("policy_error") or not isinstance(policy, Mapping):
        return {"decision": "BLOCK_POLICY_INVALID", "reasons": [str(state.get("policy_error") or "standing policy unavailable")]}
    expires = policy.get("expires_at_utc")
    try:
        policy_expiry = datetime.fromisoformat(str(expires).replace("Z", "+00:00")) if expires is not None else None
    except ValueError:
        policy_expiry = None
    if policy_expiry is None or current >= POLICY_EXPIRY or current >= policy_expiry.astimezone(UTC):
        return {"decision": "BLOCK_POLICY_EXPIRED", "reasons": ["standing policy expired or has an invalid expiry"]}
    if not state.get("chain_ok") or not state.get("seal_ok"):
        return {"decision": "BLOCK_CHAIN_OR_SEAL", "reasons": ["manifest chain or launch seal failed"]}
    if state.get("disk_state") == "RED":
        return {"decision": "BLOCK_DISK", "reasons": ["disk state is RED"]}
    guardian_candidates = list(state.get("guardian_candidates") or [])
    writer = state.get("writer") or {}
    collector_candidates = [row for row in (state.get("collector_candidates") or []) if row.get("candidate")]
    guardian_lock = state.get("guardian_lock") or {}
    collector_lock = state.get("collector_lock") or {}
    if len(guardian_candidates) > 1:
        return {"decision": "BLOCK_DUPLICATE_GUARDIAN", "reasons": ["more than one canonical guardian process"]}
    if int(writer.get("authorized_writer_count", 0) or 0) > 1 or writer.get("duplicate_writers") or len(collector_candidates) > 1:
        return {"decision": "BLOCK_DUPLICATE_COLLECTOR", "reasons": ["duplicate authorized collector writer/candidate"]}
    archive = archive_hook or (lambda path, kind, at: _archive_lock(path, kind, at))
    launcher = launch_guardian or (lambda: _launch_canonical_guardian())
    if len(guardian_candidates) == 1:
        guardian_pid = int(guardian_candidates[0].get("pid", 0) or 0)
        if not guardian_lock.get("exists") or not guardian_lock.get("valid") or guardian_lock.get("pid") != guardian_pid:
            return {"decision": "BLOCK_GUARDIAN_LOCK_AMBIGUOUS", "reasons": ["live guardian and guardian lock are inconsistent"]}
        if int(writer.get("authorized_writer_count", 0) or 0) == 1 and collector_lock.get("exists") and writer.get("lock_alive"):
            return {"decision": "NO_ACTION_LIVE", "reasons": [], "guardian_pid": guardian_pid, "collector_pid": writer.get("lock_pid")}
        return {"decision": "BLOCK_COLLECTOR_NOT_LIVE", "reasons": ["guardian is live but exactly one authorized collector writer is not proven"]}
    try:
        guardian_archive = _prove_stale_and_archive(
            guardian_lock,
            kind="guardian",
            candidates=guardian_candidates,
            now=current,
            archive_hook=archive,
            pid_alive=pid_alive,
        )
        collector_count = int(writer.get("authorized_writer_count", 0) or 0)
        if collector_count > 0 or writer.get("duplicate_writers"):
            return {"decision": "BLOCK_DUPLICATE_COLLECTOR", "reasons": ["collector writer remains present while guardian is absent"]}
        collector_archive = _prove_stale_and_archive(
            collector_lock,
            kind="collector",
            candidates=collector_candidates,
            now=current,
            archive_hook=archive,
            pid_alive=pid_alive,
        )
        launched = dict(launcher())
        return {
            "decision": "RELAUNCH_GUARDIAN",
            "reasons": [],
            "guardian_archive": guardian_archive,
            "collector_archive": collector_archive,
            "launcher": launched,
            "collector_launch_attempted": False,
            "child_authorization_created": False,
        }
    except SupervisorBlocked as exc:
        return {"decision": exc.decision, "reasons": [str(exc)]}
    except Exception as exc:
        return {"decision": "BLOCK_SUPERVISOR_ERROR", "reasons": [f"{type(exc).__name__}:{exc}"]}


def _launch_canonical_guardian() -> Mapping[str, Any]:
    if not CANONICAL_GUARDIAN.is_file():
        raise SupervisorBlocked("BLOCK_GUARDIAN_LAUNCHER_MISSING", str(CANONICAL_GUARDIAN))
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(CANONICAL_GUARDIAN.resolve()),
        "-Persistent",
        "-PollSeconds",
        "300",
    ]
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    return {
        "command": command,
        "pid": int(process.pid),
        "guardian_only": True,
        "collector_launch_attempted": False,
        "child_authorization_created": False,
    }


def _receipt_path(now: datetime) -> Path:
    RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)
    return RECEIPT_ROOT / f"R3_V8_EXTERNAL_SUPERVISOR_{now.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid.uuid4().hex}.json"


def _write_receipt(state: Mapping[str, Any] | None, decision: Mapping[str, Any], *, now: datetime, lock_disposition: str) -> dict[str, Any]:
    state = state or {}
    body: dict[str, Any] = {
        "record_type": "R3_V8_EXTERNAL_SUPERVISOR_RECEIPT",
        "schema_version": 1,
        "recorded_at_utc": now.isoformat(),
        "decision": decision.get("decision"),
        "reasons": list(decision.get("reasons") or []),
        "supervisor_lock_path": str(SUPERVISOR_LOCK_PATH),
        "supervisor_lock_disposition": lock_disposition,
        "guardian_lock_path": str(GUARDIAN_LOCK_PATH),
        "collector_lock_path": str(COLLECTOR_LOCK_PATH),
        "guardian_count": len(state.get("guardian_candidates") or []),
        "guardian_pids": [row.get("pid") for row in state.get("guardian_candidates") or []],
        "collector_writer_count": int((state.get("writer") or {}).get("authorized_writer_count", 0) or 0),
        "collector_pid": (state.get("writer") or {}).get("lock_pid"),
        "identity": state.get("identity_summary") or {"ok": False},
        "chain_ok": bool(state.get("chain_ok")),
        "seal_ok": bool(state.get("seal_ok")),
        "policy_error": state.get("policy_error"),
        "disk_state": state.get("disk_state"),
        "launcher": decision.get("launcher"),
        "guardian_archive": decision.get("guardian_archive"),
        "collector_archive": decision.get("collector_archive"),
        "collector_launch_attempted": False,
        "child_authorization_created": False,
        "scientific_data_mutated": False,
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "batch_002": "NOT_STARTED",
        "backfill": False,
        "evidence_mode": "OPERATIONS_ONLY",
    }
    body["body_sha256"] = hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()
    path = _receipt_path(now)
    path.write_text(_canonical(body) + "\n", encoding="utf-8")
    return {"path": str(path), "sha256": _sha256(path), "receipt": body}


def run_once(
    *,
    now: datetime | None = None,
    process_snapshot: Sequence[ProcessRow] | None = None,
    identity_loader: Callable[[], Mapping[str, Any]] | None = None,
    policy_loader: Callable[..., Mapping[str, Any]] | None = None,
    archive_hook: ArchiveHook | None = None,
    launch_guardian: LaunchHook | None = None,
    pid_alive: PidAlive = _pid_is_alive,
) -> dict[str, Any]:
    current = _now(now)
    state: dict[str, Any] | None = None
    try:
        with supervisor_lock():
            state = collect_state(
                now=current,
                process_snapshot=process_snapshot,
                identity_loader=identity_loader,
                policy_loader=policy_loader,
            )
            decision = assess_state(
                state,
                now=current,
                archive_hook=archive_hook,
                launch_guardian=launch_guardian,
                pid_alive=pid_alive,
            )
            receipt = _write_receipt(state, decision, now=current, lock_disposition="ACQUIRED_RELEASED")
    except SupervisorBlocked as exc:
        decision = {"decision": exc.decision, "reasons": [str(exc)]}
        receipt = _write_receipt(state, decision, now=current, lock_disposition="BLOCKED")
    except Exception as exc:
        decision = {"decision": "BLOCK_SUPERVISOR_ERROR", "reasons": [f"{type(exc).__name__}:{exc}"]}
        receipt = _write_receipt(state, decision, now=current, lock_disposition="ERROR")
    return {"decision": decision, "receipt": receipt}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", required=True, help="perform exactly one decision and exit")
    args = parser.parse_args(argv)
    result = run_once()
    print(_canonical(result))
    return 0 if result["decision"]["decision"] in {"NO_ACTION_LIVE", "RELAUNCH_GUARDIAN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
