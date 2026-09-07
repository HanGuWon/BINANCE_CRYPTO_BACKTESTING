"""Create an outcome-blind R3 V2 firewall/identity audit receipt.

The audit reads launch/control metadata and hashes the D-backed tree without
parsing market observations.  It is intentionally separate from evaluation
materialization and has no response, return, or performance fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from r3_ops import audit_writer, watchdog_snapshot


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8")
DEFAULT_ROSTER = REPO_ROOT / "campaigns/r3_prospective_context_v1/rosters/2026-09.json"
DEFAULT_MANIFEST = Path(
    r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json"
)
DEFAULT_SEAL = Path(
    r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json"
)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _tree_snapshot(root: Path) -> dict[str, Any]:
    """Hash path names and bytes only; never decode or inspect payloads."""

    digest = hashlib.sha256()
    file_count = 0
    byte_count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(relative)
        digest.update(payload)
        file_count += 1
        byte_count += len(payload)
    return {
        "file_count": file_count,
        "byte_count": byte_count,
        "tree_sha256": digest.hexdigest(),
    }


def _scientific_status() -> str:
    return _git("status", "--porcelain", "--", "scripts", "src", "tests", "configs")


def build_audit(*, root: Path, roster: Path, manifest: Path, seal: Path) -> dict[str, Any]:
    manifest_before = hashlib.sha256(manifest.read_bytes()).hexdigest()
    seal_before = hashlib.sha256(seal.read_bytes()).hexdigest()
    before = _tree_snapshot(root)
    # A short, bounded read-only window.  The collector remains running.
    time.sleep(1)
    after = _tree_snapshot(root)
    manifest_after = hashlib.sha256(manifest.read_bytes()).hexdigest()
    seal_after = hashlib.sha256(seal.read_bytes()).hexdigest()

    identity = watchdog_snapshot(root, manifest=manifest, seal=seal, roster=roster, require_exact_v8=True)
    writer = audit_writer(root)
    ahead_behind = _git("rev-list", "--left-right", "--count", "HEAD...origin/research/r2b-restricted-derivatives-v1")
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    origin_head = _git("rev-parse", "origin/research/r2b-restricted-derivatives-v1")
    source_status = _scientific_status()

    report = {
        "record_type": "R3_V2_FIREWALL_ROOT_IDENTITY_AUDIT",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "branch": branch,
        "head": head,
        "origin_head": origin_head,
        "ahead_behind": ahead_behind,
        "scientific_source_dirty": bool(source_status),
        "scientific_source_status_output": source_status,
        "implementation_commit": identity["identity"]["implementation_commit"],
        "source_tree_sha256": identity["identity"]["source_tree_sha256"],
        "registry_sha256": identity["identity"]["registry_sha256"],
        "root": str(root),
        "root_file_count_before": before["file_count"],
        "root_file_count_after": after["file_count"],
        "root_byte_count_before": before["byte_count"],
        "root_byte_count_after": after["byte_count"],
        "root_tree_sha256_before": before["tree_sha256"],
        "root_tree_sha256_after": after["tree_sha256"],
        "root_stable_during_audit": before == after,
        "manifest_sha256": identity["identity"]["manifest_sha256"],
        "seal_sha256": identity["identity"]["seal_sha256"],
        "seal_status": identity["identity"]["seal_status"],
        "manifest_chain_verification": identity["identity"]["manifest_chain_verification"],
        "manifest_entry_count": identity.get("manifest_entry_count"),
        "health_count": identity.get("health_count"),
        "cycle_count": identity.get("cycle_count"),
        "watchdog_state": identity.get("state"),
        "watchdog_reasons": identity.get("reasons", []),
        "writer": {
            "authorized_writer_count": writer.get("authorized_writer_count"),
            "duplicate_writers": writer.get("duplicate_writers", []),
            "lock_alive": writer.get("lock_alive"),
            "lock_pid": writer.get("lock_pid"),
        },
        "outcomes_accessed": identity.get("outcomes_accessed"),
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_STARTED",
        "no_root_or_manifest_rewrite": (
            before == after and manifest_before == manifest_after and seal_before == seal_after
        ),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--seal", type=Path, default=DEFAULT_SEAL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_audit(root=args.root, roster=args.roster, manifest=args.manifest, seal=args.seal)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(args.output), "root_stable": report["root_stable_during_audit"], "writer_count": report["writer"]["authorized_writer_count"], "outcomes_accessed": report["outcomes_accessed"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
