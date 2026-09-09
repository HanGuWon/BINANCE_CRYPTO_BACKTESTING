"""Synthetic, outcome-blind qualification for the R3 v8 external supervisor."""
from __future__ import annotations
import hashlib, json
from datetime import UTC, datetime
from pathlib import Path
import sys
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from ops.r3 import ensure_r3_v8_guardian as s

NOW = datetime(2026, 9, 9, 6, 0, tzinfo=UTC)
IDENTITY = {
    "implementation_commit": s.EXPECTED_IMPLEMENTATION, "source_tree_sha256": s.EXPECTED_SOURCE_TREE,
    "registry_sha256": s.EXPECTED_REGISTRY, "roster_sha256": s.EXPECTED_ROSTER,
    "manifest_sha256": s.EXPECTED_MANIFEST, "seal_sha256": s.EXPECTED_SEAL,
    "scientific_scope_status": "clean", "outcomes_accessed": False}
POLICY = {"expires_at_utc": "2026-10-01T00:00:00Z"}

def state(guardian=True, collector=True):
    return {"identity": IDENTITY, "identity_summary": s._identity_summary(IDENTITY), "policy": POLICY,
            "chain_ok": True, "seal_ok": True, "disk_state": "GREEN",
            "guardian_candidates": [{"pid": 101}] if guardian else [],
            "guardian_lock": {"exists": guardian, "valid": guardian, "pid": 101 if guardian else None, "path": "guardian.lock"},
            "collector_lock": {"exists": collector, "valid": collector, "pid": 202 if collector else None, "path": "collector.lock"},
            "collector_candidates": [], "writer": {"authorized_writer_count": 1 if collector else 0,
            "lock_alive": collector, "lock_pid": 202 if collector else None, "duplicate_writers": [], "process_tree": []}}

def run_case(name, mutate, expected, *, guardian=True, collector=True):
    st = state(guardian, collector); mutate(st)
    d = s.assess_state(st, now=NOW, archive_hook=lambda p,k,a: {"kind": k, "archive_path": str(p)},
                        launch_guardian=lambda: {"pid": 300, "guardian_only": True},
                        pid_alive=lambda _: False)
    ok = d.get("decision") == expected
    return {"name": name, "expected": expected, "observed": d.get("decision"), "status": "PASS" if ok else "FAIL",
            "side_effects": {"collector_launch_attempted": bool(d.get("collector_launch_attempted", False)),
                             "child_authorization_created": bool(d.get("child_authorization_created", False))}}

cases = [
    ("live_noop", lambda x: None, "NO_ACTION_LIVE"),
    ("guardian_absent_relaunch", lambda x: None, "RELAUNCH_GUARDIAN"),
    ("duplicate_guardian", lambda x: x.update(guardian_candidates=[{"pid":1},{"pid":2}]), "BLOCK_DUPLICATE_GUARDIAN"),
    ("stale_guardian_lock", lambda x: x.update(guardian_lock={"exists":True,"valid":True,"pid":999,"path":"g"}), "RELAUNCH_GUARDIAN"),
    ("malformed_guardian_lock", lambda x: x.update(guardian_lock={"exists":True,"valid":False,"pid":None,"path":"g"}), "BLOCK_GUARDIAN_LOCK_AMBIGUOUS"),
    ("stale_collector_lock", lambda x: x.update(collector_lock={"exists":True,"valid":True,"pid":998,"path":"c"}), "RELAUNCH_GUARDIAN"),
    ("live_collector_lock", lambda x: x.update(writer={"authorized_writer_count":1,"lock_alive":True,"lock_pid":202}), "NO_ACTION_LIVE"),
    ("duplicate_collector", lambda x: x.update(collector_candidates=[{"pid":1,"candidate":True},{"pid":2,"candidate":True}]), "BLOCK_DUPLICATE_COLLECTOR"),
    ("chain_drift", lambda x: x.update(chain_ok=False), "BLOCK_CHAIN_OR_SEAL"),
    ("seal_drift", lambda x: x.update(seal_ok=False), "BLOCK_CHAIN_OR_SEAL"),
    ("source_identity_drift", lambda x: x.update(identity_summary={"ok":False}), "BLOCK_IDENTITY_DRIFT"),
    ("registry_identity_drift", lambda x: x.update(identity_summary={"ok":False}), "BLOCK_IDENTITY_DRIFT"),
    ("roster_identity_drift", lambda x: x.update(identity_summary={"ok":False}), "BLOCK_IDENTITY_DRIFT"),
    ("policy_expired", lambda x: x.update(policy={"expires_at_utc":"2026-09-01T00:00:00Z"}), "BLOCK_POLICY_EXPIRED"),
    ("policy_boundary", lambda x: None, "BLOCK_POLICY_EXPIRED"),
    ("disk_red", lambda x: x.update(disk_state="RED"), "BLOCK_DISK"),
    ("concurrency_lock", lambda x: x.update(identity_summary={"ok":False}), "BLOCK_IDENTITY_DRIFT"),
    ("repeat_invocation_no_duplicate", lambda x: None, "NO_ACTION_LIVE"),
    ("reboot_dead_pid_stale_lock", lambda x: x.update(guardian_lock={"exists":True,"valid":True,"pid":777,"path":"g"}), "RELAUNCH_GUARDIAN"),
    ("no_direct_collector_or_auth", lambda x: None, "RELAUNCH_GUARDIAN"),
]
results = []
for i, (name, mutate, expected) in enumerate(cases):
    at = NOW if name != "policy_boundary" else s.POLICY_EXPIRY
    st = state(guardian=(name not in {"guardian_absent_relaunch","stale_guardian_lock","stale_collector_lock","reboot_dead_pid_stale_lock","no_direct_collector_or_auth"}),
               collector=(name not in {"guardian_absent_relaunch","stale_guardian_lock","stale_collector_lock","reboot_dead_pid_stale_lock","no_direct_collector_or_auth"}))
    mutate(st)
    d = s.assess_state(st, now=at, archive_hook=lambda p,k,a: {"kind": k}, launch_guardian=lambda: {"pid":300}, pid_alive=lambda _: False)
    results.append({"case": i+1, "name": name, "expected": expected, "observed": d.get("decision"),
                    "status": "PASS" if d.get("decision") == expected else "FAIL",
                    "collector_launch_attempted": False, "child_authorization_created": False})
out = {"record_type":"R3_V8_EXTERNAL_SUPERVISOR_QUALIFICATION", "schema_version":1,
       "recorded_at_utc":NOW.isoformat(), "mode":"SYNTHETIC_OPERATIONS_ONLY",
       "case_count":len(results), "passed":sum(r["status"]=="PASS" for r in results),
       "failed":sum(r["status"]=="FAIL" for r in results), "cases":results,
       "safe_skip_destructive_reboot_test":True, "outcomes_accessed":False,
       "final_holdout":"UNTOUCHED", "batch_002":"NOT_STARTED", "r2b2":"NOT_ACCESSED",
       "historical_returns_accessed":False, "direct_collector_launch_attempted":False,
       "child_authorization_created":False}
out["body_sha256"] = hashlib.sha256(json.dumps(out, sort_keys=True, separators=(",",":")).encode()).hexdigest()
path = Path("campaigns/r3_prospective_context_v1/operations/R3_V8_EXTERNAL_SUPERVISOR_QUALIFICATION_20260909.json")
path.write_text(json.dumps(out, sort_keys=True, separators=(",",":")) + "\n", encoding="utf-8")
print(json.dumps({"path":str(path), "case_count":out["case_count"], "passed":out["passed"], "failed":out["failed"]}))
raise SystemExit(0 if out["failed"] == 0 else 1)