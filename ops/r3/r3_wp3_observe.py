"""Outcome-blind, append-only observer for the sealed-v8 recovery phase.

The observer reads only launch identity, control metadata, cycle metadata,
health receipts, manifest-chain bytes, and process/lock metadata.  It never
opens symbol payloads and never starts, stops, repairs, or backfills a
collector.  Exit 0 means every WP3 gate passed; exit 2 is a durable block
receipt; all other failures are execution failures and are fail-closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ops.r3 import r3_ops


OBSERVATION_FIELDS = frozenset(
    {
        "record_type",
        "recorded_at_utc",
        "observation_index",
        "command",
        "cwd",
        "exit_code",
        "state",
        "reasons",
        "cycle_count",
        "expected_cycle_count",
        "current_grid_missing_cycle_count",
        "historical_baseline_missing_cycle_count",
        "baseline_last_cycle_id",
        "new_cycle_ids",
        "nonqualifying_post_launch_cycle_ids",
        "launch_consumed_at_utc",
        "writer_before",
        "writer_after",
        "writer_pid_continuity",
        "duplicate_writers",
        "process_tree_sha256",
        "collector_candidate_census",
        "identity",
        "control_identity_sha256",
        "chain_prefix_entry_count",
        "chain_prefix_sha256",
        "historical_cycle_id_set_sha256",
        "full_chain_sha256",
        "cycle_metadata_prefix_sha256",
        "prior_observation_receipt",
        "prior_receipt_sha256",
        "receipt_body_sha256",
        "outcomes_accessed",
        "final_holdout",
        "r2b2",
        "forceorder_v3_migration",
    }
)

ANCHOR_FIELDS = frozenset(
    {
        "record_type",
        "recorded_at_utc",
        "source_receipt",
        "source_receipt_sha256",
        "launch_receipt",
        "launch_receipt_sha256",
        "launch_consumed_at_utc",
        "root",
        "implementation_commit",
        "source_tree_sha256",
        "registry_sha256",
        "roster_sha256",
        "roster_file_sha256",
        "launch_manifest_sha256",
        "launch_seal_sha256",
        "control_identity_sha256",
        "historical_cycle_count",
        "historical_expected_cycle_count",
        "historical_missing_cycle_count",
        "baseline_last_cycle_id",
        "baseline_last_target_bar_open",
        "chain_prefix_entry_count",
        "chain_prefix_sha256",
        "cycle_metadata_prefix_sha256",
        "historical_cycle_id_set_sha256",
        "writer_pid_at_launch",
        "outcomes_accessed",
        "final_holdout",
        "r2b2",
        "forceorder_v3_migration",
    }
)

# The anchor is immutable evidence created in this plan.  Pin its file bytes
# so a modified local anchor cannot silently redefine the preserved gap.
EXPECTED_ANCHOR_SHA256 = "aeb1732b9667421d13f7f46fac2ac6269a9528a102a12a9fc6c40f8add5a27fd"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _control_identity(identity: dict[str, Any]) -> tuple[dict[str, Any], str]:
    fields = {
        "root": str(Path(str(identity["root"])).resolve()),
        "implementation_commit": str(identity["implementation_commit"]),
        "source_tree_sha256": str(identity["source_tree_sha256"]),
        "registry_sha256": str(identity["registry_sha256"]),
        "roster_sha256": str(identity["roster_sha256"]),
        "roster_file_sha256": str(identity["roster_file_sha256"]),
        "launch_manifest_sha256": str(identity["manifest_sha256"]),
        "launch_seal_sha256": str(identity["seal_sha256"]),
    }
    return fields, _sha_bytes(_canonical(fields).encode("utf-8"))


def _prefix_hash(root: Path, count: int) -> tuple[str, int, str]:
    path = Path(root) / "raw_v1" / "manifest_chain.jsonl"
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    if len(lines) < count:
        raise ValueError(f"manifest chain has {len(lines)} entries; expected at least {count}")
    prefix = b"".join(lines[:count])
    return _sha_bytes(prefix), len(lines), _sha_bytes(raw)


def _metadata_prefix_hash(root: Path, count: int) -> tuple[str, int]:
    paths = sorted((Path(root) / "raw_v1").rglob("cycle_metadata.jsonl"))
    if len(paths) != 1:
        raise ValueError(f"expected exactly one cycle metadata stream, found {len(paths)}")
    raw = paths[0].read_bytes()
    lines = raw.splitlines(keepends=True)
    if len(lines) < count:
        raise ValueError(f"cycle metadata has {len(lines)} lines; expected at least {count}")
    return _sha_bytes(b"".join(lines[:count])), len(lines)


def _cycle_id_hash(cycles: list[dict[str, Any]], count: int) -> str:
    if len(cycles) < count:
        raise ValueError(f"cycle metadata has {len(cycles)} records; expected at least {count}")
    ids = sorted(str(item["cycle_id"]) for item in cycles[:count])
    return _sha_bytes(_canonical(ids).encode("utf-8"))


def _writer_tree_hash(writer: dict[str, Any]) -> str:
    return _sha_bytes(_canonical(writer.get("process_tree", [])).encode("utf-8"))


def _blank_receipt(args: argparse.Namespace, exit_code: int, reason: str) -> dict[str, Any]:
    return {
        "record_type": "R3_V8_WP3_OBSERVATION",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "observation_index": int(args.observation_index),
        "command": list(args.command),
        "cwd": str(Path.cwd().resolve()),
        "exit_code": int(exit_code),
        "state": "BLOCKED",
        "reasons": [reason],
        "cycle_count": 0,
        "expected_cycle_count": 0,
        "current_grid_missing_cycle_count": 0,
        "historical_baseline_missing_cycle_count": 0,
        "baseline_last_cycle_id": None,
        "new_cycle_ids": [],
        "nonqualifying_post_launch_cycle_ids": [],
        "launch_consumed_at_utc": None,
        "writer_before": {},
        "writer_after": {},
        "writer_pid_continuity": {"stable": False},
        "duplicate_writers": [],
        "process_tree_sha256": None,
        "collector_candidate_census": {"before": [], "after": [], "unmatched": []},
        "identity": {},
        "control_identity_sha256": None,
        "chain_prefix_entry_count": 0,
        "chain_prefix_sha256": None,
        "historical_cycle_id_set_sha256": None,
        "full_chain_sha256": None,
        "cycle_metadata_prefix_sha256": None,
        "prior_observation_receipt": None,
        "prior_receipt_sha256": None,
        "receipt_body_sha256": None,
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
    }


def observe(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    root = Path(args.root).resolve()
    anchor_path = Path(args.baseline_anchor).resolve()
    if r3_ops._sha256(anchor_path) != EXPECTED_ANCHOR_SHA256:
        raise ValueError("baseline anchor file hash mismatch")
    anchor = _read_json(anchor_path)
    if set(anchor) != ANCHOR_FIELDS or anchor.get("record_type") != "R3_V8_WP3_BASELINE_ANCHOR":
        raise ValueError("baseline anchor record_type mismatch")
    launch_path = Path(args.launch_receipt).resolve()
    if r3_ops._sha256(launch_path) != str(anchor["launch_receipt_sha256"]):
        raise ValueError("launch receipt file hash mismatch")
    source_receipt_path = (r3_ops.REPO_ROOT / str(anchor["source_receipt"])).resolve()
    if r3_ops._sha256(source_receipt_path) != str(anchor["source_receipt_sha256"]):
        raise ValueError("baseline source receipt file hash mismatch")
    launch = _read_json(launch_path)
    if launch.get("record_type") != "R3_V8_AUTHORIZED_RESUME_LAUNCH":
        raise ValueError("launch receipt record_type mismatch")
    launch_time = r3_ops._parse_time(launch["authorization_consumed_at_utc"])
    if int(anchor["historical_cycle_count"]) != 197:
        raise ValueError("WP3 requires the 197-cycle historical anchor")
    if int(anchor["historical_missing_cycle_count"]) != 87:
        raise ValueError("WP3 requires the 87-cycle preserved-gap anchor")
    if launch.get("authorization_consumed_at_utc") != anchor.get("launch_consumed_at_utc"):
        raise ValueError("launch timestamp does not match baseline anchor")
    if str(Path(str(anchor["root"])).resolve()) != str(root):
        raise ValueError("baseline root mismatch")

    identity = r3_ops.verify_identity(
        root,
        manifest=r3_ops.V8_MANIFEST,
        seal=r3_ops.V8_SEAL,
        roster=r3_ops.V8_ROSTER,
        require_exact_v8=True,
    )
    control_fields, control_sha = _control_identity(identity)
    if control_sha != anchor.get("control_identity_sha256"):
        raise ValueError("control identity hash drift")

    cycles = r3_ops._cycle_records(root)
    health = r3_ops._health_records(root)
    chain = r3_ops._chain_records(root)
    prefix_sha, chain_count, full_chain_sha = _prefix_hash(root, int(anchor["chain_prefix_entry_count"]))
    historical_id_sha = _cycle_id_hash(cycles, int(anchor["historical_cycle_count"]))
    metadata_baseline_sha, _ = _metadata_prefix_hash(root, int(anchor["historical_cycle_count"]))
    reasons: list[str] = []
    process_before = r3_ops._process_snapshot()
    writer_before = r3_ops.audit_writer(root, snapshot=process_before)
    process_after = r3_ops._process_snapshot()
    writer_after = r3_ops.audit_writer(root, snapshot=process_after)
    def candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            row
            for row in rows
            if "run_r3_prospective_collector.py" in str(row.get("command_line", "")).lower()
            and Path(str(row.get("executable", ""))).name.lower().startswith("python")
        ]
    candidates_before = candidates(process_before)
    candidates_after = candidates(process_after)
    authorized_tree_pids_before = {int(item["pid"]) for item in writer_before.get("process_tree", [])}
    authorized_tree_pids_after = {int(item["pid"]) for item in writer_after.get("process_tree", [])}
    unmatched_before = [row for row in candidates_before if int(row["pid"]) not in authorized_tree_pids_before]
    unmatched_after = [row for row in candidates_after if int(row["pid"]) not in authorized_tree_pids_after]
    unmatched = [
        {"snapshot": "before", "row": row} for row in unmatched_before
    ] + [
        {"snapshot": "after", "row": row} for row in unmatched_after
    ]
    writer_pid_before = writer_before.get("lock_pid")
    writer_pid_after = writer_after.get("lock_pid")
    writer_pid_continuity = {
        "baseline_pid": int(anchor["writer_pid_at_launch"]),
        "before_pid": writer_pid_before,
        "after_pid": writer_pid_after,
        "stable_within_observation": writer_pid_before == writer_pid_after,
        "stable_from_launch": writer_pid_after == int(anchor["writer_pid_at_launch"]),
    }
    if writer_before.get("authorized_writer_count") != 1 or writer_after.get("authorized_writer_count") != 1:
        reasons.append("authorized_writer_count_not_one")
    if not writer_before.get("lock_alive") or not writer_after.get("lock_alive"):
        reasons.append("lock_not_alive")
    if writer_before.get("duplicate_writers") or writer_after.get("duplicate_writers"):
        reasons.append("duplicate_writer")
    if len(candidates_before) != 1 or len(candidates_after) != 1:
        reasons.append("collector_candidate_count_not_one")
    if unmatched:
        reasons.append("unmatched_collector_candidate")
    if not writer_pid_continuity["stable_within_observation"] or not writer_pid_continuity["stable_from_launch"]:
        reasons.append("writer_pid_not_continuous")
    if prefix_sha != anchor.get("chain_prefix_sha256"):
        reasons.append("historical_chain_prefix_changed")
    if historical_id_sha != anchor.get("historical_cycle_id_set_sha256"):
        reasons.append("historical_cycle_id_set_changed")
    if metadata_baseline_sha != anchor.get("cycle_metadata_prefix_sha256"):
        reasons.append("historical_cycle_metadata_prefix_changed")
    if len(cycles) != len(health) or len(cycles) != len(chain):
        reasons.append("cycle_health_manifest_count_mismatch")

    baseline_ids = {str(item["cycle_id"]) for item in cycles[: int(anchor["historical_cycle_count"])]}
    post_launch_cycles = [item for item in cycles if str(item["cycle_id"]) not in baseline_ids]
    nonqualifying_ids: list[str] = []
    new_cycles: list[dict[str, Any]] = []
    new_ids: list[str] = []
    for item in post_launch_cycles:
        cycle_id = str(item["cycle_id"])
        target_open = r3_ops._parse_time(item["target_bar_open"])
        completed = r3_ops._parse_time(item["cycle_completed_at"])
        if target_open <= launch_time or completed <= launch_time:
            nonqualifying_ids.append(cycle_id)
            continue
        new_cycles.append(item)
        new_ids.append(cycle_id)
    if len(new_ids) != len(set(new_ids)):
        reasons.append("duplicate_new_cycle_id")
    if len(new_ids) < 2:
        reasons.append("fewer_than_two_new_cycles")
    if len(health) < len(cycles) or len(chain) < len(cycles):
        reasons.append("missing_health_or_manifest_evidence")
    tree_hash = _writer_tree_hash(writer_after)
    metadata_prefix_sha, metadata_line_count = _metadata_prefix_hash(root, len(cycles))
    if identity.get("seal_status") != "SEALED" or identity.get("manifest_chain_verification") is not True:
        reasons.append("chain_or_seal_failure")
    storage = r3_ops.storage_metrics(root, chain)
    if storage.get("disk_state") == "RED":
        reasons.append("disk_critical")

    expected_count, current_missing = r3_ops._cycle_counts(cycles)
    prior_receipt_path: Path | None = Path(args.prior_receipt).resolve() if args.prior_receipt else None
    prior_receipt: dict[str, Any] | None = None
    prior_receipt_sha: str | None = None
    if prior_receipt_path:
        if prior_receipt_path.parent != Path(args.output).resolve().parent:
            reasons.append("prior_observation_outside_evidence_directory")
        prior_receipt_sha = r3_ops._sha256(prior_receipt_path)
        prior_receipt = _read_json(prior_receipt_path)
        if set(prior_receipt) != OBSERVATION_FIELDS:
            reasons.append("prior_observation_schema_mismatch")
        if int(prior_receipt.get("observation_index", -1)) != int(args.observation_index) - 1:
            reasons.append("prior_observation_sequence_mismatch")
        prior_body = dict(prior_receipt)
        prior_body["receipt_body_sha256"] = None
        if prior_receipt.get("receipt_body_sha256") != _sha_bytes(_canonical(prior_body).encode("utf-8")):
            reasons.append("prior_observation_integrity_failure")
        prior_count = int(prior_receipt.get("cycle_count", 0))
        if prior_count <= 0 or len(cycles) < prior_count:
            reasons.append("prior_observation_cycle_count_invalid")
        else:
            prior_chain_prefix, _, _ = _prefix_hash(root, prior_count)
            prior_metadata_prefix, _ = _metadata_prefix_hash(root, prior_count)
            if prior_chain_prefix != prior_receipt.get("full_chain_sha256"):
                reasons.append("post_baseline_chain_prefix_changed")
            if prior_metadata_prefix != prior_receipt.get("cycle_metadata_prefix_sha256"):
                reasons.append("post_baseline_cycle_metadata_prefix_changed")
    receipt = {
        "record_type": "R3_V8_WP3_OBSERVATION",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "observation_index": int(args.observation_index),
        "command": list(args.command),
        "cwd": str(Path.cwd().resolve()),
        "exit_code": 0 if not reasons else 2,
        "state": "PASS" if not reasons else "BLOCKED",
        "reasons": reasons,
        "cycle_count": len(cycles),
        "expected_cycle_count": expected_count,
        "current_grid_missing_cycle_count": current_missing,
        "historical_baseline_missing_cycle_count": int(anchor["historical_missing_cycle_count"]),
        "baseline_last_cycle_id": anchor["baseline_last_cycle_id"],
        "new_cycle_ids": new_ids,
        "nonqualifying_post_launch_cycle_ids": nonqualifying_ids,
        "launch_consumed_at_utc": launch["authorization_consumed_at_utc"],
        "writer_before": writer_before,
        "writer_after": writer_after,
        "writer_pid_continuity": writer_pid_continuity,
        "duplicate_writers": writer_after.get("duplicate_writers", []),
        "process_tree_sha256": tree_hash,
        "collector_candidate_census": {
            "before": candidates_before,
            "after": candidates_after,
            "unmatched": unmatched,
            "all_process_snapshot_counts": {"before": len(process_before), "after": len(process_after)},
        },
        "identity": identity,
        "control_identity_sha256": control_sha,
        "chain_prefix_entry_count": int(anchor["chain_prefix_entry_count"]),
        "chain_prefix_sha256": prefix_sha,
        "historical_cycle_id_set_sha256": historical_id_sha,
        "full_chain_sha256": full_chain_sha,
        "cycle_metadata_prefix_sha256": metadata_prefix_sha,
        "prior_observation_receipt": str(prior_receipt_path) if prior_receipt_path else None,
        "prior_receipt_sha256": prior_receipt_sha,
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
    }
    body = dict(receipt)
    body["receipt_body_sha256"] = None
    receipt["receipt_body_sha256"] = _sha_bytes(_canonical(body).encode("utf-8"))
    # Keep the schema closed and make a receipt self-auditing before writing it.
    if set(receipt) != OBSERVATION_FIELDS:
        raise AssertionError(f"observation schema drift: {sorted(set(receipt) ^ OBSERVATION_FIELDS)}")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite observation receipt: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    r3_ops._write_json_exclusive(args.output, receipt)
    return receipt, int(receipt["exit_code"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation-index", type=int, required=True)
    parser.add_argument("--baseline-anchor", type=Path, required=True)
    parser.add_argument("--launch-receipt", type=Path, required=True)
    parser.add_argument("--prior-receipt", type=Path)
    parser.add_argument("--root", type=Path, default=r3_ops.V8_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.command = sys.argv
    try:
        receipt, code = observe(args)
    except Exception as exc:  # fail closed and preserve a machine-readable reason
        receipt = _blank_receipt(args, 2, f"observer_exception:{type(exc).__name__}:{exc}")
        body = dict(receipt)
        body["receipt_body_sha256"] = None
        receipt["receipt_body_sha256"] = _sha_bytes(_canonical(body).encode("utf-8"))
        if args.output.exists():
            print(f"R3_WP3_OBSERVATION_BLOCKED: {exc}", file=sys.stderr)
            return 2
        args.output.parent.mkdir(parents=True, exist_ok=True)
        r3_ops._write_json_exclusive(args.output, receipt)
        code = 2
    print(r3_ops._canonical_json(receipt))
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
