from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.generate_fast_discovery_v2_registry_v3 import generate


def test_v3_registry_adds_only_context_rows(tmp_path: Path) -> None:
    source = tmp_path / "FEATURE_REGISTRY_V2.csv"
    source.write_text("feature_id,kind,equation,polarity,threshold,state,signal_values,warmup,gap_reset,outcome_use\nfoo,continuous,x,none,NONE,continuous-value,continuous/NaN,warmup,segment-local,NO_OUTCOME_ACCESS\n", encoding="utf-8")
    path, digest = generate(tmp_path)
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    assert [row["feature_id"] for row in rows[-2:]] == ["btc_regime", "top50_breadth"]
    assert all(row["kind"] == "context" for row in rows[-2:])
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = json.loads((tmp_path / "REGISTRY_MANIFEST_V3.json").read_text(encoding="utf-8"))
    assert manifest["supersedes"] == "FEATURE_REGISTRY_V2.csv"
