from __future__ import annotations

import json
from pathlib import Path

from evidence_paths import _wsl_candidate, resolve_evidence_root
from portable_semantic_hash import portable_semantic_sha256


def test_wsl_mapping_is_deterministic() -> None:
    assert _wsl_candidate(r"D:\data\root") == Path("/mnt/d/data/root")


def test_evidence_override_fails_closed_when_unavailable(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    monkeypatch.setenv("R2B_V6_EVIDENCE_ROOT", str(missing))
    assert resolve_evidence_root() is None


def test_csv_portable_hash_ignores_line_endings_and_row_order(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_bytes(b"b,a\r\n2,1.0\r\n1,2.0000000000000000\r\n")
    second.write_bytes("b,a\n1,2\n2,1\n".encode())
    assert portable_semantic_sha256(first) == portable_semantic_sha256(second)


def test_json_portable_hash_sorts_keys_and_normalizes_drive_paths(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(json.dumps({"root": r"D:\data", "n": 1}, indent=2), encoding="utf-8")
    second.write_text('{"n":1,"root":"/mnt/d/data"}\n', encoding="utf-8")
    assert portable_semantic_sha256(first) == portable_semantic_sha256(second)


def test_csv_portable_hash_normalizes_path_columns(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("root,value\nD:\\\\data,1\n", encoding="utf-8")
    second.write_text("root,value\n/mnt/d/data,1\n", encoding="utf-8")
    assert portable_semantic_sha256(first) == portable_semantic_sha256(second)


def test_malformed_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        portable_semantic_sha256(path)
