"""Outcome-blind operational controls for the already sealed R3 v8 collector.

This module deliberately reads only launch identity, process metadata, cycle
metadata, health receipts, manifest-chain metadata, gap counters, and disk
capacity.  It never opens market payload streams and has no outcome/return
fields in its receipt schema.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (REPO_ROOT / "src", REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from binance_research.r3_operations import (  # noqa: E402
    CollectorLockError,
    single_instance_lock,
    verify_launch_identity,
    verify_launch_seal,
    verify_manifest_chain,
)
from scripts.prepare_r3_post_boundary_launch import _source_tree_sha256  # noqa: E402


BASE_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1")
V8_ROOT = BASE_ROOT / "scientific_raw_v8"
V8_CONTROL_ROOT = BASE_ROOT / "launch_control" / "2026-09-production-v8"
V8_MANIFEST = V8_CONTROL_ROOT / "R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json"
V8_SEAL = V8_CONTROL_ROOT / "R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json"
V8_ROSTER = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "rosters" / "2026-09.json"
V8_REGISTRY = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "trial_registry.csv"
OPERATIONS_ROOT = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations"
DAILY_RECEIPT_PATH = OPERATIONS_ROOT / "R3_V8_DAILY_OPERATIONS_RECEIPTS.jsonl"
DAILY_LOCK_PATH = OPERATIONS_ROOT / "R3_V8_DAILY_OPERATIONS_RECEIPTS.lock"
COLLECTOR_SCRIPT = REPO_ROOT / "scripts" / "run_r3_prospective_collector.py"
PYTHON_EXE = Path(r"C:\Users\user\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe")

EXPECTED_IMPLEMENTATION = "ecebc49dff41eeec33af62c2c85a75c5a0bd2922"
EXPECTED_SOURCE_TREE = "b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688"
EXPECTED_REGISTRY = "c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a"
EXPECTED_MANIFEST_SHA = "cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659"
EXPECTED_SEAL_SHA = "ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85"
EXPECTED_ROSTER = "bb05514dfc78cfca3b736488b1454f4cb022da0110e2cbf69f53c505f543ea79"
EXPECTED_ROSTER_FILE = "102e1b2eb89977083142662bb8ccc1a2aad8e548095721901a42ae1de72f5d17"

INTERVAL_SECONDS = 15 * 60
GRACE_SECONDS = 120
FORBIDDEN_FIELDS = frozenset(
    {
        "gross_return",
        "net_return",
        "return",
        "returns",
        "pnl",
        "sharpe",
        "sortino",
        "hit_rate",
        "win_rate",
        "future_return",
        "outcome",
    }
)
CYCLE_PAYLOAD_FIELDS = frozenset(
    {
        "cycle_id",
        "target_bar_open",
        "target_bar_close",
        "scheduled_collection_time",
        "actual_collection_start",
        "cycle_completed_at",
        "clock_calibration_id",
        "eligible_next_execution_time",
    }
)
HEALTH_FIELDS = frozenset(
    {
        "timestamp",
        "pid",
        "campaign_id",
        "manifest_sha256",
        "roster_sha256",
        "raw_root",
        "stream_state",
        "restart_count",
        "gap_count",
        "bytes",
        "evidence_mode",
    }
)
RECEIPT_FIELDS = frozenset(
    {
        "date",
        "record_type",
        "implementation_commit",
        "source_tree_sha256",
        "registry_sha256",
        "roster_sha256",
        "launch_manifest_sha256",
        "launch_seal_sha256",
        "first_cycle",
        "last_cycle",
        "expected_cycle_count",
        "observed_cycle_count",
        "missing_cycle_count",
        "gap_categories",
        "reconnect_count",
        "manifest_chain_verification",
        "launch_seal_verification",
        "current_process_identity",
        "raw_byte_growth",
        "free_disk_bytes",
        "watchdog_state",
        "outcomes_accessed",
    }
)


class OperationsAuditError(RuntimeError):
    """A fail-closed operational identity or evidence error."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise OperationsAuditError(f"invalid UTC timestamp: {value!r}")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise OperationsAuditError(f"invalid UTC timestamp: {value!r}") from exc


def _reject_forbidden(value: Any, *, context: str) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_FIELDS.intersection(value)
        if forbidden:
            raise OperationsAuditError(f"forbidden outcome field in {context}: {sorted(forbidden)}")
        for key, child in value.items():
            _reject_forbidden(child, context=f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden(child, context=f"{context}[{index}]")


def _json_lines(path: Path) -> Iterator[dict[str, Any]]:
    if not Path(path).is_file():
        raise OperationsAuditError(f"missing operational evidence: {path}")
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OperationsAuditError(f"invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise OperationsAuditError(f"non-object JSONL at {path}:{line_number}")
        _reject_forbidden(value, context=f"{path}:{line_number}")
        yield value


def _manifest_and_seal_paths(root: Path, manifest: Path | None, seal: Path | None) -> tuple[Path, Path]:
    root = Path(root).resolve()
    manifest_path = Path(manifest or V8_MANIFEST).resolve()
    seal_path = Path(seal or manifest_path.with_name("R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json")).resolve()
    if not root.is_dir() or not (root / "raw_v1").is_dir():
        raise OperationsAuditError(f"scientific root/raw_v1 is missing: {root}")
    return manifest_path, seal_path


def verify_identity(
    root: Path = V8_ROOT,
    *,
    manifest: Path | None = None,
    seal: Path | None = None,
    roster: Path = V8_ROSTER,
    require_exact_v8: bool = False,
) -> dict[str, Any]:
    """Verify the sealed v8 identity without touching payload streams."""
    root = Path(root).resolve()
    if require_exact_v8 and root != V8_ROOT.resolve():
        raise OperationsAuditError(f"only the sealed v8 root is authorized: {root}")
    manifest_path, seal_path = _manifest_and_seal_paths(root, manifest, seal)
    roster_path = Path(roster).resolve()
    if not roster_path.is_file():
        raise OperationsAuditError(f"roster artifact is missing: {roster_path}")
    manifest_body = json.loads(manifest_path.read_text(encoding="utf-8"))
    roster_body = json.loads(roster_path.read_text(encoding="utf-8"))
    roster_sha = str(roster_body.get("roster_sha256", ""))
    if roster_sha != manifest_body.get("roster_sha256"):
        raise OperationsAuditError("roster logical SHA does not match launch manifest")
    roster_file_sha = _sha256(roster_path)
    if roster_file_sha != manifest_body.get("roster_file_sha256"):
        raise OperationsAuditError("roster file SHA does not match launch manifest")
    verified = verify_launch_identity(manifest_path, roster_sha256=roster_sha, implementation_commit=EXPECTED_IMPLEMENTATION)
    if Path(str(verified.get("scientific_root", ""))).resolve() != root:
        raise OperationsAuditError("launch manifest scientific root mismatch")
    sealed = verify_launch_seal(seal_path, manifest_path, roster_sha256=roster_sha, scientific_root=root)
    source_sha = _source_tree_sha256()
    if source_sha != verified.get("source_tree_sha256") or source_sha != EXPECTED_SOURCE_TREE:
        raise OperationsAuditError("scientific source-tree SHA mismatch")
    registry_sha = _sha256(V8_REGISTRY)
    if registry_sha != verified.get("registry_sha256") or registry_sha != EXPECTED_REGISTRY:
        raise OperationsAuditError("frozen registry SHA mismatch")
    manifest_sha = _sha256(manifest_path)
    seal_sha = _sha256(seal_path)
    if manifest_sha != EXPECTED_MANIFEST_SHA:
        raise OperationsAuditError("v8 launch manifest SHA mismatch")
    if seal_sha != EXPECTED_SEAL_SHA:
        raise OperationsAuditError("v8 launch seal SHA mismatch")
    chain = root / "raw_v1" / "manifest_chain.jsonl"
    chain_pass = chain.is_file() and verify_manifest_chain(chain)
    if not chain_pass:
        raise OperationsAuditError("v8 manifest chain is invalid")
    scoped = subprocess.run(
        ["git", "status", "--short", "--", "scripts", "src", "tests", "configs"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if scoped:
        raise OperationsAuditError(f"scientific source scope is dirty: {scoped}")
    return {
        "root": str(root),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "seal_path": str(seal_path),
        "seal_sha256": seal_sha,
        "seal_status": sealed["seal"]["status"],
        "implementation_commit": verified["implementation_commit"],
        "source_tree_sha256": source_sha,
        "registry_sha256": registry_sha,
        "roster_sha256": roster_sha,
        "roster_file_sha256": roster_file_sha,
        "manifest_chain_verification": True,
        "scientific_scope_status": "clean",
        "outcomes_accessed": False,
    }


def _cycle_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    paths = sorted((Path(root) / "raw_v1").rglob("cycle_metadata.jsonl"))
    if not paths:
        raise OperationsAuditError("cycle metadata stream is missing")
    for path in paths:
        for envelope in _json_lines(path):
            if envelope.get("stream") != "cycle_metadata":
                raise OperationsAuditError(f"unexpected stream in cycle metadata file: {path}")
            if envelope.get("evidence_mode") != "SCIENTIFIC":
                raise OperationsAuditError("non-SCIENTIFIC cycle metadata in v8 root")
            payload = envelope.get("payload")
            if not isinstance(payload, dict) or set(payload) - CYCLE_PAYLOAD_FIELDS:
                raise OperationsAuditError("cycle metadata payload is not the frozen operational schema")
            required = CYCLE_PAYLOAD_FIELDS - {"clock_calibration_id"}
            if not required.issubset(payload):
                raise OperationsAuditError("cycle metadata lacks required timing fields")
            records.append(
                {
                    "cycle_id": str(payload["cycle_id"]),
                    "target_bar_open": str(payload["target_bar_open"]),
                    "target_bar_close": str(payload["target_bar_close"]),
                    "scheduled_collection_time": str(payload["scheduled_collection_time"]),
                    "actual_collection_start": str(payload["actual_collection_start"]),
                    "cycle_completed_at": str(payload["cycle_completed_at"]),
                    "eligible_next_execution_time": str(payload["eligible_next_execution_time"]),
                    "clock_calibration_id": str(payload.get("clock_calibration_id", "")),
                }
            )
    records.sort(key=lambda item: _parse_time(item["cycle_completed_at"]))
    if len({item["cycle_id"] for item in records}) != len(records):
        raise OperationsAuditError("duplicate cycle IDs detected")
    return records


def _health_records(root: Path) -> list[dict[str, Any]]:
    path = Path(root) / "health" / "health_receipts.jsonl"
    records: list[dict[str, Any]] = []
    for value in _json_lines(path):
        unknown = set(value) - HEALTH_FIELDS
        if unknown:
            raise OperationsAuditError(f"unknown health fields: {sorted(unknown)}")
        if value.get("evidence_mode") != "SCIENTIFIC":
            raise OperationsAuditError("non-SCIENTIFIC health receipt in v8 root")
        records.append(
            {
                "timestamp": str(value.get("timestamp")),
                "manifest_sha256": value.get("manifest_sha256"),
                "roster_sha256": value.get("roster_sha256"),
                "gap_count": int(value.get("gap_count", 0)),
                "restart_count": int(value.get("restart_count", 0)),
                "bytes": int(value.get("bytes", 0)),
                "pid": int(value.get("pid", 0)),
                "stream_status": (value.get("stream_state") or {}).get("status"),
                "evidence_mode": value.get("evidence_mode"),
            }
        )
    if not records:
        raise OperationsAuditError("health receipt stream is empty")
    records.sort(key=lambda item: _parse_time(item["timestamp"]))
    return records


def _chain_records(root: Path) -> list[dict[str, Any]]:
    path = Path(root) / "raw_v1" / "manifest_chain.jsonl"
    if not path.is_file() or not verify_manifest_chain(path):
        raise OperationsAuditError("manifest chain missing or invalid")
    records: list[dict[str, Any]] = []
    for value in _json_lines(path):
        records.append(
            {
                "manifest_sha256": str(value.get("manifest_sha256")),
                "created_at": str(value.get("created_at")),
                "total_bytes": int(value.get("total_bytes", 0)),
                "total_rows": int(value.get("total_rows", 0)),
                "file_count": len(value.get("files", [])),
            }
        )
    if not records:
        raise OperationsAuditError("manifest chain is empty")
    return records


def _process_snapshot() -> list[dict[str, Any]]:
    try:
        import psutil
    except ImportError as exc:  # pragma: no cover - Windows runtime includes psutil
        raise OperationsAuditError("psutil is required for the writer audit") from exc
    snapshot: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "ppid", "name", "exe", "cmdline", "create_time"]):
        try:
            info = process.info
            snapshot.append(
                {
                    "pid": int(info.get("pid")),
                    "parent_pid": int(info.get("ppid") or 0),
                    "name": str(info.get("name") or ""),
                    "executable": str(info.get("exe") or ""),
                    "command_line": " ".join(info.get("cmdline") or []),
                    "create_time": datetime.fromtimestamp(float(info.get("create_time")), tz=UTC).isoformat() if info.get("create_time") else None,
                }
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, TypeError, ValueError):
            continue
    return snapshot


def audit_writer(root: Path, *, snapshot: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    lock_path = root / "control" / "collector.lock"
    if not lock_path.is_file():
        return {"lock_pid": None, "lock_alive": False, "authorized_writer_count": 0, "duplicate_writers": [], "process_tree": []}
    try:
        lock_pid = int(lock_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise OperationsAuditError("collector lock is malformed") from exc
    rows = snapshot if snapshot is not None else _process_snapshot()
    by_pid = {int(row["pid"]): row for row in rows}
    if lock_pid not in by_pid:
        return {"lock_pid": lock_pid, "lock_alive": False, "authorized_writer_count": 0, "duplicate_writers": [], "process_tree": []}
    seen: set[int] = set()
    stack = [lock_pid]
    children: dict[int, list[int]] = {}
    for row in rows:
        children.setdefault(int(row["parent_pid"]), []).append(int(row["pid"]))
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        row = by_pid.get(pid)
        if row is None:
            continue
        parent = int(row["parent_pid"])
        if parent in by_pid:
            stack.append(parent)
        stack.extend(children.get(pid, []))
    required = ("run_r3_prospective_collector.py", "--mode scientific", "--persistent", "scientific_raw_v8", "2026-09.json", "r3_prospective_launch_manifest_2026-09.json")
    def authorized(row: dict[str, Any]) -> bool:
        name = Path(row.get("executable", "") or row.get("name", "")).name.lower()
        if not (name == "python.exe" or (name.startswith("python") and name.endswith(".exe"))):
            return False
        command = " ".join(str(row.get("command_line", "")).lower().split())
        return all(token in command for token in required)
    matching = [row for row in rows if authorized(row)]
    outside = [row for row in matching if int(row["pid"]) not in seen]
    owner = by_pid.get(lock_pid)
    owner_authorized = bool(owner and authorized(owner))
    tree = []
    for row in rows:
        if int(row["pid"]) not in seen:
            continue
        role = "lock owner / authorized writer" if int(row["pid"]) == lock_pid else "authorized wrapper/descendant"
        tree.append({**row, "role": role})
    return {
        "lock_pid": lock_pid,
        "lock_alive": True,
        "authorized_writer_count": int(owner_authorized),
        "duplicate_writers": outside,
        "process_tree": sorted(tree, key=lambda row: int(row["pid"])),
    }


def _inclusive_p95(values: Iterable[int]) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    rank = (len(ordered) - 1) * 0.95
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def storage_metrics(root: Path, chain: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    manifests = chain or _chain_records(root)
    deltas = [max(0, manifests[index]["total_bytes"] - manifests[index - 1]["total_bytes"]) for index in range(1, len(manifests))]
    positive = [value for value in deltas if value > 0]
    median = float(statistics.median(positive)) if positive else None
    p95 = _inclusive_p95(positive)
    maximum = max(positive) if positive else None
    bytes_per_hour = median * 4.0 if median is not None else None
    bytes_per_day = median * 96.0 if median is not None else None
    free = int(shutil.disk_usage(Path(root)).free)
    projected_days = free / bytes_per_day if bytes_per_day and bytes_per_day > 0 else None
    if projected_days is None:
        disk_state = "YELLOW"
    elif projected_days >= 30:
        disk_state = "GREEN"
    elif projected_days >= 7:
        disk_state = "YELLOW"
    else:
        disk_state = "RED"
    return {
        "manifest_observation_count": len(positive),
        "bytes_deltas": positive,
        "bytes_cycle_median": median,
        "bytes_cycle_p95_inclusive": p95,
        "bytes_cycle_max": maximum,
        "observed_bytes_per_hour": bytes_per_hour,
        "projected_bytes_per_day": bytes_per_day,
        "projected_bytes_7d": bytes_per_day * 7 if bytes_per_day is not None else None,
        "projected_bytes_30d": bytes_per_day * 30 if bytes_per_day is not None else None,
        "free_disk_bytes": free,
        "projected_days_to_zero": projected_days,
        "disk_state": disk_state,
    }


def watchdog_snapshot(
    root: Path = V8_ROOT,
    *,
    manifest: Path | None = None,
    seal: Path | None = None,
    roster: Path = V8_ROSTER,
    now: datetime | None = None,
    require_exact_v8: bool = False,
    process_snapshot: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a GREEN/YELLOW/RED operational status with no outcome fields."""
    reasons: list[str] = []
    identity: dict[str, Any] | None = None
    try:
        identity = verify_identity(root, manifest=manifest, seal=seal, roster=roster, require_exact_v8=require_exact_v8)
    except Exception as exc:  # fail closed into RED, preserving the reason
        reasons.append(f"identity:{type(exc).__name__}:{exc}")
    cycles: list[dict[str, Any]] = []
    health: list[dict[str, Any]] = []
    chain: list[dict[str, Any]] = []
    try:
        cycles = _cycle_records(root)
        health = _health_records(root)
        chain = _chain_records(root)
    except Exception as exc:
        reasons.append(f"evidence:{type(exc).__name__}:{exc}")
    writer: dict[str, Any]
    try:
        writer = audit_writer(root, snapshot=process_snapshot)
    except Exception as exc:
        writer = {"lock_pid": None, "lock_alive": False, "authorized_writer_count": 0, "duplicate_writers": [], "process_tree": []}
        reasons.append(f"writer:{type(exc).__name__}:{exc}")
    if not writer.get("lock_alive"):
        reasons.append("collector_dead")
    if writer.get("authorized_writer_count") != 1:
        reasons.append("authorized_writer_count_not_one")
    if writer.get("duplicate_writers"):
        reasons.append("duplicate_writer")
    if cycles:
        latest = cycles[-1]
        reference_now = (now or datetime.now(UTC)).astimezone(UTC)
        overdue = (reference_now - _parse_time(latest["eligible_next_execution_time"])).total_seconds()
        if overdue > INTERVAL_SECONDS + GRACE_SECONDS:
            reasons.append("one_or_more_expected_cycles_late")
        if overdue > 2 * INTERVAL_SECONDS + GRACE_SECONDS:
            reasons.append("multiple_expected_cycles_missing")
    if health:
        latest_health = health[-1]
        if latest_health.get("gap_count", 0) or latest_health.get("restart_count", 0):
            reasons.append("reported_source_or_restart_gap")
    metrics: dict[str, Any] = {}
    if chain:
        try:
            metrics = storage_metrics(root, chain)
            if metrics.get("disk_state") == "RED":
                reasons.append("disk_critical")
            elif metrics.get("disk_state") == "YELLOW":
                reasons.append("disk_warning")
        except Exception as exc:
            reasons.append(f"disk:{type(exc).__name__}:{exc}")
    if not identity or not chain or not cycles or not health:
        state = "RED"
    elif any(reason in {"collector_dead", "authorized_writer_count_not_one", "duplicate_writer", "multiple_expected_cycles_missing", "disk_critical"} for reason in reasons):
        state = "RED"
    elif reasons:
        state = "YELLOW"
    else:
        state = "GREEN"
    latest_cycle = cycles[-1] if cycles else None
    latest_health = health[-1] if health else None
    expected_count = 0
    missing_count = 0
    if cycles:
        first_target = _parse_time(cycles[0]["target_bar_open"])
        last_target = _parse_time(cycles[-1]["target_bar_open"])
        expected_count = int((last_target - first_target).total_seconds() // INTERVAL_SECONDS) + 1
        missing_count = max(0, expected_count - len(cycles))
    return {
        "record_type": "R3_V8_WATCHDOG_SNAPSHOT",
        "recorded_at_utc": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "state": state,
        "reasons": reasons,
        "identity": identity,
        "writer": writer,
        "cycle_count": len(cycles),
        "health_count": len(health),
        "manifest_entry_count": len(chain),
        "first_cycle": cycles[0] if cycles else None,
        "last_cycle": latest_cycle,
        "expected_cycle_count": expected_count,
        "missing_cycle_count": missing_count,
        "latest_health": latest_health,
        "manifest_chain_verification": bool(chain),
        "launch_seal_verification": bool(identity and identity.get("seal_status") == "SEALED"),
        "storage": metrics,
        "outcomes_accessed": False,
    }


def _daily_cycle_subset(cycles: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    return [cycle for cycle in cycles if _parse_time(cycle["cycle_completed_at"]).date().isoformat() == day]


def _cycle_counts(cycles: list[dict[str, Any]]) -> tuple[int, int]:
    """Return expected and missing counts on the fixed 15-minute grid."""
    if not cycles:
        return 0, 0
    first_target = _parse_time(cycles[0]["target_bar_open"])
    last_target = _parse_time(cycles[-1]["target_bar_open"])
    expected = int((last_target - first_target).total_seconds() // INTERVAL_SECONDS) + 1
    return expected, max(0, expected - len(cycles))


def build_daily_receipt(snapshot: dict[str, Any], *, day: str) -> dict[str, Any]:
    identity = snapshot.get("identity") or {}
    cycles = [item for item in (snapshot.get("first_cycle"), snapshot.get("last_cycle")) if item]
    first_cycle = snapshot.get("first_cycle")
    last_cycle = snapshot.get("last_cycle")
    first_manifest_bytes = None
    latest_manifest_bytes = None
    storage = snapshot.get("storage") or {}
    deltas = storage.get("bytes_deltas") or []
    if deltas:
        latest_manifest_bytes = deltas[-1]
        first_manifest_bytes = deltas[0]
    writer = snapshot.get("writer") or {}
    process_identity = {
        "lock_pid": writer.get("lock_pid"),
        "authorized_writer_count": writer.get("authorized_writer_count"),
        "process_tree": writer.get("process_tree", []),
    }
    receipt = {
        "record_type": "R3_V8_DAILY_OPERATIONS_RECEIPT",
        "date": day,
        "implementation_commit": identity.get("implementation_commit"),
        "source_tree_sha256": identity.get("source_tree_sha256"),
        "registry_sha256": identity.get("registry_sha256"),
        "roster_sha256": identity.get("roster_sha256"),
        "launch_manifest_sha256": identity.get("manifest_sha256"),
        "launch_seal_sha256": identity.get("seal_sha256"),
        "first_cycle": first_cycle,
        "last_cycle": last_cycle,
        "expected_cycle_count": snapshot.get("expected_cycle_count", 0),
        "observed_cycle_count": snapshot.get("cycle_count", 0),
        "missing_cycle_count": snapshot.get("missing_cycle_count", 0),
        "gap_categories": {
            "reported_gap_count": int((snapshot.get("latest_health") or {}).get("gap_count", 0)),
            "restart_gap_count": int((snapshot.get("latest_health") or {}).get("restart_count", 0)),
        },
        "reconnect_count": int((snapshot.get("latest_health") or {}).get("restart_count", 0)),
        "manifest_chain_verification": bool(snapshot.get("manifest_chain_verification")),
        "launch_seal_verification": bool(snapshot.get("launch_seal_verification")),
        "current_process_identity": process_identity,
        "raw_byte_growth": {
            "observed_manifest_deltas": deltas,
            "first_observed_delta": first_manifest_bytes,
            "latest_observed_delta": latest_manifest_bytes,
        },
        "free_disk_bytes": (storage or {}).get("free_disk_bytes"),
        "watchdog_state": snapshot.get("state"),
        "outcomes_accessed": False,
    }
    if set(receipt) != RECEIPT_FIELDS:
        raise OperationsAuditError(f"daily receipt schema drift: {sorted(set(receipt) ^ RECEIPT_FIELDS)}")
    _reject_forbidden(receipt, context="daily receipt")
    return receipt


def append_daily_receipt(
    receipt: dict[str, Any],
    *,
    destination: Path = DAILY_RECEIPT_PATH,
    lock_path: Path = DAILY_LOCK_PATH,
) -> Path:
    destination = Path(destination)
    lock_path = Path(lock_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with single_instance_lock(lock_path):
        if destination.exists():
            for prior in _json_lines(destination):
                if prior.get("date") == receipt.get("date"):
                    raise OperationsAuditError(f"daily receipt already exists for {receipt.get('date')}")
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return destination


def _git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()


def _command_verify(args: argparse.Namespace) -> int:
    identity = verify_identity(Path(args.root), manifest=Path(args.manifest) if args.manifest else None, seal=Path(args.seal) if args.seal else None, roster=Path(args.roster), require_exact_v8=args.exact_v8)
    print(json.dumps({"status": "PASS", "head": _git_head(), "identity": identity}, sort_keys=True))
    return 0


def _command_preflight(args: argparse.Namespace) -> int:
    identity = verify_identity(Path(args.root), manifest=Path(args.manifest) if args.manifest else None, seal=Path(args.seal) if args.seal else None, roster=Path(args.roster), require_exact_v8=True)
    writer = audit_writer(Path(args.root))
    if writer.get("duplicate_writers"):
        raise OperationsAuditError("independent authorized writer detected")
    if writer.get("authorized_writer_count") == 1:
        print(json.dumps({"status": "COLLECTOR_LOCK_COLLISION", "identity": identity, "writer": writer}, sort_keys=True))
        return 73
    print(json.dumps({"status": "PASS", "identity": identity, "writer": writer}, sort_keys=True))
    return 0


def _command_watch(args: argparse.Namespace) -> int:
    snapshot = watchdog_snapshot(Path(args.root), manifest=Path(args.manifest) if args.manifest else None, seal=Path(args.seal) if args.seal else None, roster=Path(args.roster), require_exact_v8=args.exact_v8)
    print(json.dumps(snapshot, sort_keys=True))
    return 0 if snapshot["state"] != "RED" else 2


def _command_daily(args: argparse.Namespace) -> int:
    day = args.date or datetime.now(UTC).date().isoformat()
    _parse_time(day + "T00:00:00+00:00")
    snapshot = watchdog_snapshot(Path(args.root), manifest=Path(args.manifest) if args.manifest else None, seal=Path(args.seal) if args.seal else None, roster=Path(args.roster), require_exact_v8=args.exact_v8)
    # Daily fields are scoped to the requested UTC day; the watchdog state
    # itself remains a current global liveness judgment.
    all_cycles = _cycle_records(Path(args.root))
    day_cycles = _daily_cycle_subset(all_cycles, day)
    expected, missing = _cycle_counts(day_cycles)
    snapshot["first_cycle"] = day_cycles[0] if day_cycles else None
    snapshot["last_cycle"] = day_cycles[-1] if day_cycles else None
    snapshot["cycle_count"] = len(day_cycles)
    snapshot["expected_cycle_count"] = expected
    snapshot["missing_cycle_count"] = missing
    all_chain = _chain_records(Path(args.root))
    day_chain = [item for item in all_chain if _parse_time(item["created_at"]).date().isoformat() == day]
    if len(day_chain) > 1:
        snapshot.setdefault("storage", {})["bytes_deltas"] = [
            max(0, day_chain[index]["total_bytes"] - day_chain[index - 1]["total_bytes"])
            for index in range(1, len(day_chain))
        ]
    receipt = build_daily_receipt(snapshot, day=day)
    path = append_daily_receipt(receipt, destination=Path(args.destination) if args.destination else DAILY_RECEIPT_PATH, lock_path=Path(args.lock) if args.lock else DAILY_LOCK_PATH)
    print(json.dumps({"status": "APPENDED", "path": str(path), "receipt": receipt}, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=V8_ROOT)
    common.add_argument("--manifest", type=Path)
    common.add_argument("--seal", type=Path)
    common.add_argument("--roster", type=Path, default=V8_ROSTER)
    common.add_argument("--exact-v8", action="store_true")
    sub.add_parser("verify", parents=[common])
    sub.add_parser("preflight", parents=[common])
    sub.add_parser("watch", parents=[common])
    daily = sub.add_parser("daily-receipt", parents=[common])
    daily.add_argument("--date")
    daily.add_argument("--destination", type=Path)
    daily.add_argument("--lock", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            return _command_verify(args)
        if args.command == "preflight":
            return _command_preflight(args)
        if args.command == "watch":
            return _command_watch(args)
        if args.command == "daily-receipt":
            return _command_daily(args)
        raise OperationsAuditError(f"unknown command: {args.command}")
    except (OperationsAuditError, CollectorLockError, OSError, subprocess.SubprocessError) as exc:
        print(f"R3_OPERATIONS_BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
