"""Integrity checks for the immutable outcome-blind guardian qualification receipt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RECEIPT = (
    REPO_ROOT
    / "campaigns"
    / "r3_prospective_context_v1"
    / "operations"
    / "R3_V8_GUARDIAN_SYNTHETIC_QUALIFICATION_20260907_V1.json"
)


def _body_sha(value: dict[str, object]) -> str:
    body = dict(value)
    body.pop("body_sha256", None)
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_guardian_synthetic_receipt_is_complete_and_immutable() -> None:
    value = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert value["record_type"] == "R3_V8_GUARDIAN_SYNTHETIC_QUALIFICATION"
    assert value["status"] == "PASS"
    assert value["safe_skip_destructive_live_crash_test"] == "SAFE_SKIP_DESTRUCTIVE_LIVE_CRASH_TEST"
    assert value["outcomes_accessed"] is False
    assert value["final_holdout"] == "UNTOUCHED"
    assert value["r2b2"] == "NOT_ACCESSED"
    assert value["forceorder_v3_migration"] == "NOT_STARTED"
    matrix = value["matrix"]
    assert isinstance(matrix, list) and len(matrix) == 17
    assert {item["status"] for item in matrix} == {"PASS"}
    assert value["body_sha256"] == _body_sha(value)
