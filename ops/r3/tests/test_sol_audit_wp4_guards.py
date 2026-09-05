from __future__ import annotations

import json
from pathlib import Path

from ops.r3.compare_sol_audit_qualification import normalize_transcript
from ops.r3.verify_sol_audit_live_guard import main as live_guard_main
from ops.r3.verify_sol_audit_qualification_allowlist import audit_module


def test_allowlist_flags_persisted_reader_only_when_path_is_literal(tmp_path: Path) -> None:
    safe = tmp_path / "test_safe.py"
    safe.write_text("def test_safe(tmp_path):\n    return tmp_path / 'scientific_raw_v8'\n", encoding="utf-8")
    assert audit_module(safe) == []
    unsafe = tmp_path / "test_unsafe.py"
    unsafe.write_text("import pandas as pd\ndef test_unsafe():\n    return pd.read_parquet('D:/r2a2/checkpoints/trades.parquet')\n", encoding="utf-8")
    assert any("persisted" in finding for finding in audit_module(unsafe))


def test_qualification_transcript_normalization_keeps_summary_and_strips_duration() -> None:
    first = normalize_transcript("tests\\test_x.py::test_ok\n1 passed in 1.23s\n")
    second = normalize_transcript("tests/test_x.py::test_ok\n1 passed in 9.99s\n")
    assert first == second
    assert "passed" in first


def test_live_guard_reads_repository_metadata_only(capsys) -> None:
    assert live_guard_main(["--metadata-only"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PASS"
    assert result["metadata_only"] is True
    assert result["process_touched"] is False
    assert result["raw_root_opened"] is False
    assert result["checkpoint_paths_checked"] is False
