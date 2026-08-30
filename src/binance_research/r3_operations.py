"""Append-only R3 manifest, health, and single-instance operational guards."""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


class CollectorLockError(RuntimeError):
    pass


class LaunchIdentityError(RuntimeError):
    pass


def _pid_is_alive(pid: int) -> bool:
    """Probe a PID without Windows ``os.kill(..., 0)`` console side effects."""
    if pid == os.getpid():
        return True
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


def require_sha256(value: str, field: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise ValueError(f"{field} must be a hexadecimal SHA256")
    return value.lower()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def single_instance_lock(path: Path) -> Iterator[None]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        # Recover only demonstrably stale PID locks; a live or malformed lock
        # remains a hard collision and is never silently removed.
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
            if _pid_is_alive(pid):
                raise CollectorLockError(f"collector lock already held: {path}") from exc
            path.unlink(missing_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (ValueError, FileNotFoundError):
            raise CollectorLockError(f"collector lock already held: {path}") from exc
        except OSError as probe:
            raise CollectorLockError(f"collector lock owner cannot be inspected: {path}") from probe
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        path.unlink(missing_ok=True)


def build_manifest(root: Path, *, previous_manifest_sha256: str | None = None, manifest_id: str | None = None) -> dict[str, Any]:
    root = Path(root)
    files = []
    for path in sorted(root.rglob("*.jsonl")):
        if path.name == "manifest_chain.jsonl":
            continue
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path), "rows": sum(1 for _ in path.open("rb"))})
    body = {"manifest_id": manifest_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"), "created_at": datetime.now(UTC).isoformat(), "raw_root": str(root), "previous_manifest_sha256": previous_manifest_sha256, "files": files, "total_bytes": sum(item["bytes"] for item in files), "total_rows": sum(item["rows"] for item in files)}
    body["manifest_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return body


def append_manifest(root: Path, manifest: dict[str, Any]) -> Path:
    destination = Path(root) / "manifest_chain.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return destination


def append_segment_manifest(root: Path, manifest: dict[str, Any], *, segment_id: str) -> Path:
    """Append a hash-linked manifest to an isolated segment file."""
    if not segment_id or any(char in segment_id for char in "/\\"):
        raise ValueError("segment_id must be a non-empty path-safe identifier")
    destination = Path(root) / "segments" / f"segment_{segment_id}.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return destination


def verify_launch_identity(manifest_path: Path, *, roster_sha256: str, implementation_commit: str | None = None) -> dict[str, Any]:
    """Load a launch manifest and fail closed on blocked/mismatched identity."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("status") != "R3_READY_FOR_PROSPECTIVE_LAUNCH":
        raise LaunchIdentityError(f"launch manifest status is {manifest.get('status')!r}")
    if manifest.get("pilot_status") == "ENGINEERING_PILOT_ONLY":
        raise LaunchIdentityError("engineering pilot identity cannot authorize scientific collection")
    if manifest.get("roster_sha256") not in {None, roster_sha256}:
        raise LaunchIdentityError("roster SHA does not match launch manifest")
    if implementation_commit and manifest.get("implementation_commit") != implementation_commit:
        raise LaunchIdentityError("implementation commit does not match launch manifest")
    return manifest


def verify_manifest_chain(path: Path) -> bool:
    previous = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        manifest = json.loads(line)
        expected = manifest.pop("manifest_sha256")
        if manifest.get("previous_manifest_sha256") != previous:
            return False
        actual = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if actual != expected:
            return False
        previous = expected
    return True


def write_health_receipt(root: Path, *, campaign_id: str, manifest_sha256: str | None, roster_sha256: str | None, stream_state: dict[str, Any], raw_root: Path | None = None, restart_count: int = 0, gap_count: int = 0, evidence_mode: str | None = None) -> Path:
    raw_root = Path(raw_root or root)
    receipt = {"timestamp": datetime.now(UTC).isoformat(), "pid": os.getpid(), "campaign_id": campaign_id, "manifest_sha256": manifest_sha256, "roster_sha256": roster_sha256, "raw_root": str(raw_root), "stream_state": stream_state, "restart_count": restart_count, "gap_count": gap_count, "bytes": sum(path.stat().st_size for path in raw_root.rglob("*.jsonl"))}
    if evidence_mode is not None:
        receipt["evidence_mode"] = evidence_mode
    destination = Path(root) / "health" / "health_receipts.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return destination


PILOT_ALLOWED_FIELDS = frozenset({"timestamp", "campaign_id", "mode", "symbols", "manifest_sha256", "roster_sha256", "stream_counts", "bytes", "latency_seconds", "gap_counts", "storage_projection_bytes", "liquidation_state"})


def write_pilot_receipt(root: Path, *, symbols: list[str], manifest_sha256: str, roster_sha256: str, stream_counts: dict[str, int], bytes_written: int, latency_seconds: dict[str, float], gap_counts: dict[str, int], storage_projection_bytes: dict[str, int], liquidation_state: dict[str, Any]) -> Path:
    receipt = {"timestamp": datetime.now(UTC).isoformat(), "campaign_id": "r3_prospective_context_v1", "mode": "ENGINEERING_PILOT", "symbols": sorted(symbols), "manifest_sha256": manifest_sha256, "roster_sha256": roster_sha256, "stream_counts": dict(sorted(stream_counts.items())), "bytes": int(bytes_written), "latency_seconds": dict(sorted(latency_seconds.items())), "gap_counts": dict(sorted(gap_counts.items())), "storage_projection_bytes": dict(sorted(storage_projection_bytes.items())), "liquidation_state": liquidation_state}
    if set(receipt) != PILOT_ALLOWED_FIELDS:
        raise AssertionError("pilot receipt contains a non-operational field")
    destination = Path(root) / "health" / "pilot_receipts.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return destination
