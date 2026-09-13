from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.generate_fast_discovery_v2_context_registry import generate


def test_context_registry_is_deterministic_and_explicitly_supersedes_old(tmp_path: Path) -> None:
    path, digest = generate(tmp_path)
    path2, digest2 = generate(tmp_path)
    assert path == path2
    assert digest == digest2 == hashlib.sha256(path.read_bytes()).hexdigest()
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    assert len(rows) == 11
    assert [row["feature_id"] for row in rows[-2:]] == ["relative_strength_24h", "relative_strength_rank"]
    assert all(row["outcome_use"] == "NO_OUTCOME_ACCESS" for row in rows)
    manifest = json.loads((tmp_path / "REGISTRY_MANIFEST_V2.json").read_text(encoding="utf-8"))
    assert manifest["supersedes"] == "FEATURE_REGISTRY.csv"
    assert manifest["registry_sha256"] == digest
