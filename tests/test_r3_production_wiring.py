from __future__ import annotations

import hashlib
import json
import io
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
    result = executor._verify_august_source({"control_root": str(tmp_path), "AUGUST_SOURCE_ACQUISITION": {"manifest_path": str(manifest)}})
    assert result["rows"] == 1
    bad = pd.read_csv(manifest)
    bad.loc[0, "market"] = "spot"
    bad.to_csv(manifest, index=False)
    with pytest.raises(executor.PostBoundaryBlocked, match="R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE"):
        executor._verify_august_source({"control_root": str(tmp_path), "AUGUST_SOURCE_ACQUISITION": {"manifest_path": str(manifest)}})


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


def test_rollover_gap_blocks_without_next_roster() -> None:
    assert executor.rollover_state(now=datetime(2026, 10, 1, tzinfo=UTC), has_next_roster=False) == "UNIVERSE_ROLLOVER_GAP"
    assert executor.rollover_state(now=datetime(2026, 9, 30, 23, 59, tzinfo=UTC), has_next_roster=False) == "ACTIVE"


def test_canonical_receipt_records_current_full_suite() -> None:
    receipt = json.loads(Path("campaigns/r3_prospective_context_v1/full_pytest_receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["passed"] == 296 and receipt["failed"] == 0
    assert receipt["scientific_source_dirty"] is False
    assert receipt["holdout_status"] == "UNTOUCHED"
