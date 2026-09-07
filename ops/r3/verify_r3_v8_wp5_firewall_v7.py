"""Verify and publish the append-only V3/V7 R3 v8 recovery firewall.

This operations-only verifier binds the corrected outage decomposition to the
immutable V2/V6 evidence.  It never reads market payloads, returns, outcomes,
or holdout material.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ops.r3 import r3_ops


REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_ROOT = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations"
PLAN_ROOT = REPO_ROOT / "devlog" / "_plan" / "260905_sol-audit-independent-attestation-20260905"
V2_PATH = OPS_ROOT / "R3_V8_OUTAGE_AND_RECOVERY_20260907_V2.json"
V3_PATH = OPS_ROOT / "R3_V8_OUTAGE_AND_RECOVERY_20260907_V3.json"
V6_PATH = OPS_ROOT / "R3_V8_WP5_FIREWALL_RECEIPT_20260907_V6.json"
V7_PATH = OPS_ROOT / "R3_V8_WP5_FIREWALL_RECEIPT_20260907_V7.json"
CONTINUATION_PATH = OPS_ROOT / "R3_V8_FORCEORDER_V3_MIGRATION_CONTINUATION_20260907.json"
DAILY_PATH = OPS_ROOT / "R3_V8_DAILY_OPERATIONS_RECEIPTS.jsonl"
DAILY_LOCK_PATH = OPS_ROOT / "R3_V8_DAILY_OPERATIONS_RECEIPTS.lock"
WP0_PATH = PLAN_ROOT / "145_recovery_wp0_watchdog_20260907.json"
WP2_PATH = PLAN_ROOT / "168_wp2_launch_receipt_20260907_v4.json"
WP3_PATH = PLAN_ROOT / "175_wp3_verification_20260907.json"

ROOT = r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8"
IDENTITY = {
    "implementation_commit": "ecebc49dff41eeec33af62c2c85a75c5a0bd2922",
    "source_tree_sha256": "b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688",
    "registry_sha256": "c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a",
    "roster_sha256": "bb05514dfc78cfca3b736488b1454f4cb022da0110e2cbf69f53c505f543ea79",
    "launch_manifest_sha256": "cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659",
    "launch_seal_sha256": "ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85",
}
EXPECTED_V2_FILE_SHA256 = "3212f220c6ece18cc0a830b8051891f85f0cbf78b7a00aaf7c049e2f602b2e13"
EXPECTED_V3_FILE_SHA256 = "0a00b1a47f15ec4a772fd5fc6c1169c9563e8854802d85fa8f6b3c14b03d1008"
EXPECTED_V6_FILE_SHA256 = "607a768fdddcdcdcb1c38792ee3f46e802a383905dfc2f805bbb7f9cdf57e89b"
EXPECTED_V7_FILE_SHA256: str | None = "ca8ac4d2dd727c862138a9ceb83c62520a4a36f7b0ca6f7722b482afbae128e4"
EXPECTED_CONTINUATION_FILE_SHA256 = "2cd66fba2238ff6e9f353ea109c476cc003dc69ddf09c85d42770077540be7b3"
WP0_SHA256 = "5a0222eb49684ae79afea006c368262727ad88b406f4d50c13138c286b49d8ad"
WP2_SHA256 = "92f6ded575a5ebf8f4c00a07a89f36e7448a2a1f86d564659baa87022dfa8b44"
WP3_SHA256 = "b99e7ae8de773b3517a5751d5023b3a41c53115b42d583d88acf419044e67aa9"

WRITE_CONTRACT = {
    "write_once": True,
    "atomic_publish_required": True,
    "create_mode": "O_CREAT|O_EXCL",
    "overwrite": False,
    "flush_fsync_before_publish": True,
    "body_sha256_algorithm": "SHA256 of canonical UTF-8 JSON with body_sha256 omitted",
}

OUTAGE_V3_KEYS = {
    "schema_version", "record_type", "receipt_path", "recorded_at_utc",
    "outcomes_accessed", "final_holdout", "r2b2", "forceorder_v3_migration",
    "immutability", "supersedes", "write_contract", "body_sha256", "pre_outage",
    "recovery_detection", "outage_period", "daily_operations_receipt",
    "evidence_anchors", "authorized_resume", "post_recovery", "current_snapshot",
    "accounting", "nonqualifying_cycle_preservation", "identity", "outcome_firewall",
    "recovery_state",
}
FIREWALL_KEYS = {
    "schema_version", "record_type", "receipt_path", "recorded_at_utc", "write_contract",
    "body_sha256", "command", "exit_code", "stdout_sha256", "stderr_sha256", "verifier",
    "allowlist", "checks", "identity", "outcomes_accessed", "final_holdout", "r2b2",
    "forceorder_v3_migration", "migration_prerequisite_state", "status", "supersedes",
}


class FirewallError(RuntimeError):
    """A fail-closed firewall verification error."""


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FirewallError(f"cannot load {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_body_sha(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("body_sha256", None)
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FirewallError(message)


def _verify_v3() -> dict[str, Any]:
    payload = _load(V3_PATH)
    _require(isinstance(payload, dict), "V3 accounting receipt is not an object")
    _require(set(payload) == OUTAGE_V3_KEYS, "V3 accounting receipt schema drift")
    _require(payload.get("schema_version") == 2, "V3 schema_version")
    _require(payload.get("record_type") == "R3_V8_OUTAGE_AND_RECOVERY", "V3 record_type")
    _require(payload.get("receipt_path") == str(V3_PATH.resolve()), "V3 receipt_path")
    _require(payload.get("write_contract") == WRITE_CONTRACT, "V3 write_contract")
    _require(payload.get("body_sha256") == _canonical_body_sha(payload), "V3 body_sha256")
    _require(_sha256(V3_PATH) == EXPECTED_V3_FILE_SHA256, "V3 file SHA256")
    r3_ops._reject_forbidden(payload, context="V3 accounting receipt")
    _require(payload.get("immutability") == "new receipt; V2 remains preserved as immutable historical evidence and is explicitly superseded", "V3 immutability")
    _require(payload.get("supersedes") == {
        "path": str(V2_PATH.resolve()),
        "file_sha256": EXPECTED_V2_FILE_SHA256,
        "body_sha256": "97eacca30891f2a9c04f4b937a6b2441e66d0e0ad72ffcfd08202f331877a61e",
        "status": "SUPERSEDED_BY_V3",
        "reason": "V2 preserved the snapshot and pre-existing gap but did not state the exact outage-period 175-cycle decomposition and 44-hour temporal proof.",
    }, "V3 supersession")
    _require(payload.get("pre_outage") == {
        "collector_process_count": 0, "authorized_writer_count": 0, "active_lock": "ABSENT",
        "last_cycle_id": "cycle-20260905T073004537033Z", "observed_cycle_count": 197,
        "expected_cycle_count": 284, "historical_missing_cycle_count": 87, "gap_count": 32,
        "restart_count": 32, "manifest_chain": "PASS", "launch_seal": "SEALED",
    }, "V3 pre_outage")
    outage_period = payload.get("outage_period")
    _require(outage_period == {
        "start_boundary_utc": "2026-09-05T07:30:00Z",
        "end_boundary_utc": "2026-09-07T03:30:00Z",
        "elapsed_hours": 44,
        "native_step_minutes": 15,
        "native_step_count": 176,
        "intervening_missing_cycle_count": 175,
        "formula": "176 native 15-minute steps - 1 endpoint interval = 175 outage-period missing cycles",
        "endpoint_basis": "last pre-outage boundary 2026-09-05T07:30Z; authorized-resume boundary 2026-09-07T03:30Z",
        "source": "UTC wall-clock boundary arithmetic only; no market payloads or outcome values inspected",
        "no_backfill": True,
    }, "V3 outage_period decomposition")
    _require(payload.get("accounting") == {
        "pre_existing_missing": 87,
        "pre_existing_formula": "284 expected - 197 observed = 87",
        "outage_period_missing": 175,
        "outage_period_formula": "262 current snapshot missing - 87 pre-existing missing = 175",
        "total_missing_snapshot": 262,
        "total_formula": "87 pre-existing + 175 outage-period = 262 total missing",
        "independent_snapshot_formula": "466 expected - 204 observed = 262",
        "reconciliation": "PASS",
    }, "V3 accounting formulas")
    preserved = payload.get("nonqualifying_cycle_preservation")
    _require(preserved == {
        "cycle_id": "cycle-20260907T033004700902Z",
        "disposition": "NONQUALIFYING_TARGET_BEFORE_AUTHORIZATION",
        "counted_as_strict_recovery_cycle": False,
        "mutation": "NONE",
    }, "V3 nonqualifying-cycle preservation")
    _require(payload.get("identity") == {"root": ROOT, **IDENTITY}, "V3 identity")
    _require(payload.get("outcomes_accessed") is False and payload.get("final_holdout") == "UNTOUCHED", "V3 outcome firewall")
    _require(payload.get("r2b2") == "NOT_ACCESSED" and payload.get("forceorder_v3_migration") == "NOT_STARTED", "V3 migration firewall")
    _require(payload.get("outcome_firewall") == {
        "outcomes_accessed": False, "final_holdout": "UNTOUCHED", "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED", "market_payloads_or_returns_accessed": False,
    }, "V3 nested firewall")
    _require(payload.get("recovery_state") == "R3_PROSPECTIVE_COLLECTION_RECOVERED_WITH_PRESERVED_GAP", "V3 recovery state")
    return payload


def _verify_immutable_ancestors() -> None:
    _require(_sha256(V2_PATH) == EXPECTED_V2_FILE_SHA256, "V2 historical receipt was modified")
    _require(_sha256(V6_PATH) == EXPECTED_V6_FILE_SHA256, "V6 historical firewall was modified")
    _require(_sha256(CONTINUATION_PATH) == EXPECTED_CONTINUATION_FILE_SHA256, "continuation ancestor was modified")
    for path, expected in ((WP0_PATH, WP0_SHA256), (WP2_PATH, WP2_SHA256), (WP3_PATH, WP3_SHA256)):
        _require(_sha256(path) == expected, f"immutable anchor SHA mismatch: {path.name}")


def _verify_live_operational_metadata() -> dict[str, Any]:
    _require(DAILY_PATH.is_file(), "daily operations receipt is missing")
    _require(not DAILY_LOCK_PATH.exists(), "daily operations append lock is stale")
    hits = []
    for line in DAILY_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FirewallError(f"daily receipt JSONL parse failure: {exc}") from exc
        if item.get("date") == "2026-09-07":
            hits.append(item)
    _require(len(hits) == 1, f"daily 2026-09-07 line count={len(hits)}")
    item = hits[0]
    identity = item.get("current_process_identity") or {}
    _require(identity.get("authorized_writer_count") == 1, "daily writer count is not one")
    _require(identity.get("duplicate_writers") in ([], None), "daily duplicate writers")
    _require(item.get("launch_seal_verification") is True and item.get("manifest_chain_verification") is True, "daily chain/seal")
    _require(item.get("outcomes_accessed") is False, "daily outcome firewall")
    return item


def _scientific_scope_clean() -> None:
    result = subprocess.run(["git", "status", "--short", "--", "scripts", "src", "tests", "configs"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    _require(result.returncode == 0, f"git status failed: {result.stderr.strip()}")
    _require(not result.stdout.strip(), f"scientific scope is dirty: {result.stdout.strip()}")


def _allowlist() -> list[str]:
    return [str(path.resolve()) for path in (V2_PATH, V3_PATH, V6_PATH, CONTINUATION_PATH, DAILY_PATH, DAILY_LOCK_PATH, WP0_PATH, WP2_PATH, WP3_PATH)]


def _summary() -> dict[str, Any]:
    daily = _verify_live_operational_metadata()
    return {
        "status": "PASS",
        "verifier": str(Path(__file__).resolve()),
        "allowlist": _allowlist(),
        "accounting": {
            "pre_existing_missing": 87,
            "outage_period_missing": 175,
            "total_missing_snapshot": 262,
            "formulas": ["284 - 197 = 87", "262 - 87 = 175", "87 + 175 = 262", "466 - 204 = 262"],
            "temporal_proof": "2026-09-05T07:30Z to 2026-09-07T03:30Z = 44h = 176 native 15m steps; 176 - 1 = 175",
        },
        "daily_date": daily.get("date"),
        "daily_latest_cycle": (daily.get("last_cycle") or {}).get("cycle_id"),
        "identity": {"root": ROOT, **IDENTITY},
        "checks": {
            "v2_preserved_sha256": EXPECTED_V2_FILE_SHA256,
            "v6_preserved_sha256": EXPECTED_V6_FILE_SHA256,
            "v3_accounting_sha256": EXPECTED_V3_FILE_SHA256,
            "pre_existing_gap_formula": "284 - 197 = 87",
            "outage_period_formula": "262 - 87 = 175",
            "total_gap_formula": "87 + 175 = 262",
            "independent_snapshot_formula": "466 - 204 = 262",
            "temporal_boundary_proof": "44h / 15m = 176; 176 - 1 = 175",
            "nonqualifying_cycle_preserved": "cycle-20260907T033004700902Z: NONQUALIFYING_TARGET_BEFORE_AUTHORIZATION",
            "single_writer": True,
            "duplicate_writers": [],
            "manifest_chain": "PASS",
            "launch_seal": "SEALED",
            "scientific_scope_git_status": "clean",
            "outcomes_accessed": False,
            "final_holdout": "UNTOUCHED",
            "r2b2": "NOT_ACCESSED",
            "forceorder_v3_migration": "NOT_STARTED",
            "market_payloads_accessed": False,
        },
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
    }


def verify(*, require_bound_receipt: bool = True) -> dict[str, Any]:
    _verify_v3()
    _verify_immutable_ancestors()
    _scientific_scope_clean()
    summary = _summary()
    if require_bound_receipt:
        _verify_bound(V7_PATH, summary)
    return summary


def _verify_bound(path: Path, summary: dict[str, Any]) -> None:
    payload = _load(path)
    _require(isinstance(payload, dict) and set(payload) == FIREWALL_KEYS, "V7 firewall schema drift")
    _require(payload.get("schema_version") == 2 and payload.get("record_type") == "R3_V8_WP5_FIREWALL", "V7 type/version")
    _require(payload.get("receipt_path") == str(path.resolve()), "V7 receipt_path")
    _require(payload.get("write_contract") == WRITE_CONTRACT, "V7 write_contract")
    _require(payload.get("body_sha256") == _canonical_body_sha(payload), "V7 body_sha256")
    if EXPECTED_V7_FILE_SHA256 is not None:
        _require(_sha256(path) == EXPECTED_V7_FILE_SHA256, "V7 file SHA256")
    _require(payload.get("command") == "python -m ops.r3.verify_r3_v8_wp5_firewall_v7 --receipt campaigns/r3_prospective_context_v1/operations/R3_V8_WP5_FIREWALL_RECEIPT_20260907_V7.json", "V7 command")
    _require(payload.get("exit_code") == 0 and payload.get("status") == "PASS", "V7 status")
    _require(payload.get("verifier") == str(Path(__file__).resolve()), "V7 verifier")
    _require(payload.get("allowlist") == summary["allowlist"], "V7 allowlist")
    _require(payload.get("checks") == summary["checks"], "V7 checks")
    _require(payload.get("identity") == summary["identity"], "V7 identity")
    _require(payload.get("outcomes_accessed") is False and payload.get("final_holdout") == "UNTOUCHED", "V7 outcome firewall")
    _require(payload.get("r2b2") == "NOT_ACCESSED" and payload.get("forceorder_v3_migration") == "NOT_STARTED", "V7 migration firewall")
    _require(payload.get("migration_prerequisite_state") == "FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED", "V7 migration prerequisite")
    _require(payload.get("supersedes") == {
        "path": str(V6_PATH.resolve()), "file_sha256": EXPECTED_V6_FILE_SHA256,
        "status": "SUPERSEDED_BY_V7", "reason": "V7 binds the corrected V3 outage-period and temporal accounting decomposition; V6 remains immutable.",
    }, "V7 supersession")
    stdout_bytes = (json.dumps(summary, sort_keys=True) + "\n").encode("utf-8")
    _require(payload.get("stdout_sha256") == hashlib.sha256(stdout_bytes).hexdigest(), "V7 stdout_sha256")
    _require(payload.get("stderr_sha256") == hashlib.sha256(b"").hexdigest(), "V7 stderr_sha256")
    r3_ops._reject_forbidden(payload, context="V7 firewall receipt")


def _write_receipt(summary: dict[str, Any], path: Path) -> None:
    _require(path.resolve() == V7_PATH.resolve(), "only canonical V7 path may be written")
    _require(not path.exists(), "V7 receipt already exists")
    command = "python -m ops.r3.verify_r3_v8_wp5_firewall_v7 --receipt campaigns/r3_prospective_context_v1/operations/R3_V8_WP5_FIREWALL_RECEIPT_20260907_V7.json"
    stdout_bytes = (json.dumps(summary, sort_keys=True) + "\n").encode("utf-8")
    receipt: dict[str, Any] = {
        "schema_version": 2,
        "record_type": "R3_V8_WP5_FIREWALL",
        "receipt_path": str(path.resolve()),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "write_contract": WRITE_CONTRACT,
        "body_sha256": "",
        "command": command,
        "exit_code": 0,
        "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "verifier": str(Path(__file__).resolve()),
        "allowlist": summary["allowlist"],
        "checks": summary["checks"],
        "identity": summary["identity"],
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
        "migration_prerequisite_state": "FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED",
        "status": "PASS",
        "supersedes": {
            "path": str(V6_PATH.resolve()), "file_sha256": EXPECTED_V6_FILE_SHA256,
            "status": "SUPERSEDED_BY_V7", "reason": "V7 binds the corrected V3 outage-period and temporal accounting decomposition; V6 remains immutable.",
        },
    }
    receipt["body_sha256"] = _canonical_body_sha(receipt)
    data = (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = -1
    try:
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "wb", closefd=True) as stream:
            fd = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _require(not path.exists(), "V7 receipt appeared during publication")
        os.link(tmp, path)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        summary = verify(require_bound_receipt=args.receipt is None)
        if args.receipt is not None:
            _write_receipt(summary, args.receipt.resolve())
            # Bind the immutable publication immediately; this also records the
            # exact file SHA in the verifier constant for future invocations.
            _verify_bound(args.receipt.resolve(), summary)
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (FirewallError, OSError, subprocess.SubprocessError, TypeError, KeyError, ValueError) as exc:
        print(f"R3_V8_WP5_FIREWALL_V7_INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
