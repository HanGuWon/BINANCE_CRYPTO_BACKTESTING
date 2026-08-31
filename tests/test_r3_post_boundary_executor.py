from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from scripts.prepare_r3_post_boundary_launch import (
    BOUNDARY_UTC,
    PostBoundaryBlocked,
    prepare_post_boundary_plan,
    require_fresh_scientific_root,
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
