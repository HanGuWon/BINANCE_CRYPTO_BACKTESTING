from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "r3_prospective_context_v1"


def test_registry_hypotheses_join_to_exact_source_matrix() -> None:
    registry = list(csv.DictReader((CAMPAIGN / "trial_registry.csv").open(encoding="utf-8", newline="")))
    matrix = json.loads((CAMPAIGN / "R3_SOURCE_DEPENDENCY_MATRIX.json").read_text(encoding="utf-8"))
    expected = {
        "R3_H01": ("EXECUTION_QUALITY_CONTEXT", "book_ticker"),
        "R3_H02": ("PRICE_OI_QUADRANT", "klines_15m+open_interest"),
        "R3_H03": ("LIQUIDATION_CONTINUATION", "forceOrder"),
        "R3_H04": ("LIQUIDATION_REVERSION", "forceOrder"),
        "R3_H05": ("CROWDING_STRESS_MODIFIER", "premium"),
        "R3_H06": ("BTC_BREADTH_CONCORDANCE", "klines_15m"),
    }
    assert set(row["hypothesis_id"] for row in registry) == set(expected)
    for row in registry:
        mechanism, stream = expected[row["hypothesis_id"]]
        assert row["mechanism"] == mechanism
        assert matrix["primary"][row["hypothesis_id"]]["stream"] == stream
        assert matrix["primary"][row["hypothesis_id"]]["primary_required"] is True


def test_universe_contract_explicitly_selects_all_usdm_perpetuals() -> None:
    text = (CAMPAIGN / "universe_contract.md").read_text(encoding="utf-8")
    assert "USD-M rows" in text
    assert "cryptocurrency-only" not in text
