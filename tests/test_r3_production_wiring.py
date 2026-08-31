from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import scripts.prepare_r3_post_boundary_launch as executor


def _ranking(path: Path) -> Path:
    rows = []
    for rank in range(1, 51):
        rows.append({"market": "um", "symbol": f"FIX{rank:03d}USDT", "volume_month": "2026-08", "universe_month": "2026-09", "coverage_ratio": 1.0, "eligibility_reason": "ELIGIBLE_COMPLETE_PRIOR_MONTH", "rank": rank, "selected_top50": True})
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_real_roster_freeze_replay_and_identity_artifacts(tmp_path: Path) -> None:
    ranking = _ranking(tmp_path / "universe_monthly.csv")
    roster_path = tmp_path / "rosters" / "2026-09.json"
    context = {"control_root": str(tmp_path), "SEPTEMBER_RANKING": {"artifact_path": str(ranking)}, "roster_path": str(roster_path)}
    frozen = executor._freeze_september_roster(context)
    assert frozen["symbol_count"] == 50
    replayed = executor._replay_september_roster({"SEPTEMBER_ROSTER_FREEZE": frozen})
    assert replayed["roster_sha256"] == frozen["roster_sha256"]
    identity = executor._freeze_launch_identity({"SEPTEMBER_ROSTER_REPLAY": replayed, "registry_sha256": "a" * 64})
    assert identity["roster_sha256"] == frozen["roster_sha256"]
    manifest = executor._build_launch_manifest({"control_root": str(tmp_path), "scientific_root": str(tmp_path / "scientific"), "clock": "2026-09-01T00:00:00+00:00", "LAUNCH_IDENTITY_FREEZE": identity, "SEPTEMBER_ROSTER_REPLAY": replayed})
    assert manifest["status"] == "R3_READY_FOR_PROSPECTIVE_LAUNCH"
    seal = executor._build_launch_seal({"control_root": str(tmp_path), "clock": "2026-09-01T00:00:00+00:00", "LAUNCH_IDENTITY_FREEZE": identity, "SEPTEMBER_ROSTER_REPLAY": replayed, "LAUNCH_MANIFEST_BUILD": manifest})
    assert seal["status"] == "SEALED"
    assert json.loads(Path(seal["seal_path"]).read_text())["manifest_sha256"] == manifest["manifest_sha256"]


def test_real_august_verifier_rejects_scope_and_accepts_complete_fixture(tmp_path: Path) -> None:
    raw = tmp_path / "archive.zip"
    raw.write_bytes(b"fixture")
    sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    manifest = tmp_path / "acquisition.csv"
    pd.DataFrame([{"market": "um", "symbol": "FIXUSDT", "archive_month": "2026-08", "integrity_status": "PASS", "published_sha256": sha, "computed_sha256": sha, "raw_path": str(raw)}]).to_csv(manifest, index=False)
    result = executor._verify_august_source({"control_root": str(tmp_path), "AUGUST_SOURCE_ACQUISITION": {"manifest_path": str(manifest)}})
    assert result["rows"] == 1
    bad = pd.read_csv(manifest)
    bad.loc[0, "market"] = "spot"
    bad.to_csv(manifest, index=False)
    with pytest.raises(executor.PostBoundaryBlocked, match="R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE"):
        executor._verify_august_source({"control_root": str(tmp_path), "AUGUST_SOURCE_ACQUISITION": {"manifest_path": str(manifest)}})


def test_activation_adapter_requires_verified_cycle() -> None:
    with pytest.raises(executor.PostBoundaryBlocked, match="R3_BLOCKED_LAUNCH_IDENTITY"):
        executor._activate_scientific({})
    result = executor._activate_scientific({"collector_launcher": lambda _ctx: {"cycles_completed": 1, "manifest_chain_pass": True, "health_pass": True, "evidence_mode": "SCIENTIFIC"}})
    assert result["evidence_mode"] == "SCIENTIFIC"


def test_project_factory_uses_named_adapters_not_proof_defaults() -> None:
    callbacks = executor.build_project_production_callbacks()
    assert callbacks["AUGUST_SOURCE_ACQUISITION"] is executor._acquire_august_source
    assert callbacks["SEPTEMBER_RANKING"] is executor._build_september_ranking
    assert callbacks["LAUNCH_SEAL"] is executor._build_launch_seal
