from __future__ import annotations

import hashlib
import json
import io
import os
import subprocess
import zipfile
from datetime import UTC, datetime
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
    identity = executor._freeze_launch_identity({
        "SEPTEMBER_ROSTER_REPLAY": replayed,
        "SEPTEMBER_ROSTER_FREEZE": frozen,
        "AUGUST_SOURCE_VERIFICATION": {},
        "SEPTEMBER_RANKING": {},
        "SEPTEMBER_ENGINEERING_SHADOW": {},
        "scientific_root": str(tmp_path / "scientific"),
    })
    assert identity["roster_sha256"] == frozen["roster_sha256"]
    manifest = executor._build_launch_manifest({"control_root": str(tmp_path), "scientific_root": str(tmp_path / "scientific"), "clock": "2026-09-01T00:00:00+00:00", "LAUNCH_IDENTITY_FREEZE": identity, "SEPTEMBER_ROSTER_REPLAY": replayed, "AUGUST_SOURCE_VERIFICATION": {}, "SEPTEMBER_RANKING": {}, "SEPTEMBER_ROSTER_FREEZE": frozen})
    assert manifest["status"] == "R3_READY_FOR_PROSPECTIVE_LAUNCH"
    seal = executor._build_launch_seal({"control_root": str(tmp_path), "clock": "2026-09-01T00:00:00+00:00", "LAUNCH_IDENTITY_FREEZE": identity, "SEPTEMBER_ROSTER_REPLAY": replayed, "LAUNCH_MANIFEST_BUILD": manifest})
    assert seal["status"] == "SEALED"
    assert json.loads(Path(seal["seal_path"]).read_text())["manifest_sha256"] == manifest["manifest_sha256"]


def test_real_august_verifier_rejects_scope_and_accepts_complete_fixture(tmp_path: Path) -> None:
    raw = tmp_path / "archive.zip"
    rows = []
    for day in range(1, 32):
        stamp = int(pd.Timestamp(f"2026-08-{day:02d}", tz="UTC").timestamp() * 1000)
        close = stamp + 86_400_000 - 1
        rows.append([stamp, 1, 2, 0.5, 1.5, 10, close, 15, 1, 5, 7, 0])
    payload = io.StringIO()
    for row in rows:
        payload.write(",".join(map(str, row)) + "\n")
    with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("FIXUSDT-1d-2026-08.csv", payload.getvalue())
    sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    manifest = tmp_path / "acquisition.csv"
    pd.DataFrame([{"market": "um", "symbol": "FIXUSDT", "archive_month": "2026-08", "integrity_status": "PASS", "published_sha256": sha, "computed_sha256": sha, "raw_path": str(raw)}]).to_csv(manifest, index=False)
    result = executor._verify_august_source({"control_root": str(tmp_path), "census_dir": str(tmp_path / "missing-census"), "AUGUST_SOURCE_ACQUISITION": {"manifest_path": str(manifest)}})
    assert result["rows"] == 1
    bad = pd.read_csv(manifest)
    bad.loc[0, "market"] = "spot"
    bad.to_csv(manifest, index=False)
    with pytest.raises(executor.PostBoundaryBlocked, match="R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE"):
        executor._verify_august_source({"control_root": str(tmp_path), "census_dir": str(tmp_path / "missing-census"), "AUGUST_SOURCE_ACQUISITION": {"manifest_path": str(manifest)}})


def test_production_clock_uses_binance_rest_client_five_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    import binance_research.data as data
    calls: list[tuple[str, int]] = []
    class FakeRest:
        def calibrate_server_clock(self, market: str, *, sample_count: int = 5):
            calls.append((market, sample_count))
            return type("Calibration", (), {"round_trip_ms": 12, "offset_ms": 0, "calibration_id": "fake"})()
    monkeypatch.setattr(data, "BinanceRestClient", FakeRest)
    clock = executor._production_clock()
    assert calls == [("um", 5)]
    assert clock.uncertainty_ms == 7


def test_august_acquisition_filters_spot_before_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import scripts.build_r16_1d_universe as builder
    listed = pd.DataFrame([{"market": "spot", "symbol": "SPOTUSDT", "archive_month": "2026-08", "interval": "1d"}, {"market": "um", "symbol": "UMUSDT", "archive_month": "2026-08", "interval": "1d"}])
    monkeypatch.setattr(builder, "census_1d", lambda *_args, **_kwargs: (pd.DataFrame(), listed))
    captured: list[pd.DataFrame] = []
    def fake_acquire(frame: pd.DataFrame, **_kwargs):
        captured.append(frame.copy())
        return pd.DataFrame([{"market": "um", "symbol": "UMUSDT", "archive_month": "2026-08", "raw_path": str(tmp_path / "um.zip"), "published_sha256": "a" * 64, "computed_sha256": "a" * 64, "integrity_status": "PASS"}])
    monkeypatch.setattr(builder, "acquire_1d", fake_acquire)
    result = executor._acquire_august_source({"control_root": str(tmp_path), "raw_root": str(tmp_path / "raw"), "census_dir": str(tmp_path / "census")})
    assert captured and set(captured[0]["market"]) == {"um"}
    assert result["source_mode"] == "MONTHLY_ARCHIVE"


def test_activation_adapter_requires_verified_cycle() -> None:
    with pytest.raises(executor.PostBoundaryBlocked, match="R3_BLOCKED_LAUNCH_IDENTITY"):
        executor._activate_scientific({})
    result = executor._activate_scientific({"collector_launcher": lambda _ctx: {"cycles_completed": 1, "manifest_chain_pass": True, "health_pass": True, "evidence_mode": "SCIENTIFIC"}})
    assert result["evidence_mode"] == "SCIENTIFIC"


def test_supervisor_requires_first_cycle_and_records_process_identity(tmp_path: Path) -> None:
    class FakeProcess:
        pid = 4242
        def __init__(self) -> None:
            self.terminated = False
        def poll(self):
            return None
        def terminate(self):
            self.terminated = True
    process = FakeProcess()
    result = executor.supervise_scientific_process(["fake"], scientific_root=tmp_path, control_root=tmp_path / "control", popen=lambda *args, **kwargs: process, probe=lambda _proc, _root: {"cycles_completed": 1, "manifest_chain_pass": True, "health_pass": True, "evidence_mode": "SCIENTIFIC"})
    assert result["pid"] == 4242
    assert result["supervisor_status"] == "RUNNING"
    assert not (tmp_path / "control" / "scientific_collector.pid").exists()


def test_supervisor_terminates_unverified_child(tmp_path: Path) -> None:
    class FakeProcess:
        pid = 7
        def __init__(self) -> None:
            self.terminated = False
        def poll(self):
            return None
        def terminate(self):
            self.terminated = True
    process = FakeProcess()
    with pytest.raises(executor.PostBoundaryBlocked, match="R3_BLOCKED_LAUNCH_IDENTITY"):
        executor.supervise_scientific_process(["fake"], scientific_root=tmp_path, control_root=tmp_path / "control", timeout_seconds=0, popen=lambda *args, **kwargs: process, probe=lambda _proc, _root: {"cycles_completed": 0, "manifest_chain_pass": False, "health_pass": False})
    assert process.terminated


def test_supervisor_default_probe_rejects_file_only_evidence(tmp_path: Path) -> None:
    class FakeProcess:
        pid = 8
        def __init__(self) -> None:
            self.terminated = False
        def poll(self):
            return None
        def terminate(self):
            self.terminated = True
    process = FakeProcess()
    (tmp_path / "raw_v1").mkdir(parents=True)
    (tmp_path / "health").mkdir()
    with pytest.raises(executor.PostBoundaryBlocked, match="R3_BLOCKED_LAUNCH_IDENTITY"):
        executor.supervise_scientific_process(["fake"], scientific_root=tmp_path, control_root=tmp_path / "control", timeout_seconds=0, popen=lambda *args, **kwargs: process)
    assert process.terminated


def test_project_factory_uses_named_adapters_not_proof_defaults() -> None:
    callbacks = executor.build_project_production_callbacks()
    assert callbacks["AUGUST_SOURCE_ACQUISITION"] is executor._acquire_august_source
    assert callbacks["SEPTEMBER_RANKING"] is executor._build_september_ranking
    assert callbacks["LAUNCH_SEAL"] is executor._build_launch_seal


def test_direct_entrypoint_bootstraps_import_closure_from_arbitrary_cwd(tmp_path: Path) -> None:
    script = executor.REPO_ROOT / "scripts" / "prepare_r3_post_boundary_launch.py"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [str(__import__("sys").executable), str(script), "--self-check-imports"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"imports": "PASS", "repo_root": str(executor.REPO_ROOT)}


def test_collector_direct_entrypoint_bootstraps_from_arbitrary_cwd(tmp_path: Path) -> None:
    script = executor.REPO_ROOT / "scripts" / "run_r3_prospective_collector.py"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [str(__import__("sys").executable), str(script), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_repository_bootstrap_paths_are_canonical() -> None:
    assert executor.REPO_ROOT_SCRIPTS == executor.REPO_ROOT / "scripts"
    assert str(executor.REPO_ROOT) in executor.sys.path
    assert str(executor.REPO_ROOT / "src") in executor.sys.path


def test_launch_v2_defaults_do_not_reuse_historical_control_or_shadow_roots() -> None:
    assert str(executor.CONTROL_ROOT).endswith("2026-09-production-v2")
    assert executor.CONTROL_ROOT != executor.LEGACY_CONTROL_ROOT
    assert executor.CONTROL_ROOT != executor.FAILED_V1_CONTROL_ROOT
    assert str(executor.SHADOW_ROOT).endswith("engineering_shadow_september_launch_v2")


def test_launch_v2_rejects_legacy_and_failed_v1_control_roots() -> None:
    for forbidden in (executor.LEGACY_CONTROL_ROOT, executor.FAILED_V1_CONTROL_ROOT):
        with pytest.raises(executor.PostBoundaryBlocked, match="R3_BLOCKED_LAUNCH_IDENTITY"):
            executor.require_control_root(forbidden)


def test_collector_launcher_uses_absolute_repository_script(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_supervisor(command: list[str], **kwargs: object) -> dict[str, object]:
        captured["command"] = command
        return {"cycles_completed": 1, "manifest_chain_pass": True, "health_pass": True}

    monkeypatch.setattr(executor, "supervise_scientific_process", fake_supervisor)
    executor._production_collector_launcher({
        "scientific_root": "D:/scientific",
        "control_root": "D:/control",
        "SEPTEMBER_ROSTER_FREEZE": {"roster_path": "D:/roster.json"},
        "LAUNCH_MANIFEST_BUILD": {"manifest_path": "D:/manifest.json"},
        "LAUNCH_SEAL": {"seal_path": "D:/seal.json"},
        "SEPTEMBER_ROSTER_REPLAY": {"roster_sha256": "a" * 64},
    })
    command = captured["command"]
    assert isinstance(command, list)
    assert command[1] == str(executor.REPO_ROOT / "scripts" / "run_r3_prospective_collector.py")
    assert Path(command[1]).is_absolute()


def test_rollover_gap_blocks_without_next_roster() -> None:
    assert executor.rollover_state(now=datetime(2026, 10, 1, tzinfo=UTC), has_next_roster=False) == "UNIVERSE_ROLLOVER_GAP"
    assert executor.rollover_state(now=datetime(2026, 9, 30, 23, 59, tzinfo=UTC), has_next_roster=False) == "ACTIVE"


def test_calibrated_clock_defaults_to_five_samples() -> None:
    clock = executor.CalibratedClock(datetime(2026, 8, 31, tzinfo=UTC), 1.0)
    assert clock.sample_count == 5


def test_canonical_receipt_records_current_full_suite() -> None:
    receipt = json.loads(Path("campaigns/r3_prospective_context_v1/full_pytest_receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["passed"] >= 300 and receipt["failed"] == 0
    assert receipt["scientific_source_dirty"] is False
    assert receipt["holdout_status"] == "UNTOUCHED"


def test_contract_hash_fields_map_to_distinct_canonical_files() -> None:
    root = Path("campaigns/r3_prospective_context_v1")
    data_hash = hashlib.sha256((root / "data_contract.md").read_bytes()).hexdigest()
    dependency_hash = hashlib.sha256((root / "R3_SOURCE_DEPENDENCY_MATRIX.json").read_bytes()).hexdigest()
    assert data_hash != dependency_hash
    identity = executor._freeze_launch_identity({"SEPTEMBER_ROSTER_REPLAY": {"roster_sha256": "a" * 64}, "SEPTEMBER_ROSTER_FREEZE": {}, "AUGUST_SOURCE_VERIFICATION": {}, "SEPTEMBER_RANKING": {}, "SEPTEMBER_ENGINEERING_SHADOW": {}, "scientific_root": "D:/scientific"})
    assert identity["data_contract_sha256"] == data_hash
    assert identity["source_dependency_matrix_sha256"] == dependency_hash


def test_ranking_requires_verified_august_receipt(tmp_path: Path) -> None:
    with pytest.raises(executor.PostBoundaryBlocked, match="R3_BLOCKED_SEPTEMBER_RANKING"):
        executor._build_september_ranking({"control_root": str(tmp_path), "census_dir": str(tmp_path)})


def test_verified_monthly_and_daily_transport_paths_have_equal_ranking_semantics(tmp_path: Path) -> None:
    from scripts.qualify_r3_forward_ranking import build_forward_ranking_from_verified_source, ranking_semantic_sha256
    census = tmp_path / "census"
    census.mkdir()
    pd.DataFrame([{"market": "um", "symbol": "FIXUSDT", "first_archive_month": "2026-08"}]).to_csv(census / "um_archive_symbol_census.csv", index=False)
    rows = []
    for day in range(1, 32):
        stamp = int(pd.Timestamp(f"2026-08-{day:02d}", tz="UTC").timestamp() * 1000)
        rows.append([stamp, 1, 2, 0.5, 1.5, 10, stamp + 86_400_000 - 1, 15, 1, 5, 7, 0])
    def write_zip(path: Path, subset: list[list[object]]) -> str:
        payload = "".join(",".join(map(str, row)) + "\n" for row in subset)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("FIXUSDT-1d.csv", payload)
        return hashlib.sha256(path.read_bytes()).hexdigest()
    monthly = tmp_path / "monthly.zip"
    monthly_sha = write_zip(monthly, rows)
    daily_items = []
    for index, row in enumerate(rows, start=1):
        path = tmp_path / f"daily-{index:02d}.zip"
        daily_items.append({"symbol": "FIXUSDT", "path": str(path), "sha256": write_zip(path, [row]), "source_mode": "DAILY_ARCHIVE_FALLBACK"})
    def receipt(path: Path, items: list[dict[str, object]]) -> Path:
        payload = {"status": "PASS", "market": "um", "interval": "1d", "verified_inputs": items, "expected_symbols": ["FIXUSDT"]}
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path
    monthly_receipt = receipt(tmp_path / "monthly-receipt.json", [{"symbol": "FIXUSDT", "path": str(monthly), "sha256": monthly_sha, "source_mode": "MONTHLY_ARCHIVE"}])
    daily_receipt = receipt(tmp_path / "daily-receipt.json", daily_items)
    left = pd.read_csv(build_forward_ranking_from_verified_source(monthly_receipt, census, tmp_path / "out-monthly", effective_month="2026-09"))
    right = pd.read_csv(build_forward_ranking_from_verified_source(daily_receipt, census, tmp_path / "out-daily", effective_month="2026-09"))
    fields = ["prior_month_quote_volume", "rank", "selected_top50"]
    pd.testing.assert_frame_equal(left[fields], right[fields], check_dtype=False)
    assert ranking_semantic_sha256(left, effective_month="2026-09", selected_only=False) == ranking_semantic_sha256(right, effective_month="2026-09", selected_only=False)
