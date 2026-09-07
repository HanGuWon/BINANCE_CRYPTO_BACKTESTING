"""Fail-closed, outcome-blind crash-recovery guardian for sealed R3 v8.

The guardian is an operations process only.  It reads process/lock and
identity/health/manifest metadata, and it can invoke the already-qualified v8
resume launcher only when an operator supplied a fresh authorization lease.
It never creates a scientific root, backfills a cycle, opens payloads, or
calculates an outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ops.r3 import r3_ops  # noqa: E402
from ops.r3 import r3_v8_authorization  # noqa: E402


V8_ROOT = r3_ops.V8_ROOT
V8_MANIFEST = r3_ops.V8_MANIFEST
V8_SEAL = r3_ops.V8_SEAL
V8_ROSTER = r3_ops.V8_ROSTER
V8_CONTROL_ROOT = r3_ops.V8_CONTROL_ROOT
GUARDIAN_LOCK_PATH = V8_CONTROL_ROOT / "R3_V8_GUARDIAN.lock"
GUARDIAN_RECEIPT_ROOT = r3_ops.OPERATIONS_ROOT / "guardian"
GUARDIAN_STATE_PATH = GUARDIAN_RECEIPT_ROOT / "R3_V8_GUARDIAN_STATE.json"
CANONICAL_LAUNCHER = REPO_ROOT / "ops" / "r3" / "launch_r3_v8_resume.ps1"
DEFAULT_POLL_SECONDS = 300
GUARDIAN_RECORD_TYPE = "R3_V8_GUARDIAN_ATTEMPT"

_CANDIDATE_TOKENS = (
    "run_r3_prospective_collector.py",
    "--mode scientific",
    "--persistent",
    "scientific_raw_v8",
    "2026-09.json",
    "r3_prospective_launch_manifest_2026-09.json",
)

RECEIPT_FIELDS = frozenset(
    {
        "record_type",
        "recorded_at_utc",
        "guardian_pid",
        "guardian_lock_path",
        "guardian_lock_disposition",
        "decision",
        "reasons",
        "identity",
        "control_identity_sha256",
        "writer_before",
        "writer_after",
        "collector_candidate_census",
        "collector_lock_path",
        "preflight",
        "launcher",
        "outcomes_accessed",
        "final_holdout",
        "r2b2",
        "forceorder_v3_migration",
        "receipt_body_sha256",
    }
)


class GuardianError(RuntimeError):
    """A fail-closed guardian error."""


class GuardianLockCollision(GuardianError):
    def __init__(self, *, reason: str, owner: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.owner = owner


@dataclass(frozen=True)
class GuardianConfig:
    root: Path = V8_ROOT
    manifest: Path = V8_MANIFEST
    seal: Path = V8_SEAL
    roster: Path = V8_ROSTER
    launcher: Path = CANONICAL_LAUNCHER
    guardian_lock: Path = GUARDIAN_LOCK_PATH
    receipt_root: Path = GUARDIAN_RECEIPT_ROOT
    authorization: Path | None = None
    preflight_receipt: Path | None = None
    standing_policy: Path | None = None
    state_path: Path | None = None
    receipt_throttle_seconds: int = 900
    poll_seconds: int = DEFAULT_POLL_SECONDS
    # Only in-process synthetic tests may opt into fixture paths. There is no
    # CLI switch for this flag, so production invocations cannot redirect the
    # authority, launcher, or receipt sink.
    allow_test_overrides: bool = False


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def _control_identity_sha256(identity: Mapping[str, Any] | None) -> str | None:
    if not isinstance(identity, Mapping):
        return None
    fields = (
        "root",
        "implementation_commit",
        "source_tree_sha256",
        "registry_sha256",
        "roster_sha256",
        "roster_file_sha256",
        "manifest_sha256",
        "seal_sha256",
    )
    if any(field not in identity for field in fields):
        return None
    payload = {field: identity[field] for field in fields}
    return _sha256_bytes(_canonical_json(payload).encode("utf-8"))


def _read_roster_expiry(path: Path, *, now: datetime) -> dict[str, Any]:
    """Read only the roster's exact effective_end metadata, fail closed."""
    try:
        body = r3_ops._load_json_object(Path(path))
    except Exception as exc:  # pragma: no cover - exercised through caller
        return {"known": False, "expired": True, "reason": f"roster_read:{type(exc).__name__}:{exc}"}
    value = body.get("effective_end")
    if not isinstance(value, str) or not value.strip():
        return {"known": False, "expired": True, "reason": "effective_end_missing"}
    # A naive timestamp is rejected rather than interpreted in local time.
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return {"known": False, "expired": True, "reason": "effective_end_malformed"}
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return {"known": False, "expired": True, "reason": "effective_end_not_timezone_aware"}
    expiry = parsed.astimezone(UTC)
    current = now.astimezone(UTC)
    return {
        "known": True,
        "expired": current >= expiry,
        "field": "effective_end",
        "effective_end_utc": expiry.isoformat(),
    }


def _candidate_reason(row: Mapping[str, Any], *, root: Path, roster: Path, manifest: Path) -> tuple[bool, str]:
    name = Path(str(row.get("executable") or row.get("name") or "")).name.lower()
    command = " ".join(str(row.get("command_line") or "").lower().split())
    if not (name == "python.exe" or (name.startswith("python") and name.endswith(".exe"))):
        return False, "non_python_executable"
    required = (*_CANDIDATE_TOKENS, str(Path(root).resolve()).lower(), str(Path(roster).resolve()).lower(), str(Path(manifest).resolve()).lower())
    missing = [token for token in required if token not in command]
    if missing:
        return False, "missing:" + ",".join(missing)
    return True, "authorized_v8_command_tokens"


def _candidate_census(
    rows: list[dict[str, Any]],
    *,
    root: Path,
    roster: Path,
    manifest: Path,
    writer: Mapping[str, Any],
) -> list[dict[str, Any]]:
    tree_pids = {int(item.get("pid")) for item in writer.get("process_tree", []) if str(item.get("pid", "")).isdigit()}
    census: list[dict[str, Any]] = []
    for row in rows:
        candidate, reason = _candidate_reason(row, root=root, roster=roster, manifest=manifest)
        census.append(
            {
                "pid": int(row.get("pid", 0)),
                "parent_pid": int(row.get("parent_pid", 0)),
                "name": str(row.get("name") or ""),
                "executable": str(row.get("executable") or ""),
                "command_line": str(row.get("command_line") or ""),
                "create_time_utc": row.get("create_time"),
                "candidate": bool(candidate),
                "candidate_reason": reason,
                "in_authorized_collector_tree": int(row.get("pid", 0)) in tree_pids,
            }
        )
    return sorted(census, key=lambda item: item["pid"])


def collect_snapshot(config: GuardianConfig, *, now: datetime | None = None, process_snapshot: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Collect outcome-blind state for one guardian decision."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    rows = process_snapshot if process_snapshot is not None else r3_ops._process_snapshot()
    watchdog = r3_ops.watchdog_snapshot(
        Path(config.root),
        manifest=Path(config.manifest),
        seal=Path(config.seal),
        roster=Path(config.roster),
        now=current,
        require_exact_v8=True,
        process_snapshot=rows,
    )
    writer = watchdog.get("writer") or {}
    lock_path = Path(config.root).resolve() / "control" / "collector.lock"
    identity = watchdog.get("identity")
    expiry = _read_roster_expiry(Path(config.roster), now=current)
    census = _candidate_census(
        rows,
        root=Path(config.root),
        roster=Path(config.roster),
        manifest=Path(config.manifest),
        writer=writer,
    )
    identity_ok = bool(identity) and identity.get("scientific_scope_status") == "clean" and identity.get("outcomes_accessed") is False
    return {
        "recorded_at_utc": current.isoformat(),
        "identity": identity,
        "identity_ok": identity_ok,
        "control_identity_sha256": _control_identity_sha256(identity),
        "writer": writer,
        "collector_candidate_census": census,
        "collector_lock_path": str(lock_path),
        "collector_lock_path_exists": lock_path.is_file(),
        "chain_ok": bool(watchdog.get("manifest_chain_verification")),
        "seal_ok": bool(watchdog.get("launch_seal_verification")),
        "disk_state": (watchdog.get("storage") or {}).get("disk_state"),
        "roster_expiry": expiry,
        "watchdog_state": watchdog.get("state"),
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
    }


def _validate_config(config: GuardianConfig) -> None:
    if config.allow_test_overrides:
        return
    expected = {
        "root": V8_ROOT,
        "manifest": V8_MANIFEST,
        "seal": V8_SEAL,
        "roster": V8_ROSTER,
        "launcher": CANONICAL_LAUNCHER,
        "guardian_lock": GUARDIAN_LOCK_PATH,
        "receipt_root": GUARDIAN_RECEIPT_ROOT,
    }
    if config.standing_policy is not None:
        expected["standing_policy"] = r3_v8_authorization.STANDING_POLICY_PATH
    if config.state_path is not None:
        expected["state_path"] = GUARDIAN_STATE_PATH
    for field, path in expected.items():
        if Path(getattr(config, field)).resolve() != Path(path).resolve():
            raise GuardianError(f"production guardian path override is forbidden: {field}")
    if config.standing_policy is None:
        raise GuardianError("production guardian requires the canonical standing recovery policy")
    if config.authorization is not None:
        raise GuardianError("production guardian does not accept opaque operator authorization; it mints a child lease from the standing policy")


def assess_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return the fail-closed decision before authorization handoff."""
    writer = snapshot.get("writer") or {}
    authorized_count = int(writer.get("authorized_writer_count", 0) or 0)
    duplicates = list(writer.get("duplicate_writers") or [])
    census = [item for item in snapshot.get("collector_candidate_census", []) if item.get("candidate")]
    reasons: list[str] = []

    outside_candidates = [item for item in census if item.get("candidate") and not item.get("in_authorized_collector_tree")]
    if duplicates or authorized_count > 1 or (authorized_count == 1 and outside_candidates):
        return {"decision": "BLOCKED_DUPLICATE_WRITER", "reasons": ["duplicate_writer_or_candidate"]}
    if not snapshot.get("identity_ok"):
        return {"decision": "BLOCKED_IDENTITY", "reasons": ["exact_v8_identity_or_scientific_scope_failed"]}
    if not snapshot.get("chain_ok") or not snapshot.get("seal_ok"):
        return {"decision": "BLOCKED_CHAIN_OR_SEAL", "reasons": ["manifest_chain_or_launch_seal_failed"]}
    expiry = snapshot.get("roster_expiry") or {}
    if not expiry.get("known"):
        return {"decision": "BLOCKED_ROSTER_EXPIRY_UNKNOWN", "reasons": [str(expiry.get("reason") or "effective_end_unknown")]}
    if expiry.get("expired"):
        return {"decision": "BLOCKED_ROSTER_EXPIRED", "reasons": ["effective_end_reached"]}
    if snapshot.get("disk_state") == "RED":
        return {"decision": "BLOCKED_DISK", "reasons": ["disk_state_red"]}

    if authorized_count == 1:
        owner_pid = int(writer.get("lock_pid") or 0)
        owner_candidates = [item for item in census if item.get("candidate") and int(item.get("pid", 0)) == owner_pid]
        if not writer.get("lock_alive") or not snapshot.get("collector_lock_path_exists") or len(owner_candidates) != 1:
            return {"decision": "BLOCKED_STALE_OR_UNKNOWN_LOCK", "reasons": ["writer_lock_and_process_tree_not_consistent"]}
        return {"decision": "NO_ACTION_LIVE", "reasons": []}

    if authorized_count != 0:
        return {"decision": "BLOCKED_DUPLICATE_WRITER", "reasons": ["authorized_writer_count_not_zero_or_one"]}
    if snapshot.get("collector_lock_path_exists") or writer.get("lock_pid") is not None or census:
        return {"decision": "BLOCKED_STALE_OR_UNKNOWN_LOCK", "reasons": ["collector_lock_or_unknown_process_present"]}
    return {"decision": "RESUME_ELIGIBLE", "reasons": reasons}


def _authorization_metadata(path: Path, *, now: datetime) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_absolute() or not path.is_file():
        return None, "authorization_path_missing_or_not_absolute"
    try:
        value = r3_ops._load_json_object(path)
    except Exception as exc:
        return None, f"authorization_invalid:{type(exc).__name__}:{exc}"
    if set(value) not in (r3_ops.RESUME_AUTHORIZATION_FIELDS, r3_ops.CHILD_RESUME_AUTHORIZATION_FIELDS):
        return None, "authorization_schema_drift"
    if value.get("record_type") != r3_ops.RESUME_AUTHORIZATION_RECORD_TYPE:
        return None, "authorization_record_type_invalid"
    if value.get("mode") != "EXISTING_SEALED_V8_ONLY":
        return None, "authorization_mode_invalid"
    if set(value) == r3_ops.CHILD_RESUME_AUTHORIZATION_FIELDS:
        if value.get("authorization_kind") != r3_v8_authorization.CHILD_AUTHORIZATION_KIND:
            return None, "authorization_kind_invalid"
        try:
            r3_v8_authorization._require_sha(value.get("parent_policy_sha256"), "parent_policy_sha256")
        except Exception:
            return None, "parent_policy_sha_invalid"
    if value.get("consumed_at_utc") is not None:
        return None, "authorization_already_consumed"
    try:
        issued = r3_ops._parse_time(value.get("issued_at_utc"))
        expires = r3_ops._parse_time(value.get("expires_at_utc"))
    except Exception as exc:
        return None, f"authorization_time_invalid:{type(exc).__name__}"
    if now.astimezone(UTC) < issued or now.astimezone(UTC) >= expires:
        return None, "authorization_outside_validity_window"
    preflight_value = value.get("preflight_receipt_path")
    if not isinstance(preflight_value, str) or not preflight_value:
        return None, "authorization_preflight_path_missing"
    preflight = Path(preflight_value)
    if not preflight.is_absolute():
        return None, "authorization_preflight_path_not_absolute"
    if not preflight.is_file():
        return None, "authorization_preflight_receipt_missing"
    recorded_preflight_sha = str(value.get("preflight_receipt_sha256") or "")
    if len(recorded_preflight_sha) != 64 or any(char not in "0123456789abcdefABCDEF" for char in recorded_preflight_sha):
        return None, "authorization_preflight_sha_missing_or_invalid"
    try:
        if r3_ops._sha256(preflight).lower() != recorded_preflight_sha.lower():
            return None, "authorization_preflight_receipt_sha_mismatch"
    except OSError:
        return None, "authorization_preflight_receipt_unreadable"
    if value.get("preflight_exit_code") != 0 or not isinstance(value.get("preflight_writer"), dict) or int(value["preflight_writer"].get("authorized_writer_count", -1)) != 0:
        return None, "authorization_preflight_metadata_invalid"
    return {"authorization": value, "preflight_path": preflight}, None


def _default_preflight_runner(config: GuardianConfig, authorization: Path, preflight: Path) -> dict[str, Any]:
    # A new standing-policy attempt passes a not-yet-existing child path and
    # therefore asks the canonical launcher to publish an immutable preflight
    # receipt. Legacy operator leases already carry a receipt and must not be
    # replaced.
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path(config.launcher).resolve()),
        "-PreflightOnly",
    ]
    if not Path(authorization).is_file():
        command += ["-PreflightReceipt", str(Path(preflight).resolve())]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"command": command, "exit_code": int(result.returncode), "output": (result.stdout or result.stderr or "").strip()}


def _default_launcher_runner(config: GuardianConfig, authorization: Path, preflight: Path) -> dict[str, Any]:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path(config.launcher).resolve()),
        "-AuthorizationReceipt",
        str(authorization.resolve()),
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"command": command, "exit_code": int(result.returncode), "output": (result.stdout or result.stderr or "").strip()}


@contextmanager
def _guardian_lock(path: Path) -> Iterator[str]:
    """Acquire a strict no-removal guardian lock."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}:{uuid.uuid4().hex}"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        try:
            owner = path.read_text(encoding="utf-8").strip()
        except OSError:
            owner = None
        reason = "GUARDIAN_LOCK_COLLISION"
        if not owner or ":" not in owner:
            reason = "GUARDIAN_LOCK_STALE_OR_MALFORMED"
        else:
            try:
                owner_pid = int(owner.split(":", 1)[0])
            except ValueError:
                owner_pid = -1
            if owner_pid <= 0 or not _pid_is_alive(owner_pid):
                reason = "GUARDIAN_LOCK_STALE_OR_MALFORMED"
        raise GuardianLockCollision(reason=reason, owner=owner) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(token)
            handle.flush()
            os.fsync(handle.fileno())
        yield token
    finally:
        try:
            if path.read_text(encoding="utf-8").strip() == token:
                path.unlink(missing_ok=True)
        except OSError:
            # A lost/unreadable lock is not replaced or repaired by cleanup.
            pass


def _receipt_path(root: Path, *, now: datetime) -> Path:
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return Path(root) / f"R3_V8_GUARDIAN_ATTEMPT_{stamp}_{uuid.uuid4().hex}.json"


def _state_path(config: GuardianConfig) -> Path:
    return Path(config.state_path or (Path(config.receipt_root) / "R3_V8_GUARDIAN_STATE.json")).resolve()


def _new_preflight_path(config: GuardianConfig, *, now: datetime) -> Path:
    root = Path(config.receipt_root) / "preflight"
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return (root / f"R3_V8_GUARDIAN_PREFLIGHT_{stamp}_{uuid.uuid4().hex}.json").resolve()


def _pending_child_path(config: GuardianConfig, *, now: datetime) -> Path:
    root = Path(config.receipt_root) / "child_authorizations"
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return (root / f".pending_{stamp}_{uuid.uuid4().hex}.json").resolve()


def _auth_identity(identity: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize watchdog identity names to the authorization contract."""
    value = dict(identity or {})
    value.setdefault("launch_manifest_sha256", value.get("manifest_sha256"))
    value.setdefault("launch_seal_sha256", value.get("seal_sha256"))
    return value


def _receipt_state_key(receipt: Mapping[str, Any]) -> str:
    writer = receipt.get("writer_before") or {}
    stable = {
        "decision": receipt.get("decision"),
        "reasons": receipt.get("reasons"),
        "control_identity_sha256": receipt.get("control_identity_sha256"),
        "authorized_writer_count": writer.get("authorized_writer_count"),
        "lock_pid": writer.get("lock_pid"),
        "guardian_lock_disposition": receipt.get("guardian_lock_disposition"),
    }
    return _sha256_bytes(_canonical_json(stable).encode("utf-8"))


def _publish_receipt(config: GuardianConfig, receipt: Mapping[str, Any], *, now: datetime, throttle: bool) -> dict[str, Any]:
    """Write transition receipts and suppress unchanged persistent heartbeats."""
    destination = _receipt_path(config.receipt_root, now=now)
    state_path = _state_path(config)
    state: dict[str, Any] = {}
    try:
        if state_path.is_file():
            loaded = r3_ops._load_json_object(state_path)
            if isinstance(loaded, dict):
                state = loaded
    except Exception:
        # A malformed state file never authorizes a resume; discard only the
        # in-memory hint and emit a fresh immutable diagnostic receipt.
        state = {}
    state_key = _receipt_state_key(receipt)
    emitted_at = None
    if state.get("last_emitted_at_utc"):
        try:
            emitted_at = r3_ops._parse_time(state["last_emitted_at_utc"])
        except Exception:
            emitted_at = None
    unchanged = state.get("last_state_key") == state_key
    if throttle and unchanged and emitted_at is not None:
        age = (now.astimezone(UTC) - emitted_at).total_seconds()
        if age < max(1, int(config.receipt_throttle_seconds)):
            state.update({
                "schema_version": 1,
                "last_seen_at_utc": now.astimezone(UTC).isoformat(),
                "poll_count": int(state.get("poll_count", 0) or 0) + 1,
            })
            try:
                r3_ops._write_json_replace(state_path, state)
            except Exception:
                pass
            return {"receipt_path": str(state.get("last_receipt_path") or ""), "receipt": dict(receipt), "emitted": False, "state_key": state_key}
    result = _write_receipt(receipt, destination=destination)
    state = {
        "schema_version": 1,
        "last_state_key": state_key,
        "last_decision": receipt.get("decision"),
        "last_emitted_at_utc": now.astimezone(UTC).isoformat(),
        "last_seen_at_utc": now.astimezone(UTC).isoformat(),
        "last_receipt_path": result["receipt_path"],
        "emission_count": int(state.get("emission_count", 0) or 0) + 1,
        "poll_count": int(state.get("poll_count", 0) or 0) + 1,
    }
    try:
        r3_ops._write_json_replace(state_path, state)
    except Exception:
        # The immutable receipt remains valid even if a best-effort state
        # update cannot be persisted; no second sink is attempted.
        pass
    result["emitted"] = True
    result["state_key"] = state_key
    return result


def _write_receipt(payload: Mapping[str, Any], *, destination: Path) -> dict[str, Any]:
    body = dict(payload)
    body.pop("receipt_body_sha256", None)
    unknown = set(body) - (RECEIPT_FIELDS - {"receipt_body_sha256"})
    if unknown:
        raise GuardianError(f"guardian receipt schema drift: {sorted(unknown)}")
    body["receipt_body_sha256"] = _sha256_bytes(_canonical_json(body).encode("utf-8"))
    r3_ops._write_json_exclusive(Path(destination), body)
    return {"receipt_path": str(Path(destination).resolve()), "receipt": body}


def _base_receipt(config: GuardianConfig, *, now: datetime, decision: str, reasons: list[str], snapshot: Mapping[str, Any] | None, lock_disposition: str, preflight: Mapping[str, Any] | None = None, launcher: Mapping[str, Any] | None = None, writer_after: Mapping[str, Any] | None = None) -> dict[str, Any]:
    snapshot = snapshot or {}
    return {
        "record_type": GUARDIAN_RECORD_TYPE,
        "recorded_at_utc": now.astimezone(UTC).isoformat(),
        "guardian_pid": os.getpid(),
        "guardian_lock_path": str(Path(config.guardian_lock).resolve()),
        "guardian_lock_disposition": lock_disposition,
        "decision": decision,
        "reasons": list(reasons),
        "identity": snapshot.get("identity"),
        "control_identity_sha256": snapshot.get("control_identity_sha256"),
        "writer_before": snapshot.get("writer"),
        "writer_after": writer_after,
        "collector_candidate_census": snapshot.get("collector_candidate_census", []),
        "collector_lock_path": snapshot.get("collector_lock_path", str(Path(config.root).resolve() / "control" / "collector.lock")),
        "preflight": preflight,
        "launcher": launcher,
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
    }


SnapshotProvider = Callable[[GuardianConfig, datetime], Mapping[str, Any]]
Runner = Callable[[GuardianConfig, Path, Path], Mapping[str, Any]]


def _run_once_unlocked(
    config: GuardianConfig,
    *,
    now: datetime,
    snapshot_provider: SnapshotProvider,
    preflight_runner: Runner,
    launcher_runner: Runner,
    throttle: bool = False,
) -> dict[str, Any]:
    before = dict(snapshot_provider(config, now))
    assessed = assess_snapshot(before)
    decision = str(assessed["decision"])
    preflight: Mapping[str, Any] | None = None
    launcher: Mapping[str, Any] | None = None
    after_writer: Mapping[str, Any] | None = None
    if decision == "RESUME_ELIGIBLE":
        # Production operation is standing-policy driven.  The explicit
        # authorization branch remains for immutable legacy/operator leases and
        # for backwards-compatible synthetic tests.
        if config.authorization is None and config.standing_policy is None:
            decision = "AUTHORIZATION_REQUIRED"
            assessed = {"reasons": ["no_standing_policy_or_explicit_authorization"]}
        elif config.authorization is None:
            try:
                policy_binding = r3_v8_authorization.load_standing_policy(Path(config.standing_policy), now=now)
                authorization_path = _pending_child_path(config, now=now)
                preflight_path = Path(config.preflight_receipt or _new_preflight_path(config, now=now)).resolve()
                if config.preflight_receipt is not None and not Path(config.preflight_receipt).is_absolute():
                    raise r3_v8_authorization.AuthorizationError("preflight_path_override_not_absolute")
                preflight = dict(preflight_runner(config, authorization_path, preflight_path))
                if int(preflight.get("exit_code", 1)) != 0:
                    decision = "BLOCKED_PREFLIGHT"
                    assessed = {"reasons": ["canonical_preflight_failed"]}
                elif not preflight_path.is_file():
                    decision = "BLOCKED_PREFLIGHT"
                    assessed = {"reasons": ["immutable_preflight_receipt_missing"]}
                else:
                    after = dict(snapshot_provider(config, datetime.now(UTC).astimezone(UTC)))
                    after_assessed = assess_snapshot(after)
                    after_writer = after.get("writer")
                    if after_assessed["decision"] != "RESUME_ELIGIBLE":
                        decision = "BLOCKED_RACE_CHANGED"
                        assessed = {"reasons": ["writer_lock_or_identity_changed_after_preflight"]}
                    else:
                        child = r3_v8_authorization.mint_child_authorization(
                            policy_binding,
                            identity=_auth_identity(after.get("identity")),
                            preflight_path=preflight_path,
                            now=now,
                            destination_root=Path(config.receipt_root) / "child_authorizations",
                        )
                        authorization_path = Path(child["path"]).resolve()
                        r3_v8_authorization.verify_child_metadata(
                            authorization_path,
                            policy_binding=policy_binding,
                            identity=_auth_identity(after.get("identity")),
                            now=now,
                        )
                        preflight = {**preflight, "standing_policy_sha256": policy_binding["policy_sha256"], "child_authorization": child}
                        launcher = dict(launcher_runner(config, authorization_path, preflight_path))
                        if int(launcher.get("exit_code", 1)) != 0:
                            decision = "BLOCKED_LAUNCH_FAILURE"
                            assessed = {"reasons": ["canonical_authorized_launcher_failed"]}
                        else:
                            decision = "RESUME_STARTED"
                            assessed = {"reasons": []}
            except r3_v8_authorization.AuthorizationError as exc:
                decision = "BLOCKED_AUTHORIZATION_POLICY"
                assessed = {"reasons": [str(exc)]}
            except Exception as exc:
                decision = "BLOCKED_AUTHORIZATION_HANDOFF"
                assessed = {"reasons": [f"child_authorization_error:{type(exc).__name__}:{exc}"]}
        else:
            authorization_path = Path(config.authorization)
            if not authorization_path.is_absolute():
                auth_meta, auth_error = None, "authorization_path_not_absolute"
            else:
                auth_meta, auth_error = _authorization_metadata(authorization_path, now=now)
            if auth_meta is None:
                decision = "AUTHORIZATION_REQUIRED"
                assessed = {"reasons": [auth_error or "authorization_invalid"]}
            else:
                auth_value = auth_meta["authorization"]
                expected_identity = before.get("identity") or {}
                auth_identity_pairs = {
                    "root": "root",
                    "implementation_commit": "implementation_commit",
                    "source_tree_sha256": "source_tree_sha256",
                    "registry_sha256": "registry_sha256",
                    "roster_sha256": "roster_sha256",
                    "launch_manifest_sha256": "manifest_sha256",
                    "launch_seal_sha256": "seal_sha256",
                }
                if any(str(auth_value.get(auth_field)) != str(expected_identity.get(identity_field)) for auth_field, identity_field in auth_identity_pairs.items()):
                    decision = "BLOCKED_AUTHORIZATION_HANDOFF"
                    assessed = {"reasons": ["authorization_identity_does_not_match_snapshot"]}
                else:
                    if config.preflight_receipt is not None and not Path(config.preflight_receipt).is_absolute():
                        decision = "BLOCKED_AUTHORIZATION_HANDOFF"
                        assessed = {"reasons": ["preflight_path_override_not_absolute"]}
                        preflight_path = auth_meta["preflight_path"].resolve()
                    else:
                        preflight_path = Path(config.preflight_receipt or auth_meta["preflight_path"]).resolve()
                    if decision == "BLOCKED_AUTHORIZATION_HANDOFF":
                        pass
                    elif preflight_path != auth_meta["preflight_path"].resolve():
                        decision = "BLOCKED_AUTHORIZATION_HANDOFF"
                        assessed = {"reasons": ["preflight_path_override_mismatch"]}
                    else:
                        preflight = dict(preflight_runner(config, Path(config.authorization).resolve(), preflight_path))
                        if int(preflight.get("exit_code", 1)) != 0:
                            decision = "BLOCKED_PREFLIGHT"
                            assessed = {"reasons": ["canonical_preflight_failed"]}
                        else:
                            after = dict(snapshot_provider(config, datetime.now(UTC).astimezone(UTC)))
                            after_assessed = assess_snapshot(after)
                            after_writer = after.get("writer")
                            if after_assessed["decision"] != "RESUME_ELIGIBLE":
                                decision = "BLOCKED_RACE_CHANGED"
                                assessed = {"reasons": ["writer_lock_or_identity_changed_after_preflight"]}
                            else:
                                launcher = dict(launcher_runner(config, Path(config.authorization).resolve(), preflight_path))
                                if int(launcher.get("exit_code", 1)) != 0:
                                    decision = "BLOCKED_LAUNCH_FAILURE"
                                    assessed = {"reasons": ["canonical_authorized_launcher_failed"]}
                                else:
                                    decision = "RESUME_STARTED"
                                    assessed = {"reasons": []}
    receipt = _base_receipt(
        config,
        now=now,
        decision=decision,
        reasons=list(assessed.get("reasons") or []),
        snapshot=before,
        lock_disposition="ACQUIRED_RELEASED",
        preflight=preflight,
        launcher=launcher,
        writer_after=after_writer,
    )
    return _publish_receipt(config, receipt, now=now, throttle=throttle)


def run_once(
    config: GuardianConfig,
    *,
    now: datetime | None = None,
    snapshot_provider: SnapshotProvider | None = None,
    preflight_runner: Runner | None = None,
    launcher_runner: Runner | None = None,
) -> dict[str, Any]:
    _validate_config(config)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    provider = snapshot_provider or (lambda cfg, at: collect_snapshot(cfg, now=at))
    preflight = preflight_runner or _default_preflight_runner
    launcher = launcher_runner or _default_launcher_runner
    try:
        with _guardian_lock(config.guardian_lock):
            return _run_once_unlocked(config, now=current, snapshot_provider=provider, preflight_runner=preflight, launcher_runner=launcher)
    except GuardianLockCollision as exc:
        receipt = _base_receipt(
            config,
            now=current,
            decision="BLOCKED_GUARDIAN_LOCK_COLLISION",
            reasons=[exc.reason],
            snapshot=None,
            lock_disposition="COLLISION",
        )
        return _write_receipt(receipt, destination=_receipt_path(config.receipt_root, now=current))
    except Exception as exc:
        receipt = _base_receipt(
            config,
            now=current,
            decision="BLOCKED_GUARDIAN_ERROR",
            reasons=[f"{type(exc).__name__}:{exc}"],
            snapshot=None,
            lock_disposition="ERROR",
        )
        return _write_receipt(receipt, destination=_receipt_path(config.receipt_root, now=current))


def run_persistent(config: GuardianConfig, *, snapshot_provider: SnapshotProvider | None = None, preflight_runner: Runner | None = None, launcher_runner: Runner | None = None, sleep_fn: Callable[[float], None] = time.sleep) -> int:
    """Serialize polls under one guardian lock for the process lifetime."""
    _validate_config(config)
    current = datetime.now(UTC).astimezone(UTC)
    provider = snapshot_provider or (lambda cfg, at: collect_snapshot(cfg, now=at))
    preflight = preflight_runner or _default_preflight_runner
    launcher = launcher_runner or _default_launcher_runner
    try:
        with _guardian_lock(config.guardian_lock):
            while True:
                poll_now = datetime.now(UTC).astimezone(UTC)
                try:
                    _run_once_unlocked(config, now=poll_now, snapshot_provider=provider, preflight_runner=preflight, launcher_runner=launcher, throttle=True)
                except Exception as exc:
                    # A malformed receipt/evidence or subprocess failure must
                    # be visible but must not kill the only recovery authority.
                    try:
                        error_receipt = _base_receipt(
                            config,
                            now=poll_now,
                            decision="BLOCKED_GUARDIAN_ERROR",
                            reasons=[f"{type(exc).__name__}:{exc}"],
                            snapshot=None,
                            lock_disposition="ACQUIRED_RELEASED",
                        )
                        _publish_receipt(config, error_receipt, now=poll_now, throttle=True)
                    except Exception:
                        # Do not attempt a second sink or mutate evidence.
                        pass
                sleep_fn(max(1, int(config.poll_seconds)))
    except KeyboardInterrupt:
        return 0
    except GuardianLockCollision as exc:
        # A persistent duplicate cannot safely write through the existing
        # owner's lock, so one immutable collision receipt is sufficient.
        try:
            receipt = _base_receipt(config, now=current, decision="BLOCKED_GUARDIAN_LOCK_COLLISION", reasons=[exc.reason], snapshot=None, lock_disposition="COLLISION")
            _write_receipt(receipt, destination=_receipt_path(config.receipt_root, now=current))
        except Exception:
            pass
        return 73


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--persistent", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--preflight-receipt", type=Path)
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = GuardianConfig(
        authorization=args.authorization,
        preflight_receipt=args.preflight_receipt,
        poll_seconds=args.poll_seconds,
        standing_policy=r3_v8_authorization.STANDING_POLICY_PATH,
        state_path=GUARDIAN_STATE_PATH,
    )
    if args.once:
        result = run_once(config)
        print(_canonical_json(result))
        decision = result["receipt"]["decision"]
        if decision in {"NO_ACTION_LIVE", "RESUME_STARTED"}:
            return 0
        if decision == "AUTHORIZATION_REQUIRED":
            return 74
        return 1
    return run_persistent(config)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
