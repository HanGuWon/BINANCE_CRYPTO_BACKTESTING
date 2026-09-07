from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ops.r3.verify_r3_v8_wp5_firewall_v7 import (
    EXPECTED_V2_FILE_SHA256,
    EXPECTED_V3_FILE_SHA256,
    EXPECTED_V6_FILE_SHA256,
    EXPECTED_V7_FILE_SHA256,
    V2_PATH,
    V3_PATH,
    V6_PATH,
    V7_PATH,
    verify,
)


def test_v3_accounting_is_explicit_and_append_only() -> None:
    payload = json.loads(V3_PATH.read_text(encoding="utf-8"))
    assert payload["supersedes"]["status"] == "SUPERSEDED_BY_V3"
    assert payload["pre_outage"]["historical_missing_cycle_count"] == 87
    assert payload["outage_period"]["intervening_missing_cycle_count"] == 175
    assert payload["outage_period"]["native_step_count"] == 176
    assert payload["accounting"]["total_missing_snapshot"] == 262
    assert payload["nonqualifying_cycle_preservation"]["counted_as_strict_recovery_cycle"] is False
    assert payload["nonqualifying_cycle_preservation"]["mutation"] == "NONE"


def test_v2_v6_v3_v7_hashes_are_bound() -> None:
    assert hashlib.sha256(V2_PATH.read_bytes()).hexdigest() == EXPECTED_V2_FILE_SHA256
    assert hashlib.sha256(V3_PATH.read_bytes()).hexdigest() == EXPECTED_V3_FILE_SHA256
    assert hashlib.sha256(V6_PATH.read_bytes()).hexdigest() == EXPECTED_V6_FILE_SHA256
    assert EXPECTED_V7_FILE_SHA256 is not None
    assert hashlib.sha256(V7_PATH.read_bytes()).hexdigest() == EXPECTED_V7_FILE_SHA256


def test_v7_firewall_verifies_accounting_and_firewall() -> None:
    summary = verify()
    assert summary["status"] == "PASS"
    assert summary["accounting"]["outage_period_missing"] == 175
    assert summary["checks"]["temporal_boundary_proof"] == "44h / 15m = 176; 176 - 1 = 175"
    assert summary["checks"]["nonqualifying_cycle_preserved"].startswith("cycle-20260907T033004700902Z")
    assert summary["outcomes_accessed"] is False
    assert summary["final_holdout"] == "UNTOUCHED"
    assert summary["r2b2"] == "NOT_ACCESSED"
    assert summary["forceorder_v3_migration"] == "NOT_STARTED"
