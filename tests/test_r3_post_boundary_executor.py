from datetime import UTC, datetime
import json
import uuid
from pathlib import Path

import pytest

from scripts.prepare_r3_post_boundary_launch import (
    BOUNDARY_UTC,
    CalibratedClock,
    PostBoundaryBlocked,
    execute_post_boundary,
    prepare_post_boundary_plan,
    require_fresh_scientific_root,
    rollover_state,
)


def test_post_boundary_plan_rejects_before_boundary(tmp_path: Path) -> None:
    with pytest.raises(PostBoundaryBlocked, match="R3_BLOCKED_SEPTEMBER_ROSTER"):
        prepare_post_boundary_plan(now=datetime(2026, 8, 31, 23, 59, tzinfo=UTC), scientific_root=tmp_path)


def test_post_boundary_plan_is_time_gated_and_plan_only(tmp_path: Path) -> None:
    root = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\_preboundary_executor_test_root")
    if root.exists() and any(root.iterdir()):
        pytest.skip("test root was left non-empty by an external run")
    plan = prepare_post_boundary_plan(now=BOUNDARY_UTC, scientific_root=root)
    assert plan["execute"] is False
    assert plan["outcomes"] == "NOT_STARTED"
    assert "build_september_liquidity_ranking" in plan["steps"]


def test_scientific_root_rejects_nonfresh_engineering_path(tmp_path: Path) -> None:
    root = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\engineering_shadow_august_v6_realtime")
    with pytest.raises(PostBoundaryBlocked, match="R3_BLOCKED_LAUNCH_IDENTITY"):
        require_fresh_scientific_root(root)


def test_scientific_root_requires_d_backing(tmp_path: Path) -> None:
    with pytest.raises(PostBoundaryBlocked, match="R3_BLOCKED_STORAGE"):
        require_fresh_scientific_root(tmp_path)


def test_blocked_launch_manifest_is_not_reused() -> None:
    manifest = json.loads(Path("campaigns/r3_prospective_context_v1/R3_LAUNCH_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] in {"R3_BLOCKED_FINAL_LAUNCH_CONFORMANCE", "R3_BLOCKED_ROSTER_PROVENANCE"}


def _droot(name: str) -> Path:
    return Path(rf"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\_{name}_{uuid.uuid4().hex}")


def _callbacks(calls: list[str]) -> dict[str, object]:
    stages = [
        "AUGUST_SOURCE_ACQUISITION", "AUGUST_SOURCE_VERIFICATION", "SEPTEMBER_RANKING",
        "SEPTEMBER_ROSTER_FREEZE", "SEPTEMBER_ROSTER_REPLAY", "SEPTEMBER_ENGINEERING_SHADOW",
        "LAUNCH_IDENTITY_FREEZE", "LAUNCH_MANIFEST_BUILD", "LAUNCH_SEAL", "SCIENTIFIC_ROOT_GATE", "SCIENTIFIC_ACTIVATION",
    ]
    return {stage: (lambda _ctx, stage=stage: calls.append(stage) or {"proof": stage, "evidence_mode": "ENGINEERING_SHADOW" if stage == "SEPTEMBER_ENGINEERING_SHADOW" else "CONTROL"}) for stage in stages}


def test_preboundary_executor_writes_no_receipt_and_invokes_no_callback() -> None:
    calls: list[str] = []
    receipt_root = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\_preboundary_no_action")
    with pytest.raises(PostBoundaryBlocked, match="R3_BLOCKED_SEPTEMBER_ROSTER"):
        execute_post_boundary(clock=CalibratedClock(datetime(2026, 8, 31, 23, 59, tzinfo=UTC), 1), scientific_root=_droot("preboundary_no_action"), receipt_root=receipt_root, callbacks=_callbacks(calls))
    assert calls == []
    assert not receipt_root.exists()


def test_uncertain_clock_blocks_before_any_stage() -> None:
    with pytest.raises(PostBoundaryBlocked, match="R3_BLOCKED_CLOCK_CAUSALITY"):
        execute_post_boundary(clock=CalibratedClock(BOUNDARY_UTC, 2000.1), scientific_root=_droot("uncertain"))


@pytest.mark.parametrize(
    ("stage", "code"),
    [("AUGUST_SOURCE_ACQUISITION", "R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE"),
     ("AUGUST_SOURCE_VERIFICATION", "R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE"),
     ("SEPTEMBER_RANKING", "R3_BLOCKED_SEPTEMBER_RANKING"),
     ("SEPTEMBER_ROSTER_REPLAY", "R3_BLOCKED_SEPTEMBER_ROSTER"),
     ("SEPTEMBER_ENGINEERING_SHADOW", "R3_BLOCKED_SEPTEMBER_SHADOW"),
     ("LAUNCH_IDENTITY_FREEZE", "R3_BLOCKED_LAUNCH_IDENTITY"),
     ("LAUNCH_SEAL", "R3_BLOCKED_LAUNCH_IDENTITY")],
)
def test_stage_failures_are_explicit_and_fail_closed(stage: str, code: str) -> None:
    callbacks = _callbacks([])
    callbacks[stage] = lambda _ctx: (_ for _ in ()).throw(PostBoundaryBlocked(code, "synthetic failure"))
    with pytest.raises(PostBoundaryBlocked, match=code):
        execute_post_boundary(clock=CalibratedClock(BOUNDARY_UTC, 1), scientific_root=_droot("stage_" + stage.lower()), callbacks=callbacks)


def test_success_is_ordered_idempotent_and_activation_follows_seal() -> None:
    calls: list[str] = []
    root, receipts = _droot("success"), _droot("success_receipts")
    callbacks = _callbacks(calls)
    first = execute_post_boundary(clock=CalibratedClock(BOUNDARY_UTC, 1), scientific_root=root, receipt_root=receipts, callbacks=callbacks)
    assert first["status"] == "R3_READY_FOR_PROSPECTIVE_LAUNCH"
    assert calls[-1] == "SCIENTIFIC_ACTIVATION"
    assert calls.index("LAUNCH_IDENTITY_FREEZE") < calls.index("LAUNCH_SEAL") < calls.index("SCIENTIFIC_ACTIVATION")
    calls.clear()
    second = execute_post_boundary(clock=CalibratedClock(BOUNDARY_UTC, 1), scientific_root=root, receipt_root=receipts, callbacks=callbacks)
    assert second["status"] == first["status"]
    assert calls == []


def test_conflicting_receipt_and_nonfresh_root_block() -> None:
    root, receipts = _droot("conflict"), _droot("conflict_receipts")
    execute_post_boundary(clock=CalibratedClock(BOUNDARY_UTC, 1), scientific_root=root, receipt_root=receipts, callbacks=_callbacks([]))
    (receipts / "september_ranking.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PostBoundaryBlocked, match="R3_BLOCKED_LAUNCH_IDENTITY"):
        execute_post_boundary(clock=CalibratedClock(BOUNDARY_UTC, 1), scientific_root=root, receipt_root=receipts, callbacks=_callbacks([]))


def test_engineering_shadow_cannot_claim_scientific_mode() -> None:
    callbacks = _callbacks([])
    callbacks["SEPTEMBER_ENGINEERING_SHADOW"] = lambda _ctx: {"evidence_mode": "SCIENTIFIC"}
    with pytest.raises(PostBoundaryBlocked, match="R3_BLOCKED_SEPTEMBER_SHADOW"):
        execute_post_boundary(clock=CalibratedClock(BOUNDARY_UTC, 1), scientific_root=_droot("contaminated"), callbacks=callbacks)


def test_activation_cannot_run_without_launch_seal() -> None:
    callbacks = _callbacks([])
    del callbacks["LAUNCH_SEAL"]
    with pytest.raises(PostBoundaryBlocked, match="R3_BLOCKED_LAUNCH_IDENTITY"):
        execute_post_boundary(clock=CalibratedClock(BOUNDARY_UTC, 1), scientific_root=_droot("no_seal"), callbacks=callbacks)


def test_rollover_expires_without_authorized_next_roster() -> None:
    assert rollover_state(now=datetime(2026, 10, 1, tzinfo=UTC), has_next_roster=False) == "UNIVERSE_ROLLOVER_GAP"
    assert rollover_state(now=datetime(2026, 10, 1, tzinfo=UTC), has_next_roster=True) == "ACTIVE"
