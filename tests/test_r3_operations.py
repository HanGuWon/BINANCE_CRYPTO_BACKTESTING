from __future__ import annotations

import json
from pathlib import Path

import pytest

from binance_research.r3_operations import CollectorLockError, append_manifest, build_manifest, single_instance_lock, verify_manifest_chain, write_health_receipt


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


def test_manifest_chain_tamper_is_rejected(tmp_path: Path) -> None:
    raw = tmp_path / "raw_v1"
    raw.mkdir()
    first = build_manifest(raw, manifest_id="m1")
    chain = append_manifest(raw, first)
    chain.write_text(chain.read_text(encoding="utf-8").replace('"total_rows":0', '"total_rows":1'), encoding="utf-8")
    assert verify_manifest_chain(chain) is False
