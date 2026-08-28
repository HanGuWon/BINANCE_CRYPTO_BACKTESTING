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
        raise CollectorLockError(f"collector lock already held: {path}") from exc
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


def write_health_receipt(root: Path, *, campaign_id: str, manifest_sha256: str | None, roster_sha256: str | None, stream_state: dict[str, Any], raw_root: Path | None = None, restart_count: int = 0, gap_count: int = 0) -> Path:
    raw_root = Path(raw_root or root)
    receipt = {"timestamp": datetime.now(UTC).isoformat(), "pid": os.getpid(), "campaign_id": campaign_id, "manifest_sha256": manifest_sha256, "roster_sha256": roster_sha256, "raw_root": str(raw_root), "stream_state": stream_state, "restart_count": restart_count, "gap_count": gap_count, "bytes": sum(path.stat().st_size for path in raw_root.rglob("*.jsonl"))}
    destination = Path(root) / "health" / "health_receipts.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return destination
