"""Freeze a deterministic, byte-prefix cutoff of the sealed R3 v8 root.

The live collector may continue appending after the manifest snapshot.  The
receipt therefore records the exact byte and line prefix named by one complete
manifest-chain entry; it never copies or writes the live root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any


RAW_DEFAULT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8")
LAUNCH_DEFAULT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json")
SEAL_DEFAULT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json")
FORBIDDEN = ("outcome", "holdout", "return", "pnl", "r2b2")


class CutoffError(RuntimeError):
    """Fail-closed cutoff error."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_prefix(path: Path, size: int) -> tuple[str, bytes]:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    remaining = size
    with path.open("rb") as handle:
        while remaining:
            block = handle.read(min(1024 * 1024, remaining))
            if not block:
                break
            digest.update(block)
            chunks.append(block)
            remaining -= len(block)
    if remaining:
        raise CutoffError(f"file shorter than manifest prefix: {path}")
    return digest.hexdigest(), b"".join(chunks)


def _strict_object(raw: bytes, *, context: str) -> dict[str, Any]:
    def reject(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CutoffError(f"duplicate JSON key at {context}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CutoffError(f"invalid JSON at {context}") from exc
    if not isinstance(value, dict):
        raise CutoffError(f"JSON object required at {context}")
    return value


def _last_chain_snapshot(chain: Path) -> dict[str, Any]:
    lines = [line for line in chain.read_bytes().splitlines() if line.strip()]
    if not lines:
        raise CutoffError(f"manifest chain is empty: {chain}")
    snapshot = _strict_object(lines[-1], context=str(chain))
    files = snapshot.get("files")
    if not isinstance(files, list) or not files:
        raise CutoffError("manifest snapshot has no file list")
    return snapshot


def _safe_relpath(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise CutoffError("manifest path must be a non-empty POSIX relative path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or "." in parsed.parts:
        raise CutoffError(f"unsafe manifest path: {value}")
    return parsed.as_posix()


def _cycle_from_prefix(prefix: bytes) -> dict[str, str] | None:
    latest: dict[str, str] | None = None
    for line in prefix.splitlines():
        if not line.strip():
            continue
        value = _strict_object(line, context="cycle metadata prefix")
        payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
        cycle_id = payload.get("cycle_id")
        completed = payload.get("cycle_completed_at")
        if isinstance(cycle_id, str) and cycle_id and isinstance(completed, str) and completed:
            latest = {"cycle_id": cycle_id, "cycle_completed_at": completed}
    return latest


def freeze_cutoff(
    raw_root: Path,
    output: Path,
    *,
    launch_manifest: Path = LAUNCH_DEFAULT,
    launch_seal: Path = SEAL_DEFAULT,
    implementation_commit: str | None = None,
) -> dict[str, Any]:
    raw_root = raw_root.resolve()
    if raw_root.drive.upper() != "D:" or raw_root.name != "scientific_raw_v8":
        raise CutoffError(f"only the sealed D-backed v8 root is allowed: {raw_root}")
    chain = raw_root / "raw_v1" / "manifest_chain.jsonl"
    if not chain.is_file() or not launch_manifest.is_file() or not launch_seal.is_file():
        raise CutoffError("raw manifest chain, launch manifest, and launch seal are required")
    manifest_obj = _strict_object(launch_manifest.read_bytes(), context=str(launch_manifest))
    seal_obj = _strict_object(launch_seal.read_bytes(), context=str(launch_seal))
    if seal_obj.get("status") != "SEALED":
        raise CutoffError("launch seal is not SEALED")
    if manifest_obj.get("campaign_id") != "r3_prospective_context_v1":
        raise CutoffError("launch manifest campaign mismatch")
    if manifest_obj.get("scientific_root") != str(raw_root):
        raise CutoffError("launch manifest scientific root mismatch")
    manifest_sha = _sha256_file(launch_manifest)
    if seal_obj.get("manifest_sha256") != manifest_sha:
        raise CutoffError("launch seal does not bind the launch manifest")

    snapshot = _last_chain_snapshot(chain)
    if snapshot.get("raw_root") != str(raw_root / "raw_v1"):
        raise CutoffError("manifest-chain raw root mismatch")
    entries: list[dict[str, Any]] = []
    cycle: dict[str, str] | None = None
    for raw_entry in snapshot["files"]:
        if not isinstance(raw_entry, dict):
            raise CutoffError("manifest file entry is not an object")
        relative = _safe_relpath(raw_entry.get("path"))
        size = raw_entry.get("bytes")
        rows = raw_entry.get("rows")
        expected_sha = raw_entry.get("sha256")
        if not isinstance(size, int) or size < 0 or not isinstance(rows, int) or rows < 0:
            raise CutoffError(f"invalid size/row count for {relative}")
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise CutoffError(f"invalid SHA256 for {relative}")
        source = raw_root / "raw_v1" / Path(*PurePosixPath(relative).parts)
        if not source.is_file():
            raise CutoffError(f"manifest file is missing: {source}")
        actual_sha, prefix = _sha256_prefix(source, size)
        if actual_sha.lower() != expected_sha.lower():
            raise CutoffError(f"manifest prefix hash mismatch: {relative}")
        prefix_rows = prefix.count(b"\n") + (1 if prefix and not prefix.endswith(b"\n") else 0)
        if prefix_rows != rows:
            raise CutoffError(f"manifest prefix row mismatch: {relative}: {prefix_rows} != {rows}")
        if relative.endswith("/cycle_metadata.jsonl"):
            cycle = _cycle_from_prefix(prefix) or cycle
        entries.append({"path": relative, "bytes": size, "rows": rows, "sha256": expected_sha.lower()})
    entries.sort(key=lambda item: item["path"])
    if cycle is None:
        raise CutoffError("no complete cycle metadata found in manifest prefix")
    result: dict[str, Any] = {
        "record_type": "R3_FORCEORDER_V3_CUTOFF_RECEIPT",
        "status": "FROZEN",
        "raw_root": str(raw_root),
        "raw_data_root": str(raw_root / "raw_v1"),
        "manifest_chain": str(chain),
        "manifest_id": snapshot.get("manifest_id"),
        "manifest_created_at": snapshot.get("created_at"),
        "manifest_sha256": str(snapshot.get("manifest_sha256") or "").lower(),
        "previous_manifest_sha256": str(snapshot.get("previous_manifest_sha256") or "").lower(),
        "launch_manifest": str(launch_manifest),
        "launch_manifest_sha256": manifest_sha,
        "launch_seal": str(launch_seal),
        "launch_seal_sha256": _sha256_file(launch_seal),
        "launch_seal_status": "SEALED",
        "implementation_commit": implementation_commit,
        "cutoff_cycle": cycle,
        "file_count": len(entries),
        "total_bytes": sum(item["bytes"] for item in entries),
        "total_rows": sum(item["rows"] for item in entries),
        "prefix_only": True,
        "raw_v8_mutated": False,
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "files": entries,
    }
    encoded = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    lowered = str(output).replace("\\", "/").lower()
    if any(token in lowered for token in FORBIDDEN):
        raise CutoffError(f"forbidden cutoff output path: {output}")
    output = output.resolve()
    if output.exists():
        raise CutoffError(f"refusing to overwrite cutoff receipt: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded, encoding="utf-8", newline="\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=RAW_DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--launch-manifest", type=Path, default=LAUNCH_DEFAULT)
    parser.add_argument("--launch-seal", type=Path, default=SEAL_DEFAULT)
    parser.add_argument("--implementation-commit")
    args = parser.parse_args()
    result = freeze_cutoff(args.raw_root, args.output, launch_manifest=args.launch_manifest, launch_seal=args.launch_seal, implementation_commit=args.implementation_commit)
    print(json.dumps({key: result[key] for key in ("status", "manifest_id", "manifest_sha256", "file_count", "total_rows", "cutoff_cycle", "raw_v8_mutated", "outcomes_accessed")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
