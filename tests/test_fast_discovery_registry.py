from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from binance_research.fast_discovery_signals import S0_SIGNAL_SEMANTICS
from scripts.generate_fast_discovery_v2_registry import generate


def test_registry_is_deterministic_and_matches_frozen_semantics(tmp_path: Path) -> None:
    first, digest_one = generate(tmp_path)
    second, digest_two = generate(tmp_path)
    assert first == second
    assert digest_one == digest_two == hashlib.sha256(first.read_bytes()).hexdigest()
    rows = list(csv.DictReader(first.open(encoding="utf-8", newline="")))
    assert [row["feature_id"] for row in rows] == list(S0_SIGNAL_SEMANTICS)
    assert len(rows) == 9
    assert all(row["outcome_use"] == "NO_OUTCOME_ACCESS" for row in rows)
    manifest = json.loads((tmp_path / "REGISTRY_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["registry_sha256"] == digest_one
    assert manifest["holdout"] == "UNTOUCHED"
