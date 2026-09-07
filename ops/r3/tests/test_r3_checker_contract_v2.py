from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ops.r3.check_r3_evaluation_readiness import (
    FROZEN_IMPLEMENTATION_COMMIT,
    FROZEN_LAUNCH_MANIFEST_SHA256,
    FROZEN_REGISTRY_SHA256,
    FROZEN_SCIENTIFIC_ROOT,
    FROZEN_SOURCE_TREE_SHA256,
    PRIMARY_FAMILY_KEYS,
    ReadinessInputError,
    validate_primary_family_metadata,
)


def _triple() -> tuple[dict, dict, dict]:
    horizon_map = {
        "source_available_rule": "source_available_time < next_executable_open_time",
        "artifact_sha256": "h" * 64,
        "horizons": {key: {"primary": True} for key in PRIMARY_FAMILY_KEYS},
    }
    amendment = {
        "source_available_rule": "source_available_time < next_executable_open_time",
        "amendment_sha256": "a" * 64,
        "evaluation_horizon_alternatives": [],
    }
    manifest = {
        "horizon_keys": list(PRIMARY_FAMILY_KEYS),
        "primary_p_value_keys": list(PRIMARY_FAMILY_KEYS),
        "primary_p_value_count": 6,
        "horizon_sha256": "h" * 64,
        "amendment_sha256": "a" * 64,
        "frozen_implementation_commit": FROZEN_IMPLEMENTATION_COMMIT,
        "frozen_source_tree_sha256": FROZEN_SOURCE_TREE_SHA256,
        "frozen_registry_sha256": FROZEN_REGISTRY_SHA256,
        "scientific_root": FROZEN_SCIENTIFIC_ROOT,
        "launch_manifest_sha256": FROZEN_LAUNCH_MANIFEST_SHA256,
        "launch_seal_status": "SEALED",
        "source_available_rule": "source_available_time < next_executable_open_time",
    }
    return amendment, horizon_map, manifest


def test_exact_six_primary_slots_and_identity_pins_pass() -> None:
    amendment, horizon_map, manifest = _triple()
    receipt = validate_primary_family_metadata(amendment, horizon_map, manifest)
    assert receipt["primary_family_keys"] == list(PRIMARY_FAMILY_KEYS)
    assert receipt["primary_p_value_count"] == 6


@pytest.mark.parametrize(
    "mutator",
    [
        lambda a, h, m: m["primary_p_value_keys"].append("H07"),
        lambda a, h, m: m.update({"component_p_values": {"spread": 0.1}}),
        lambda a, h, m: m.update({"horizon_sha256": "f" * 64}),
        lambda a, h, m: m.update({"frozen_registry_sha256": "f" * 64}),
        lambda a, h, m: m.update({"launch_seal_status": "OPEN"}),
        lambda a, h, m: m.update({"evaluation_horizon_alternatives": ["15m"]}),
    ],
)
def test_hidden_component_hash_identity_and_alternate_variants_fail(mutator) -> None:
    amendment, horizon_map, manifest = _triple()
    mutator(amendment, horizon_map, manifest)
    with pytest.raises(ReadinessInputError):
        validate_primary_family_metadata(amendment, horizon_map, manifest)


def test_source_open_substitution_and_missing_strict_rule_fail() -> None:
    amendment, horizon_map, manifest = _triple()
    amendment["text"] = "source_open_time is substituted for availability"
    with pytest.raises(ReadinessInputError, match="source_open_time"):
        validate_primary_family_metadata(amendment, horizon_map, manifest)
    amendment, horizon_map, manifest = _triple()
    horizon_map["source_available_rule"] = "backward_to_completed_bar_decision_time"
    manifest["source_available_rule"] = "backward_to_completed_bar_decision_time"
    amendment["source_available_rule"] = "backward_to_completed_bar_decision_time"
    with pytest.raises(ReadinessInputError, match="source availability"):
        validate_primary_family_metadata(amendment, horizon_map, manifest)


def test_exact_order_and_primary_flags_are_required() -> None:
    amendment, horizon_map, manifest = _triple()
    horizon_map["horizons"] = {key: {"primary": True} for key in reversed(PRIMARY_FAMILY_KEYS)}
    with pytest.raises(ReadinessInputError):
        validate_primary_family_metadata(amendment, horizon_map, manifest)
    amendment, horizon_map, manifest = _triple()
    horizon_map["horizons"]["H03"]["primary"] = False
    with pytest.raises(ReadinessInputError):
        validate_primary_family_metadata(amendment, horizon_map, manifest)


def test_inventory_verifier_is_deterministic_and_metadata_only() -> None:
    root = Path(__file__).resolve().parents[3]
    command = [sys.executable, str(root / "ops" / "r3" / "verify_r3_inventory_contract.py")]
    first = subprocess.check_output(command, cwd=root, text=True)
    second = subprocess.check_output(command, cwd=root, text=True)
    assert json.loads(first) == json.loads(second)
    payload = json.loads(first)
    assert payload["status"] == "PASS" and payload["metadata_only"] is True and payload["root_accessed"] is False


def test_checker_source_has_no_materializer_or_executor_import() -> None:
    source = Path(__file__).resolve().parents[1] / "check_r3_evaluation_readiness.py"
    text = source.read_text(encoding="utf-8").lower()
    assert "import materializer" not in text and "import executor" not in text
