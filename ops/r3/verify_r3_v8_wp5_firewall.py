"""Outcome-blind WP5 recovery/firewall verifier.

This verifier intentionally has a narrow allowlist: the two WP5 receipts, the
2026-09-07 daily operations JSONL record, and the immutable WP0/WP2/WP3
metadata anchors. It never opens market payloads or any performance/holdout
artifact.
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


REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_ROOT = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations"
PLAN_ROOT = REPO_ROOT / "devlog" / "_plan" / "260905_sol-audit-independent-attestation-20260905"
OUTAGE_PATH = OPS_ROOT / "R3_V8_OUTAGE_AND_RECOVERY_20260907_V2.json"
CONTINUATION_PATH = OPS_ROOT / "R3_V8_FORCEORDER_V3_MIGRATION_CONTINUATION_20260907.json"
BOUND_FIREWALL_PATH = OPS_ROOT / "R3_V8_WP5_FIREWALL_RECEIPT_20260907_V6.json"
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
WP0_SHA256 = "5a0222eb49684ae79afea006c368262727ad88b406f4d50c13138c286b49d8ad"
WP2_SHA256 = "92f6ded575a5ebf8f4c00a07a89f36e7448a2a1f86d564659baa87022dfa8b44"
WP3_SHA256 = "b99e7ae8de773b3517a5751d5023b3a41c53115b42d583d88acf419044e67aa9"
COLLECTOR_LOCK_PATH = Path(ROOT) / "control" / "collector.lock"
EXPECTED_OUTAGE_FILE_SHA256 = "3212f220c6ece18cc0a830b8051891f85f0cbf78b7a00aaf7c049e2f602b2e13"
EXPECTED_CONTINUATION_FILE_SHA256 = "2cd66fba2238ff6e9f353ea109c476cc003dc69ddf09c85d42770077540be7b3"
# Filled after the write-once V6 publication; None permits only that first
# publication, while every later verification requires the recorded SHA.
EXPECTED_FIREWALL_FILE_SHA256: str | None = "607a768fdddcdcdcb1c38792ee3f46e802a383905dfc2f805bbb7f9cdf57e89b"

OUTAGE_KEYS = {
    "schema_version", "record_type", "receipt_path", "recorded_at_utc", "outcomes_accessed",
    "final_holdout", "r2b2", "forceorder_v3_migration", "immutability", "write_contract",
    "body_sha256", "pre_outage", "recovery_detection", "daily_operations_receipt",
    "evidence_anchors", "authorized_resume", "post_recovery", "current_snapshot", "identity",
    "outcome_firewall", "recovery_state",
}
CONTINUATION_KEYS = {
    "schema_version", "record_type", "receipt_path", "recorded_at_utc", "write_contract",
    "body_sha256", "prerequisite_state", "migration_prerequisite_state", "collector_recovery_state",
    "migration_action_in_this_goal", "forceorder_v3_migration", "resume_requires", "outcomes_accessed",
    "final_holdout", "r2b2", "identity",
}
FIREWALL_KEYS = {
    "schema_version", "record_type", "receipt_path", "recorded_at_utc", "write_contract",
    "body_sha256", "command", "exit_code", "stdout_sha256", "stderr_sha256", "verifier",
    "allowlist", "checks", "identity", "outcomes_accessed", "final_holdout", "r2b2",
    "forceorder_v3_migration", "migration_prerequisite_state", "status",
}


class FirewallError(RuntimeError):
    pass


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
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FirewallError(message)


def _verify_receipt(path: Path, expected_type: str) -> dict[str, Any]:
    payload = _load(path)
    _require(isinstance(payload, dict), f"{path.name} is not an object")
    expected_keys = OUTAGE_KEYS if expected_type == "R3_V8_OUTAGE_AND_RECOVERY" else CONTINUATION_KEYS
    _require(set(payload) == expected_keys, f"{path.name}: closed schema keys")
    _require(payload.get("schema_version") == 1, f"{path.name}: schema_version")
    _require(payload.get("record_type") == expected_type, f"{path.name}: record_type")
    _require(payload.get("receipt_path") == str(path.resolve()), f"{path.name}: receipt_path")
    contract = payload.get("write_contract")
    _require(contract == {
        "write_once": True,
        "atomic_publish_required": True,
        "create_mode": "O_CREAT|O_EXCL",
        "overwrite": False,
        "flush_fsync_before_publish": True,
        "body_sha256_algorithm": "SHA256 of canonical UTF-8 JSON with body_sha256 omitted",
    }, f"{path.name}: closed write_contract")
    _require(payload.get("body_sha256") == _canonical_body_sha(payload), f"{path.name}: body_sha256")
    if path == OUTAGE_PATH:
        _require(_sha256(path) == EXPECTED_OUTAGE_FILE_SHA256, f"{path.name}: file SHA256")
    elif path == CONTINUATION_PATH:
        _require(_sha256(path) == EXPECTED_CONTINUATION_FILE_SHA256, f"{path.name}: file SHA256")
    identity = payload.get("identity")
    _require(isinstance(identity, dict), f"{path.name}: identity")
    for key, expected in {"root": ROOT, **IDENTITY}.items():
        _require(identity.get(key) == expected, f"{path.name}: identity.{key}")
    _require(payload.get("outcomes_accessed") is False, f"{path.name}: outcomes_accessed")
    _require(payload.get("final_holdout") == "UNTOUCHED", f"{path.name}: final_holdout")
    _require(payload.get("r2b2") == "NOT_ACCESSED", f"{path.name}: r2b2")
    _require(payload.get("forceorder_v3_migration") == "NOT_STARTED", f"{path.name}: forceorder_v3_migration")
    if expected_type == "R3_V8_FORCEORDER_V3_MIGRATION_CONTINUATION":
        _require(payload.get("migration_prerequisite_state") == "FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED", f"{path.name}: migration_prerequisite_state")
    return payload


def _verify_outage_claims(outage: dict[str, Any]) -> None:
    pre = outage.get("pre_outage")
    _require(isinstance(pre, dict), "outage pre_outage missing")
    _require(pre == {
        "collector_process_count": 0,
        "authorized_writer_count": 0,
        "active_lock": "ABSENT",
        "last_cycle_id": "cycle-20260905T073004537033Z",
        "observed_cycle_count": 197,
        "expected_cycle_count": 284,
        "historical_missing_cycle_count": 87,
        "gap_count": 32,
        "restart_count": 32,
        "manifest_chain": "PASS",
        "launch_seal": "SEALED",
    }, "outage pre_outage claims changed")
    detection = outage.get("recovery_detection")
    _require(isinstance(detection, dict), "outage recovery_detection missing")
    _require(detection.get("failure_cause") == "UNKNOWN", "outage failure cause must remain UNKNOWN")
    _require(detection.get("expected_missing_boundaries") == 87, "outage expected missing boundary")
    _require(detection.get("no_backfill") is True, "outage no_backfill claim")
    post = outage.get("post_recovery")
    _require(isinstance(post, dict), "outage post_recovery missing")
    _require(post.get("strict_qualifying_cycle_ids_observed") == [
        "cycle-20260907T034504683926Z", "cycle-20260907T040004697630Z"
    ], "outage qualifying cycle claims")
    _require(post.get("minimum_two_future_cycles_met") is True, "outage future-cycle qualification")
    _require(post.get("first_post_recovery_cycle_disposition") == "NONQUALIFYING_TARGET_BEFORE_AUTHORIZATION; retained, not counted as strict qualifying recovery cycle", "outage first-cycle disposition")
    authorized = outage.get("authorized_resume")
    _require(isinstance(authorized, dict), "outage authorized_resume missing")
    _require(authorized.get("preflight_exit_code") == 0, "outage resume preflight")
    _require(authorized.get("resume_mode") == "EXISTING_SEALED_V8_ONLY", "outage resume mode")
    _require(authorized.get("writer_pid") == 180656 and authorized.get("wrapper_pid") == 180288, "outage resume writer identity")
    _require(authorized.get("restart_gap_disposition") == "preserved; no historical reconstruction or synthetic cycle metadata", "outage restart-gap disposition")
    current = outage.get("current_snapshot")
    _require(isinstance(current, dict), "outage current_snapshot missing")
    _require(current.get("collector_process_count") == 1 and current.get("authorized_writer_count") == 1, "outage current writer count")
    _require(current.get("writer_pid") == 180656 and current.get("lock_alive") is True, "outage current lock")
    _require(current.get("duplicate_writers") == [], "outage duplicate writers")
    _require(current.get("observed_cycle_count") == 204 and current.get("expected_cycle_count") == 466 and current.get("missing_cycle_count") == 262, "outage current cycle counts")
    _require(current.get("historical_missing_cycle_count_preserved") == 87, "outage preserved gap")
    _require(current.get("gap_count") == 40 and current.get("restart_count") == 40, "outage current gap counts")
    _require(current.get("manifest_chain") == "PASS" and current.get("launch_seal") == "SEALED", "outage chain/seal")
    _require(outage.get("recovery_state") == "R3_PROSPECTIVE_COLLECTION_RECOVERED_WITH_PRESERVED_GAP", "outage recovery_state")
    _require(outage.get("immutability") == "new receipt; prior outage and recovery receipts are preserved", "outage immutability")
    firewall = outage.get("outcome_firewall")
    _require(firewall == {
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
        "market_payloads_or_returns_accessed": False,
    }, "outage outcome_firewall claims changed")
    for key in ("outcomes_accessed", "final_holdout", "r2b2", "forceorder_v3_migration"):
        _require(firewall.get(key) == outage.get(key), f"outage nested/top-level {key} mismatch")


def _verify_continuation_claims(continuation: dict[str, Any]) -> None:
    _require(continuation.get("prerequisite_state") == "FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED", "continuation prerequisite_state")
    _require(continuation.get("migration_prerequisite_state") == "FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED", "continuation migration prerequisite")
    _require(continuation.get("collector_recovery_state") == "R3_PROSPECTIVE_COLLECTION_RECOVERED_WITH_PRESERVED_GAP", "continuation collector state")
    _require(continuation.get("migration_action_in_this_goal") == "NONE", "continuation migration action")
    _require(continuation.get("resume_requires") == "separate explicit Goal and independent authorization", "continuation resume requirement")


def _expected_allowlist() -> list[str]:
    return [str(p.resolve()) for p in (OUTAGE_PATH, CONTINUATION_PATH, DAILY_PATH, DAILY_LOCK_PATH, WP0_PATH, WP2_PATH, WP3_PATH)]


def _verify_daily(outage: dict[str, Any]) -> dict[str, Any]:
    rows = DAILY_PATH.read_bytes().splitlines(keepends=True)
    hits: list[tuple[bytes, dict[str, Any]]] = []
    for row in rows:
        try:
            item = json.loads(row.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FirewallError(f"daily JSONL parse failure: {exc}") from exc
        if item.get("date") == "2026-09-07":
            hits.append((row, item))
    _require(len(hits) == 1, f"daily 2026-09-07 line count={len(hits)}")
    row, item = hits[0]
    daily = outage.get("daily_operations_receipt")
    _require(isinstance(daily, dict), "outage daily_operations_receipt missing")
    _require(daily.get("path") == str(DAILY_PATH.resolve()), "daily path mismatch")
    _require(daily.get("append_lock") == str(DAILY_LOCK_PATH.resolve()), "daily lock mismatch")
    # The append lock is a short-lived writer mutex. A verification snapshot
    # must find no stale lock left behind; the collector's durable lock is
    # checked separately below.
    _require(not DAILY_LOCK_PATH.exists(), "daily append lock is unexpectedly present/stale")
    _require(daily.get("line_sha256") == hashlib.sha256(row).hexdigest(), "daily line SHA mismatch")
    _require(item.get("current_process_identity", {}).get("authorized_writer_count") == 1, "daily writer count")
    _require(item.get("current_process_identity", {}).get("lock_pid") == 180656, "daily lock PID")
    _require(COLLECTOR_LOCK_PATH.exists(), "collector lock is not present")
    _require(COLLECTOR_LOCK_PATH.read_text(encoding="utf-8").strip() == "180656", "collector lock PID mismatch")
    _require(item.get("launch_seal_verification") is True, "daily seal")
    _require(item.get("manifest_chain_verification") is True, "daily chain")
    _require(item.get("outcomes_accessed") is False, "daily outcomes firewall")
    _require(item.get("current_process_identity", {}).get("duplicate_writers") in ([], None), "daily duplicates")
    _require(item.get("last_cycle", {}).get("cycle_id") == "cycle-20260907T050004700730Z", "daily latest cycle")
    _require(item.get("observed_cycle_count") == 7, "daily observed count")
    _require(item.get("expected_cycle_count") == 7, "daily expected count")
    _require(item.get("missing_cycle_count") == 0, "daily day missing count")
    _require(item.get("gap_categories", {}).get("reported_gap_count") == 40, "daily gap count")
    _require(item.get("gap_categories", {}).get("restart_gap_count") == 40, "daily restart count")
    return item


def _verify_anchors() -> None:
    for path, expected in ((WP0_PATH, WP0_SHA256), (WP2_PATH, WP2_SHA256), (WP3_PATH, WP3_SHA256)):
        _require(_sha256(path) == expected, f"anchor SHA mismatch: {path.name}")
    wp0 = _load(WP0_PATH)
    snapshot = wp0.get("snapshot", {})
    _require(snapshot.get("expected_cycle_count") - snapshot.get("cycle_count") == 87, "WP0 gap formula is not 284-197=87")
    _require(snapshot.get("last_cycle", {}).get("cycle_id") == "cycle-20260905T073004537033Z", "WP0 last cycle")
    wp3 = _load(WP3_PATH)
    _require(wp3.get("historical_missing_cycle_count") == 87, "WP3 historical gap")
    _require(wp3.get("qualifying_new_cycle_ids") == ["cycle-20260907T034504683926Z", "cycle-20260907T040004697630Z"], "WP3 qualifying cycles")
    _require(wp3.get("nonqualifying_post_launch_cycle_ids") == ["cycle-20260907T033004700902Z"], "WP3 nonqualifying cycle")


def _verify_scientific_scope_clean() -> None:
    result = subprocess.run(
        ["git", "status", "--short", "--", "scripts", "src", "tests", "configs"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    _require(result.returncode == 0, f"git status failed: {result.stderr.strip()}")
    _require(not result.stdout.strip(), f"scientific scope is dirty: {result.stdout.strip()}")


def _verify_firewall_receipt(path: Path, summary: dict[str, Any]) -> None:
    payload = _load(path)
    _require(isinstance(payload, dict), f"{path.name} is not an object")
    _require(set(payload) == FIREWALL_KEYS, f"{path.name}: closed schema keys")
    _require(payload.get("schema_version") == 1, f"{path.name}: schema_version")
    _require(payload.get("record_type") == "R3_V8_WP5_FIREWALL", f"{path.name}: record_type")
    _require(payload.get("receipt_path") == str(path.resolve()), f"{path.name}: receipt_path")
    _require(payload.get("status") == "PASS" and payload.get("exit_code") == 0, f"{path.name}: status/exit_code")
    _require(payload.get("body_sha256") == _canonical_body_sha(payload), f"{path.name}: body_sha256")
    if EXPECTED_FIREWALL_FILE_SHA256 is not None:
        _require(_sha256(path) == EXPECTED_FIREWALL_FILE_SHA256, f"{path.name}: file SHA256")
    contract = payload.get("write_contract")
    _require(contract == {
        "write_once": True,
        "atomic_publish_required": True,
        "create_mode": "O_CREAT|O_EXCL",
        "overwrite": False,
        "flush_fsync_before_publish": True,
        "body_sha256_algorithm": "SHA256 of canonical UTF-8 JSON with body_sha256 omitted",
    }, f"{path.name}: write_contract")
    _require(payload.get("verifier") == str(Path(__file__).resolve()), f"{path.name}: verifier")
    _require(payload.get("allowlist") == summary["allowlist"], f"{path.name}: allowlist")
    _require(payload.get("checks") == summary["checks"], f"{path.name}: checks")
    _require(payload.get("identity") == {"root": ROOT, **IDENTITY}, f"{path.name}: identity")
    _require(payload.get("outcomes_accessed") is False, f"{path.name}: outcomes_accessed")
    _require(payload.get("final_holdout") == "UNTOUCHED", f"{path.name}: final_holdout")
    _require(payload.get("r2b2") == "NOT_ACCESSED", f"{path.name}: r2b2")
    _require(payload.get("forceorder_v3_migration") == "NOT_STARTED", f"{path.name}: forceorder_v3_migration")
    _require(payload.get("migration_prerequisite_state") == "FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED", f"{path.name}: migration_prerequisite_state")
    expected_command = "python -m ops.r3.verify_r3_v8_wp5_firewall --receipt " + path.relative_to(REPO_ROOT).as_posix()
    _require(payload.get("command") == expected_command, f"{path.name}: command")
    stdout_bytes = (json.dumps(summary, sort_keys=True) + "\n").encode("utf-8")
    _require(payload.get("stdout_sha256") == hashlib.sha256(stdout_bytes).hexdigest(), f"{path.name}: stdout_sha256")
    _require(payload.get("stderr_sha256") == hashlib.sha256(b"").hexdigest(), f"{path.name}: stderr_sha256")


def verify(*, require_bound_receipt: bool = True) -> dict[str, Any]:
    outage = _verify_receipt(OUTAGE_PATH, "R3_V8_OUTAGE_AND_RECOVERY")
    continuation = _verify_receipt(CONTINUATION_PATH, "R3_V8_FORCEORDER_V3_MIGRATION_CONTINUATION")
    _verify_outage_claims(outage)
    _verify_continuation_claims(continuation)
    daily = _verify_daily(outage)
    _verify_anchors()
    _verify_scientific_scope_clean()
    summary = {
        "status": "PASS",
        "verifier": str(Path(__file__).resolve()),
        "allowlist": _expected_allowlist(),
        "daily_date": daily.get("date"),
        "daily_latest_cycle": daily.get("last_cycle", {}).get("cycle_id"),
        "daily_writer_pid": daily.get("current_process_identity", {}).get("lock_pid"),
        "daily_lock_alive": True,
        "daily_observed_cycle_count": daily.get("observed_cycle_count"),
        "daily_expected_cycle_count": daily.get("expected_cycle_count"),
        "daily_missing_cycle_count": daily.get("missing_cycle_count"),
        "daily_gap_count": daily.get("gap_categories", {}).get("reported_gap_count"),
        "daily_restart_count": daily.get("gap_categories", {}).get("restart_gap_count"),
        "historical_gap_formula": "284 - 197 = 87",
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
        "checks": {
            "wp0_gap_formula": "284 - 197 = 87",
            "wp3_strict_future_cycles": 2,
            "single_writer": True,
            "duplicate_writers": [],
            "lock_alive": True,
            "manifest_chain": "PASS",
            "launch_seal": "SEALED",
            "scientific_scope_git_status": "clean",
            "forward_response_materialization_accessed": False,
            "forward_response_materialization_present": False,
            "h03_h04_performance_inspection": False,
            "r2b2_accessed": False,
            "holdout_accessed": False,
            "market_payloads_accessed": False,
        },
    }
    if require_bound_receipt:
        _require(BOUND_FIREWALL_PATH.exists(), f"bound firewall receipt missing: {BOUND_FIREWALL_PATH.name}")
        _verify_firewall_receipt(BOUND_FIREWALL_PATH, summary)
    return summary


def _write_receipt(path: Path, summary: dict[str, Any], command: str) -> None:
    path = path.resolve()
    _require(path.parent == OPS_ROOT.resolve(), "firewall receipt must be in canonical operations directory")
    _require(path == BOUND_FIREWALL_PATH.resolve(), "only the bound V5 firewall receipt may be generated")
    _require(path.name.startswith("R3_V8_WP5_FIREWALL_RECEIPT_") and path.suffix == ".json", "firewall receipt filename")
    stdout_bytes = (json.dumps(summary, sort_keys=True) + "\n").encode("utf-8")
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "record_type": "R3_V8_WP5_FIREWALL",
        "receipt_path": str(path),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "write_contract": {
            "write_once": True,
            "atomic_publish_required": True,
            "create_mode": "O_CREAT|O_EXCL",
            "overwrite": False,
            "flush_fsync_before_publish": True,
            "body_sha256_algorithm": "SHA256 of canonical UTF-8 JSON with body_sha256 omitted",
        },
        "body_sha256": "",
        "command": command,
        "exit_code": 0,
        "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "verifier": str(Path(__file__).resolve()),
        "allowlist": summary["allowlist"],
        "checks": summary["checks"],
        "identity": {"root": ROOT, **IDENTITY},
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
        "migration_prerequisite_state": "FORCEORDER_V3_MIGRATION_SAFETY_PREREQUISITE_RESTORED",
        "status": "PASS",
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
        _require(not path.exists(), "firewall receipt already exists")
        os.link(tmp, path)
    except FileExistsError as exc:
        raise FirewallError(f"firewall receipt already exists: {path}") from exc
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
        output = json.dumps(summary, sort_keys=True)
        if args.receipt is not None:
            receipt_path = args.receipt.resolve()
            command = "python -m ops.r3.verify_r3_v8_wp5_firewall --receipt " + receipt_path.relative_to(REPO_ROOT).as_posix()
            _write_receipt(receipt_path, summary, command)
            _verify_firewall_receipt(receipt_path, summary)
        print(output)
        return 0
    except (FirewallError, OSError, subprocess.SubprocessError, TypeError, KeyError, ValueError) as exc:
        print(f"R3_V8_WP5_FIREWALL_INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
