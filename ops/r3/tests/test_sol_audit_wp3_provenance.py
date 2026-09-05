from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
INDEX_PATH = REPO_ROOT / "campaigns/r3_prospective_context_v1/operations/SOL_AUDIT_WP3_PROVENANCE_INDEX_20260905.json"
REPORT_PATH = REPO_ROOT / "reports/SOL_AUDIT_WP3_PROVENANCE_RECONCILIATION.md"
EXPECTED_KEYS = {
    "active_v8_identity",
    "base_commit",
    "branch",
    "corrections",
    "dispositions",
    "final_holdout_status",
    "merge_action",
    "outcome_values_accessed",
    "r2b2_status",
    "record_type",
    "references",
    "repair_commits",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_wp3_provenance_index_and_report_contract() -> None:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert set(index) == EXPECTED_KEYS
    assert isinstance(index["active_v8_identity"], dict)
    assert re.fullmatch(r"[0-9a-f]{40}", index["base_commit"])
    assert all(re.fullmatch(r"[0-9a-f]{40}", value) for value in index["repair_commits"])
    assert isinstance(index["references"], list)
    assert isinstance(index["dispositions"], list)
    assert isinstance(index["corrections"], list)
    assert index["outcome_values_accessed"] is False
    assert index["final_holdout_status"] == "UNTOUCHED"
    assert index["r2b2_status"] == "NOT_STARTED"
    assert index["merge_action"] == "NONE"
    authoritative = {
        "R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL.md": "ac788de08e77a5eb87b7b5a6619ada104668df3dc00f6908491ee2e1afa79672",
        "R3_EVALUATION_HORIZON_MAP_V1.json": "7cd935a33ac7ed47d1b9c7e037d5033b3add694934730eca5ebadda48fbb98e5",
        "R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL_REPRODUCIBILITY_MANIFEST.json": "0cb2400f2ada8cc35882563d49af14f8e33e4148f21cc128ce02c8127849a104",
    }
    for suffix, expected in authoritative.items():
        ref = next(item for item in index["references"] if item["path"].endswith(suffix))
        assert ref["sha256"] == expected
        assert _sha256(REPO_ROOT / ref["path"]) == expected
        assert suffix in report
        assert expected in report
    statuses = {item["status"] for item in index["dispositions"]}
    assert "CURRENT_FROZEN" in statuses
    assert "HISTORICAL_EVIDENCE/SUPERSEDED_BY_ADVERSARIAL_V2" in statuses
    assert "INVALID_SUPERSEDED/BLOCKED" in statuses
    assert "HARNESS_REPAIR_ONLY" in statuses
    assert "HISTORICAL_SNAPSHOT" in statuses
    for item in index["corrections"]:
        assert re.fullmatch(r"[0-9a-f]{64}", item["old_sha256"])
        assert re.fullmatch(r"[0-9a-f]{64}", item["new_sha256"])
        assert item["path"] in report
        assert item["old_sha256"] in report
        assert item["new_sha256"] in report
    assert "net_return" not in report.lower()
    assert "aggregate_mean_net_return" not in report.lower()
