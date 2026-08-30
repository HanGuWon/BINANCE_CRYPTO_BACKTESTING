from __future__ import annotations

import json
from pathlib import Path

import pytest

from binance_research.collector import AppendOnlyEventStore
from binance_research.r3_operations import CollectorLockError, LaunchIdentityError, append_manifest, append_segment_manifest, build_manifest, cycle_metadata, finalize_segment, require_sha256, single_instance_lock, verify_engineering_shadow_root, verify_launch_identity, verify_manifest_chain, verify_scientific_launch_identity, write_health_receipt, write_pilot_receipt


def test_manifest_chain_is_hash_linked_and_append_only(tmp_path: Path) -> None:
    raw = tmp_path / "raw_v1" / "um" / "BTCUSDT"
    raw.mkdir(parents=True)
    (raw / "premium.jsonl").write_text('{"value":1}\n', encoding="utf-8")
    first = build_manifest(tmp_path / "raw_v1", manifest_id="m1")
    chain = append_manifest(tmp_path / "raw_v1", first)
    second = build_manifest(tmp_path / "raw_v1", previous_manifest_sha256=first["manifest_sha256"], manifest_id="m2")
    append_manifest(tmp_path / "raw_v1", second)
    assert verify_manifest_chain(chain)
    assert len(chain.read_text(encoding="utf-8").splitlines()) == 2


def test_single_instance_lock_rejects_collision_and_cleans_up(tmp_path: Path) -> None:
    lock = tmp_path / "collector.lock"
    with single_instance_lock(lock):
        with pytest.raises(CollectorLockError):
            with single_instance_lock(lock):
                pass
    assert not lock.exists()


def test_health_receipt_contains_operational_identity(tmp_path: Path) -> None:
    path = write_health_receipt(tmp_path, campaign_id="r3_prospective_context_v1", manifest_sha256="a" * 64, roster_sha256="b" * 64, stream_state={"premium": "OK"})
    receipt = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert receipt["campaign_id"] == "r3_prospective_context_v1"
    assert receipt["manifest_sha256"] == "a" * 64
    assert receipt["stream_state"]["premium"] == "OK"
    assert path.parent.parent == tmp_path


def test_shadow_event_envelopes_are_explicitly_labeled(tmp_path: Path) -> None:
    path = AppendOnlyEventStore(tmp_path).append(
        "premium", "um", "BTCUSDT", {"value": 0.0},
        endpoint="/fapi/v1/premiumIndex", evidence_mode="ENGINEERING_SHADOW",
    )
    envelope = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert envelope["evidence_mode"] == "ENGINEERING_SHADOW"
    assert envelope["source_kind"] == "rest_snapshot"


def test_engineering_shadow_root_verifier_binds_manifest_health_and_roster(tmp_path: Path) -> None:
    raw = tmp_path / "raw_v1" / "um" / "BTCUSDT"
    raw.mkdir(parents=True)
    envelope = {"symbol": "BTCUSDT", "stream": "premium", "evidence_mode": "ENGINEERING_SHADOW", "continuity_state": "COMPLETE"}
    (raw / "premium.jsonl").write_text(json.dumps(envelope) + "\n", encoding="utf-8")
    manifest = build_manifest(tmp_path / "raw_v1", manifest_id="shadow")
    append_manifest(tmp_path / "raw_v1", manifest)
    write_health_receipt(tmp_path, campaign_id="r3_prospective_context_v1", manifest_sha256=manifest["manifest_sha256"], roster_sha256="a" * 64, stream_state={"status": "CYCLE_COMPLETE"}, evidence_mode="ENGINEERING_SHADOW")
    result = verify_engineering_shadow_root(tmp_path, expected_symbols=["BTCUSDT"], roster_sha256="a" * 64)
    assert result["rows"] == 1
    assert result["symbols"] == 1


def test_scientific_identity_requires_exact_roster_and_contract_fields(tmp_path: Path) -> None:
    launch = tmp_path / "launch.json"
    body = {"status": "R3_READY_FOR_PROSPECTIVE_LAUNCH", "pilot_status": "VERIFIED", "campaign_id": "r3_prospective_context_v1", "roster_sha256": "a" * 64, "implementation_commit": "c"}
    launch.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(LaunchIdentityError, match="source_tree_sha256"):
        verify_scientific_launch_identity(launch, expected={**body, "source_tree_sha256": "b" * 64})


def test_cycle_metadata_and_finalized_segment_are_immutable(tmp_path: Path) -> None:
    metadata = cycle_metadata(cycle_id="c1", target_bar_open="2026-08-30T00:00:00Z", target_bar_close="2026-08-30T00:15:00Z", scheduled_collection_time="2026-08-30T00:15:01Z", actual_collection_start="2026-08-30T00:15:01Z", cycle_completed_at="2026-08-30T00:15:02Z", clock_calibration_id="clk1", eligible_next_execution_time="2026-08-30T00:30:00Z")
    assert metadata["cycle_id"] == "c1"
    segment = tmp_path / "segment.jsonl"
    segment.write_text(json.dumps({"exchange_event_time": "2026-08-30T00:15:00Z", "collector_receipt_time": "2026-08-30T00:15:01Z"}) + "\n", encoding="utf-8")
    receipt = tmp_path / "segment.receipt.json"
    first = finalize_segment(segment, receipt)
    assert first["status"] == "FINALIZED"
    assert finalize_segment(segment, receipt) == first
    segment.write_text(segment.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="immutable"):
        finalize_segment(segment, receipt)


def test_manifest_chain_tamper_is_rejected(tmp_path: Path) -> None:
    raw = tmp_path / "raw_v1"
    raw.mkdir()
    first = build_manifest(raw, manifest_id="m1")
    chain = append_manifest(raw, first)
    chain.write_text(chain.read_text(encoding="utf-8").replace('"total_rows":0', '"total_rows":1'), encoding="utf-8")
    assert verify_manifest_chain(chain) is False


def test_roster_identity_must_be_hex_sha256() -> None:
    assert require_sha256("A" * 64, "roster").islower()
    with pytest.raises(ValueError):
        require_sha256("not-a-sha", "roster")


def test_pilot_receipt_is_operational_only(tmp_path: Path) -> None:
    path = write_pilot_receipt(tmp_path, symbols=["BTCUSDT", "ETHUSDT"], manifest_sha256="a" * 64, roster_sha256="b" * 64, stream_counts={"premium": 2}, bytes_written=10, latency_seconds={"premium": 0.1}, gap_counts={}, storage_projection_bytes={"24h": 960}, liquidation_state={"connected": True})
    receipt = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert receipt["mode"] == "ENGINEERING_PILOT"
    assert not {"gross_return", "net_return", "pnl", "sharpe"} & set(receipt)


def test_pilot_scope_validator_is_exact() -> None:
    from scripts.run_r3_prospective_collector import PILOT_SYMBOLS, validate_pilot_inputs
    validate_pilot_inputs(Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r3_prospective_context_v1"), list(PILOT_SYMBOLS))
    with pytest.raises(ValueError):
        validate_pilot_inputs(Path("C:/tmp/r3_prospective_context_v1"), list(PILOT_SYMBOLS))


def test_engineering_shadow_loads_symbols_only_from_valid_roster() -> None:
    from datetime import UTC, datetime
    from scripts.run_r3_prospective_collector import validate_engineering_shadow_inputs

    symbols, roster_sha = validate_engineering_shadow_inputs(
        Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r3_prospective_context_v1/engineering_shadow_august_v1"),
        Path("campaigns/r3_prospective_context_v1/rosters/2026-08.json"),
        at_utc=datetime(2026, 8, 30, 12, tzinfo=UTC),
    )
    assert len(symbols) == 50
    assert roster_sha == "ec2609bb7df0019984d41be3c5f18154591f5c8735a71557de7207c5606a00cc"


def test_engineering_shadow_rejects_scientific_roots_and_post_boundary() -> None:
    from datetime import UTC, datetime
    from scripts.run_r3_prospective_collector import validate_engineering_shadow_inputs

    roster = Path("campaigns/r3_prospective_context_v1/rosters/2026-08.json")
    with pytest.raises(ValueError):
        validate_engineering_shadow_inputs(Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r3_prospective_context_v1/raw_v1"), roster, at_utc=datetime(2026, 8, 30, tzinfo=UTC))
    with pytest.raises(ValueError):
        validate_engineering_shadow_inputs(Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r3_prospective_context_v1/engineering_shadow_august_v4"), roster, at_utc=datetime(2026, 9, 1, tzinfo=UTC))


def test_stale_pid_lock_is_recovered_but_malformed_lock_is_not(tmp_path: Path) -> None:
    stale = tmp_path / "stale.lock"
    stale.write_text("99999999", encoding="utf-8")
    with single_instance_lock(stale):
        assert stale.exists()
    malformed = tmp_path / "malformed.lock"
    malformed.write_text("not-a-pid", encoding="utf-8")
    with pytest.raises(CollectorLockError):
        with single_instance_lock(malformed):
            pass


def test_segment_manifest_and_launch_identity_fail_closed(tmp_path: Path) -> None:
    raw = tmp_path / "raw_v1"
    raw.mkdir()
    manifest = build_manifest(raw, manifest_id="segment-1")
    segment = append_segment_manifest(raw, manifest, segment_id="20260829T1200Z")
    assert segment.exists()
    launch = tmp_path / "launch.json"
    launch.write_text(json.dumps({"status": "R3_BLOCKED_FINAL_LAUNCH_CONFORMANCE"}), encoding="utf-8")
    with pytest.raises(LaunchIdentityError):
        verify_launch_identity(launch, roster_sha256="a" * 64)
