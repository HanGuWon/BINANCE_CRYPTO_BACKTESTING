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
    if manifest.get("roster_sha256") != roster_sha256:
        raise LaunchIdentityError("roster SHA does not match launch manifest")
    for field in ("implementation_commit", "source_tree_sha256", "registry_sha256"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            raise LaunchIdentityError(f"launch manifest lacks exact {field}")
        if field != "implementation_commit":
            require_sha256(value, field)
    if implementation_commit and manifest.get("implementation_commit") != implementation_commit:
        raise LaunchIdentityError("implementation commit does not match launch manifest")
    return manifest


def verify_scientific_launch_identity(manifest_path: Path, *, expected: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when any pinned scientific contract identity is absent or mismatched."""
    manifest = verify_launch_identity(manifest_path, roster_sha256=str(expected["roster_sha256"]), implementation_commit=str(expected.get("implementation_commit")) if expected.get("implementation_commit") else None)
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise LaunchIdentityError(f"scientific launch identity mismatch: {field}")
    return manifest


def verify_launch_seal(seal_path: Path, manifest_path: Path, *, roster_sha256: str, scientific_root: Path | None = None) -> dict[str, Any]:
    """Require a sealed, content-addressed launch before scientific collection."""
    seal_path, manifest_path = Path(seal_path), Path(manifest_path)
    if not seal_path.is_file():
        raise LaunchIdentityError("launch seal is missing")
    try:
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LaunchIdentityError("launch seal is invalid") from exc
    if seal.get("status") != "SEALED":
        raise LaunchIdentityError("launch seal is not SEALED")
    actual_manifest_sha = _sha256(manifest_path)
    if seal.get("manifest_sha256") != actual_manifest_sha:
        raise LaunchIdentityError("launch seal manifest SHA does not match manifest")
    sealed_manifest = Path(str(seal.get("manifest_path", ""))).resolve()
    if sealed_manifest != manifest_path.resolve():
        raise LaunchIdentityError("launch seal manifest path mismatch")
    if seal.get("roster_sha256") != roster_sha256:
        raise LaunchIdentityError("launch seal roster SHA does not match")
    manifest = verify_launch_identity(manifest_path, roster_sha256=roster_sha256)
    if scientific_root is not None and Path(str(manifest.get("scientific_root", ""))).resolve() != Path(scientific_root).resolve():
        raise LaunchIdentityError("launch seal scientific root mismatch")
    try:
        sealed_at = datetime.fromisoformat(str(seal["sealed_at_utc"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise LaunchIdentityError("launch seal lacks valid completion time") from exc
    return {"seal": seal, "manifest": manifest, "manifest_sha256": actual_manifest_sha, "sealed_at_utc": sealed_at.astimezone(UTC).isoformat()}


def cycle_metadata(*, cycle_id: str, target_bar_open: str, target_bar_close: str, scheduled_collection_time: str, actual_collection_start: str, cycle_completed_at: str, clock_calibration_id: str, eligible_next_execution_time: str) -> dict[str, str]:
    """Return the canonical machine-readable cycle timing record."""
    return {"cycle_id": cycle_id, "target_bar_open": target_bar_open, "target_bar_close": target_bar_close, "scheduled_collection_time": scheduled_collection_time, "actual_collection_start": actual_collection_start, "cycle_completed_at": cycle_completed_at, "clock_calibration_id": clock_calibration_id, "eligible_next_execution_time": eligible_next_execution_time}


def finalize_segment(segment_path: Path, receipt_path: Path) -> dict[str, Any]:
    """Write or verify an immutable bounded segment receipt."""
    segment_path, receipt_path = Path(segment_path), Path(receipt_path)
    if not segment_path.is_file():
        raise ValueError("segment does not exist")
    rows = [json.loads(line) for line in segment_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    record = {"path": str(segment_path), "rows": len(rows), "bytes": segment_path.stat().st_size, "sha256": _sha256(segment_path), "first_event_time": next((r.get("exchange_event_time") for r in rows if r.get("exchange_event_time") is not None), None), "last_event_time": next((r.get("exchange_event_time") for r in reversed(rows) if r.get("exchange_event_time") is not None), None), "first_receipt_time": next((r.get("collector_receipt_time") for r in rows if r.get("collector_receipt_time") is not None), None), "last_receipt_time": next((r.get("collector_receipt_time") for r in reversed(rows) if r.get("collector_receipt_time") is not None), None), "status": "FINALIZED"}
    if receipt_path.exists():
        prior = json.loads(receipt_path.read_text(encoding="utf-8"))
        if prior != record:
            raise ValueError("finalized segment is immutable and receipt changed")
        return prior
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return record


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


def verify_engineering_shadow_root(root: Path, *, expected_symbols: list[str], roster_sha256: str) -> dict[str, Any]:
    """Verify an outcome-blind roster shadow root without reading market outcomes."""
    root = Path(root)
    raw = root / "raw_v1"
    chain = raw / "manifest_chain.jsonl"
    health_path = root / "health" / "health_receipts.jsonl"
    if not raw.is_dir() or not chain.is_file() or not verify_manifest_chain(chain):
        raise ValueError("shadow manifest chain is missing or invalid")
    if not health_path.is_file():
        raise ValueError("shadow health receipt is missing")
    health_lines = [line for line in health_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    health = json.loads(health_lines[-1])
    if health.get("evidence_mode") != "ENGINEERING_SHADOW":
        raise ValueError("shadow health receipt has the wrong evidence mode")
    if health.get("roster_sha256") != require_sha256(roster_sha256, "roster_sha256"):
        raise ValueError("shadow roster identity mismatch")
    files = [path for path in raw.rglob("*.jsonl") if path.name != "manifest_chain.jsonl"]
    rows = 0
    bytes_total = 0
    symbols: set[str] = set()
    per_symbol_streams: dict[str, set[str]] = {}
    per_symbol_gaps: dict[str, set[str]] = {}
    modes: set[str | None] = set()
    primary_streams = {"book_ticker", "klines_15m", "open_interest", "premium", "premium_klines_15m"}
    for path in files:
        bytes_total += path.stat().st_size
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            envelope = json.loads(line)
            rows += 1
            if envelope.get("stream") in primary_streams:
                symbol = str(envelope.get("symbol"))
                stream = str(envelope.get("stream"))
                symbols.add(symbol)
                per_symbol_streams.setdefault(symbol, set()).add(stream)
                if stream in {"klines_15m", "premium_klines_15m"}:
                    payload = envelope.get("payload")
                    if not isinstance(payload, dict) or not payload.get("source_open_time") or not payload.get("source_available_time"):
                        raise ValueError("normalized kline envelope lacks source timing")
            elif envelope.get("stream") == "collector_status":
                payload = envelope.get("payload") or {}
                symbol = str(envelope.get("symbol"))
                stream = payload.get("stream")
                if stream in primary_streams and envelope.get("continuity_state") in {"POLL_GAP", "RATE_LIMIT_GAP", "RESTART_GAP", "SEQUENCE_GAP"}:
                    per_symbol_gaps.setdefault(symbol, set()).add(str(stream))
            modes.add(envelope.get("evidence_mode"))
    if modes != {"ENGINEERING_SHADOW"}:
        raise ValueError("shadow raw envelopes are not uniformly labeled")
    expected = {str(symbol).upper() for symbol in expected_symbols}
    if (symbols - {"ALL"}) != expected:
        raise ValueError("shadow symbol set does not match roster")
    for symbol in expected:
        missing = primary_streams - per_symbol_streams.get(symbol, set()) - per_symbol_gaps.get(symbol, set())
        if missing:
            raise ValueError(f"shadow symbol {symbol} missing primary streams: {sorted(missing)}")
    latest = json.loads([line for line in chain.read_text(encoding="utf-8").splitlines() if line.strip()][-1])
    if latest.get("manifest_sha256") != health.get("manifest_sha256"):
        raise ValueError("health receipt does not bind the latest manifest")
    if latest.get("total_rows") != rows or latest.get("total_bytes") != bytes_total or len(latest.get("files", [])) != len(files):
        raise ValueError("manifest totals do not match shadow files")
    return {"manifest_sha256": latest["manifest_sha256"], "files": len(files), "rows": rows, "bytes": bytes_total, "symbols": len(expected), "gap_count": health.get("gap_count", 0)}


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
