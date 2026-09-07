from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ops.r3 import r3_forceorder_identity as identity


ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "campaigns" / "r3_prospective_context_v1" / "R3_SOURCE_DEPENDENCY_MATRIX_V2_FORCEORDER.json"
OLD_MATRIX = ROOT / "campaigns" / "r3_prospective_context_v1" / "R3_SOURCE_DEPENDENCY_MATRIX.json"


def test_forceorder_matrix_supersedes_immutable_v1_and_matches_helper() -> None:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    old_sha = hashlib.sha256(OLD_MATRIX.read_bytes()).hexdigest()
    assert matrix["supersedes"] == OLD_MATRIX.name
    assert matrix["superseded_sha256"] == old_sha
    assert matrix["forceorder_contract"]["stream"] == "liquidation"
    assert matrix["forceorder_contract"]["accepted_st_tokens"] == [1, "1", "UM", "USD-M", "USDⓈ-M"]
    for hypothesis in ("R3_H03", "R3_H04"):
        assert matrix["primary"][hypothesis]["identity_tuple"] == [
            "market_type", "symbol", "E_ms", "T_ms", "t_trade_id", "S", "o", "f", "q", "p", "ap", "X", "l", "z", "ps", "st"
        ]
        assert set(matrix["primary"][hypothesis]["canonical_order_keys"]) == set(identity.ORDER_ALLOWED)
