from datetime import UTC, datetime
from pathlib import Path
import pytest
from ops.r3 import ensure_r3_v8_guardian as supervisor

NOW = datetime(2026, 9, 9, 6, 0, tzinfo=UTC)
IDENTITY = {
    "implementation_commit": supervisor.EXPECTED_IMPLEMENTATION,
    "source_tree_sha256": supervisor.EXPECTED_SOURCE_TREE,
    "registry_sha256": supervisor.EXPECTED_REGISTRY,
    "roster_sha256": supervisor.EXPECTED_ROSTER,
    "manifest_sha256": supervisor.EXPECTED_MANIFEST,
    "seal_sha256": supervisor.EXPECTED_SEAL,
    "scientific_scope_status": "clean",
    "outcomes_accessed": False,
}
POLICY = {"expires_at_utc": "2026-10-01T00:00:00Z"}

def base_state(*, guardian=True, collector=True):
    return {
        "identity": IDENTITY, "identity_summary": supervisor._identity_summary(IDENTITY),
        "policy": POLICY, "chain_ok": True, "seal_ok": True, "disk_state": "GREEN",
        "guardian_candidates": [{"pid": 101}] if guardian else [],
        "guardian_lock": {"exists": guardian, "valid": guardian, "pid": 101 if guardian else None, "path": "guardian.lock"},
        "collector_lock": {"exists": collector, "valid": collector, "pid": 202 if collector else None, "path": "collector.lock"},
        "collector_candidates": [],
        "writer": {"authorized_writer_count": 1 if collector else 0, "lock_alive": collector, "lock_pid": 202 if collector else None, "duplicate_writers": [], "process_tree": []},
    }

def test_live_no_action():
    d = supervisor.assess_state(base_state(), now=NOW)
    assert d["decision"] == "NO_ACTION_LIVE"
    assert d["guardian_pid"] == 101 and d["collector_pid"] == 202

@pytest.mark.parametrize("mutator,expected", [
    (lambda s: s.update(identity_summary={"ok": False}), "BLOCK_IDENTITY_DRIFT"),
    (lambda s: s.update(policy_error="bad"), "BLOCK_POLICY_INVALID"),
    (lambda s: s.update(policy={"expires_at_utc": "2026-09-01T00:00:00Z"}), "BLOCK_POLICY_EXPIRED"),
    (lambda s: s.update(chain_ok=False), "BLOCK_CHAIN_OR_SEAL"),
    (lambda s: s.update(seal_ok=False), "BLOCK_CHAIN_OR_SEAL"),
    (lambda s: s.update(disk_state="RED"), "BLOCK_DISK"),
    (lambda s: s.update(guardian_candidates=[{"pid": 1}, {"pid": 2}]), "BLOCK_DUPLICATE_GUARDIAN"),
    (lambda s: s.update(collector_candidates=[{"pid": 1, "candidate": True}, {"pid": 2, "candidate": True}]), "BLOCK_DUPLICATE_COLLECTOR"),
    (lambda s: s.update(guardian_lock={"exists": True, "valid": False, "pid": None}), "BLOCK_GUARDIAN_LOCK_AMBIGUOUS"),
    (lambda s: s.update(writer={"authorized_writer_count": 1, "lock_alive": False, "lock_pid": 202}), "BLOCK_COLLECTOR_NOT_LIVE"),
])
def test_fail_closed_matrix(mutator, expected):
    s = base_state(); mutator(s)
    assert supervisor.assess_state(s, now=NOW, pid_alive=lambda _: True)["decision"] == expected

def test_relaunch_guardian_only_after_stale_locks():
    s = base_state(guardian=False, collector=False)
    s["guardian_lock"] = {"exists": True, "valid": True, "pid": 999, "path": "guardian.lock"}
    s["collector_lock"] = {"exists": True, "valid": True, "pid": 998, "path": "collector.lock"}
    archived = []
    d = supervisor.assess_state(s, now=NOW, archive_hook=lambda p,k,a: archived.append(k) or {"kind": k},
        launch_guardian=lambda: {"pid": 303, "guardian_only": True}, pid_alive=lambda _: False)
    assert d["decision"] == "RELAUNCH_GUARDIAN"
    assert archived == ["guardian", "collector"]
    assert d["collector_launch_attempted"] is False and d["child_authorization_created"] is False

def test_no_collector_direct_launch():
    s = base_state(guardian=False, collector=False); launched = []
    d = supervisor.assess_state(s, now=NOW, launch_guardian=lambda: launched.append(1) or {"pid": 304}, pid_alive=lambda _: False)
    assert d["decision"] == "RELAUNCH_GUARDIAN" and launched == [1]
    assert d["collector_launch_attempted"] is False

def test_live_guardian_lock_mismatch_blocks():
    s = base_state(); s["guardian_lock"]["pid"] = 999
    assert supervisor.assess_state(s, now=NOW)["decision"] == "BLOCK_GUARDIAN_LOCK_AMBIGUOUS"

def test_stale_lock_owner_candidate_blocks():
    with pytest.raises(supervisor.SupervisorBlocked) as exc:
        supervisor._prove_stale_and_archive({"exists": True, "valid": True, "pid": 999, "path": "x"},
            kind="guardian", candidates=[{"pid": 999}], now=NOW, archive_hook=lambda *a: {}, pid_alive=lambda _: False)
    assert exc.value.decision == "BLOCK_GUARDIAN_LOCK_ACTIVE"

def test_malformed_lock_blocks():
    s = base_state(guardian=False, collector=False)
    s["guardian_lock"] = {"exists": True, "valid": False, "pid": None, "path": "guardian.lock"}
    assert supervisor.assess_state(s, now=NOW, pid_alive=lambda _: False)["decision"] == "BLOCK_GUARDIAN_LOCK_AMBIGUOUS"

def test_supervisor_lock_collision(tmp_path: Path):
    path = tmp_path / "supervisor.lock"
    with supervisor.supervisor_lock(path):
        with pytest.raises(supervisor.SupervisorBlocked) as exc:
            with supervisor.supervisor_lock(path): pass
        assert exc.value.decision == "BLOCK_SUPERVISOR_LOCK_COLLISION"

def test_expiry_boundary_is_blocked():
    assert supervisor.assess_state(base_state(), now=supervisor.POLICY_EXPIRY)["decision"] == "BLOCK_POLICY_EXPIRED"

def test_candidate_census_exposed(monkeypatch):
    rows = [{"pid": 202, "parent_pid": 0, "name": "python.exe", "executable": "python.exe",
             "command_line": "python run_r3_prospective_collector.py --mode SCIENTIFIC --persistent " + str(supervisor.V8_ROOT) + " " + str(supervisor.V8_ROSTER) + " " + str(supervisor.V8_MANIFEST) + " scientific_raw_v8 2026-09.json r3_prospective_launch_manifest_2026-09.json",
             "create_time": None}]
    monkeypatch.setattr(supervisor.r3_ops, "_process_snapshot", lambda: rows)
    monkeypatch.setattr(supervisor.r3_ops, "verify_identity", lambda require_exact_v8=True: IDENTITY)
    monkeypatch.setattr(supervisor.r3_v8_authorization, "load_standing_policy", lambda now=None: POLICY)
    monkeypatch.setattr(supervisor.r3_ops, "watchdog_snapshot", lambda *a, **k: {
        "writer": {"authorized_writer_count": 1, "lock_alive": True, "lock_pid": 202, "process_tree": []},
        "manifest_chain_verification": True, "launch_seal_verification": True, "storage": {"disk_state": "GREEN"}})
    s = supervisor.collect_state(now=NOW)
    assert len(s["collector_candidates"]) == 1 and s["collector_candidates"][0]["candidate"] is True