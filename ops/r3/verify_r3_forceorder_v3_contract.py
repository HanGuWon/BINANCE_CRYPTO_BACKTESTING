"""Verify the synthetic, metadata-only ForceOrder V3 contract.

This verifier intentionally constructs official-shaped fixtures in memory. It
does not open the active collection root, a checkpoint, a response value, or a
holdout row.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for import_root in (SRC, ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from binance_research.collector import (  # noqa: E402
    observed_forceorder_pressure_v3,
    route_liquidation_event_v3,
)
from ops.r3 import r3_forceorder_identity_v3 as identity  # noqa: E402
from ops.r3.build_r3_evidence_inventory import build_forceorder_metadata  # noqa: E402


MATRIX = ROOT / "campaigns" / "r3_prospective_context_v1" / "R3_SOURCE_DEPENDENCY_MATRIX_V3_FORCEORDER.json"
FORBIDDEN_OUTPUT_TOKENS = ("return", "pnl", "sharpe", "outcome", "holdout", "r2b2")


def _payload(*, symbol: str, pair: str, subtype: int, event_ms: int, top_level: bool = True) -> dict[str, Any]:
    order: dict[str, Any] = {
        "s": symbol,
        "S": "SELL",
        "o": "LIMIT",
        "f": "IOC",
        "q": "1.0000",
        "p": "100.00",
        "ap": "100.0",
        "X": "FILLED",
        "l": "1",
        "z": "1.000",
        "T": event_ms,
        "t": 0,
        "m": False,
        "wt": "CONTRACT_PRICE",
        "ot": "LIMIT",
    }
    payload: dict[str, Any] = {"e": "forceOrder", "E": event_ms, "o": order}
    if top_level:
        payload.update({"ps": pair, "st": subtype})
    else:
        order.update({"ps": pair, "st": subtype})
    return payload


def _envelope(payload: dict[str, Any], *, market: str, symbol: str) -> dict[str, Any]:
    return {
        "market_type": market,
        "symbol": symbol,
        "stream": "LIQUIDATION",
        "endpoint": "wss://fstream.binance.com/market/ws/!forceOrder@arr",
        "collector_receipt_time": "1970-01-01T00:00:00.001Z",
        "continuity_state": "COMPLETE",
        "payload": payload,
    }


def _assert_reject(payload: dict[str, Any], reason: str) -> None:
    try:
        identity.normalize_forceorder_payload_v3(payload)
    except identity.ForceOrderIdentityV3Error as exc:
        if exc.reason != reason:
            raise AssertionError(f"expected {reason}, got {exc.reason}") from exc
    else:
        raise AssertionError(f"expected V3 rejection {reason}")


def verify() -> dict[str, Any]:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    expected_tuple = [
        "market_type", "event_type", "event_symbol", "pair_symbol", "E_ms",
        "T_ms", "t_trade_id", "S", "o", "f", "q", "p", "ap", "X",
        "l", "z", "st",
    ]
    if matrix["forceorder_contract"]["identity_tuple"] != expected_tuple:
        raise AssertionError("V3 matrix identity tuple drifted")

    um_payload = _payload(symbol="BTCUSDT", pair="BTCUSDT", subtype=1, event_ms=1)
    cm_payload = _payload(symbol="BTCUSD_PERP", pair="BTCUSD", subtype=2, event_ms=2)
    legacy_payload = _payload(symbol="ETHUSDT", pair="ETHUSDT", subtype=1, event_ms=3, top_level=False)

    parsed_um, normalized_um = identity.normalize_forceorder_payload_v3(um_payload)
    if parsed_um[0] != "um" or normalized_um["ps"] != "BTCUSDT" or normalized_um["st"] != 1:
        raise AssertionError("UM parser normalization mismatch")
    parsed_cm, normalized_cm = identity.normalize_forceorder_payload_v3(cm_payload)
    if parsed_cm[0] != "cm" or normalized_cm["ps"] != "BTCUSD" or normalized_cm["st"] != 2:
        raise AssertionError("CM parser normalization mismatch")
    parsed_legacy, normalized_legacy = identity.normalize_forceorder_payload_v3(legacy_payload)
    if parsed_legacy[0] != "um" or normalized_legacy["ps"] != "ETHUSDT":
        raise AssertionError("legacy nested fallback mismatch")

    if route_liquidation_event_v3(um_payload) != ("um", "BTCUSDT"):
        raise AssertionError("UM collector route mismatch")
    if route_liquidation_event_v3(cm_payload) != ("cm", "BTCUSD_PERP"):
        raise AssertionError("CM collector route mismatch")
    observed = observed_forceorder_pressure_v3(cm_payload)
    if observed["market"] != parsed_cm[0] or observed["symbol"] != parsed_cm[2] or observed["pair_symbol"] != parsed_cm[3] or observed["subtype"] != parsed_cm[16]:
        raise AssertionError("collector/parser field mismatch")
    if observed["trade_order_time"] != 2 or observed["position_side"] is not None:
        raise AssertionError("collector used a wrong timestamp or position-side field")

    um_envelope = _envelope(um_payload, market="UM", symbol="BTCUSDT")
    cm_envelope = _envelope(cm_payload, market="CM", symbol="BTCUSD_PERP")
    legacy_envelope = _envelope(legacy_payload, market="UM", symbol="ETHUSDT")
    duplicate = copy.deepcopy(um_envelope)
    duplicate["collector_receipt_time"] = "1970-01-01T00:00:00.002Z"
    complete = {datetime(1970, 1, 1, 0, 15, tzinfo=UTC)}
    metadata = build_forceorder_metadata([um_envelope, duplicate, cm_envelope, legacy_envelope], identity_version="v3", complete_bar_opens=complete)
    if metadata["identity_key_version"] != "forceorder:v3" or metadata["unique_event_count"] != 3 or metadata["duplicate_envelope_count"] != 1:
        raise AssertionError("inventory V3 metadata accounting mismatch")
    if metadata["representative_market_counts"] != {"cm": 1, "um": 2}:
        raise AssertionError("inventory V3 market accounting mismatch")

    pair_conflict = copy.deepcopy(um_payload)
    pair_conflict["o"]["ps"] = "ETHUSDT"
    _assert_reject(pair_conflict, "PAIR_SYMBOL_CONFLICT")
    st_conflict = copy.deepcopy(um_payload)
    st_conflict["o"]["st"] = 2
    _assert_reject(st_conflict, "ST_CONFLICT")
    symbol_conflict = copy.deepcopy(um_payload)
    symbol_conflict["o"]["s"] = "ETHUSDT"
    _assert_reject(symbol_conflict, "SYMBOL_PAIR_MISMATCH")
    missing_st = copy.deepcopy(um_payload)
    missing_st.pop("st")
    missing_st["o"].pop("st", None)
    _assert_reject(missing_st, "ST_MISSING")

    original_hash = identity._sha256_text
    try:
        identity._sha256_text = lambda _value: "f" * 64  # type: ignore[assignment]
        collision = identity.deduplicate_forceorders_v3([
            _envelope(_payload(symbol="BTCUSDT", pair="BTCUSDT", subtype=1, event_ms=10), market="UM", symbol="BTCUSDT"),
            _envelope(_payload(symbol="BTCUSDT", pair="BTCUSDT", subtype=1, event_ms=11), market="UM", symbol="BTCUSDT"),
        ])
    finally:
        identity._sha256_text = original_hash  # type: ignore[assignment]
    if collision.collision_envelope_count != 2 or not collision.invariant_ok:
        raise AssertionError("V3 collision accounting mismatch")

    return {
        "status": "PASS",
        "matrix": MATRIX.name,
        "fixture_counts": {"um_official": 1, "cm_official": 1, "legacy_nested": 1, "contradictions": 3, "replay": 1, "collision_members": 2},
        "parser_collector_inventory_agreement": True,
        "active_root_accessed": False,
        "performance_values_accessed": False,
        "final_holdout_accessed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify()
    if args.output is not None:
        output = args.output.resolve()
        lowered = str(output).replace("\\", "/").lower()
        if any(token in lowered for token in FORBIDDEN_OUTPUT_TOKENS):
            raise ValueError(f"forbidden output path: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise ValueError(f"refusing to overwrite {output}")
        output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("R3_FORCEORDER_V3_CHECK=" + result["status"])
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

