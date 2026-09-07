"""Verify the R3 V2 inventory contract on constructed metadata only.

This verifier deliberately does not open the scientific context root, response
streams, labels, or outcome artifacts.  It exercises the strict gap and
per-hypothesis schema with a synthetic inventory and hashes the superseding
dependency matrix for provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ops.r3.check_r3_evaluation_readiness import (
    FROZEN_IMPLEMENTATION_COMMIT,
    FROZEN_LAUNCH_MANIFEST_SHA256,
    FROZEN_REGISTRY_SHA256,
    FROZEN_SCIENTIFIC_ROOT,
    FROZEN_SOURCE_TREE_SHA256,
    PRIMARY_FAMILY_KEYS,
    PRIMARY_HYPOTHESES,
    validate_per_hypothesis_gates,
    validate_primary_family_metadata,
    validate_scoped_gap_blocks,
)


MATRIX = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "R3_SOURCE_DEPENDENCY_MATRIX_V2_FORCEORDER.json"
HORIZON_MAP = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "R3_EVALUATION_HORIZON_MAP_V1.json"
AMENDMENT = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL.md"
MANIFEST = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL_REPRODUCIBILITY_MANIFEST.json"
FORBIDDEN_OUTPUT_TOKENS = ("holdout", "r2b2", "gross_return", "net_return", "pnl", "sharpe", "outcome")


def _synthetic_inventory() -> dict[str, Any]:
    blocks = [f"2026-01-{index:02d}T00:00:00+00:00" for index in range(1, 31)]
    used_sha = "a" * 64
    hypotheses = {hypothesis: list(blocks) for hypothesis in PRIMARY_HYPOTHESES}
    days = {hypothesis: [f"2026-01-{index:02d}" for index in range(1, 31)] for hypothesis in PRIMARY_HYPOTHESES}
    contributions = {hypothesis: {used_sha: {"effective_month": "2026-09", "complete_count": 1}} for hypothesis in PRIMARY_HYPOTHESES}
    return {
        "calendar": {"independent_utc_days": 30, "independent_utc_6h_blocks": 120},
        "gap_blocks_by_scope": {"R3_H01": ["2026-01-01T00:00:00+00:00"]},
        "availability_and_gaps": {
            "gap_records": [{
                "category": "SOURCE_UNAVAILABLE", "stream": "book_ticker",
                "start_time": "2026-01-01T00:01:00+00:00", "end_time": None,
                "utc_6h_block_ids": ["2026-01-01T00:00:00+00:00"], "scopes": ["R3_H01"],
            }],
            "gap_accounting_complete": True,
            "health_gap_count": 1,
            "health_restart_count": 0,
            "source_unavailable_records": 1,
        },
        "streams": {}, "cycles": {},
        "usable_blocks_by_hypothesis": hypotheses,
        "usable_days_by_hypothesis": days,
        "roster_contribution_by_hypothesis": contributions,
    }


def _safe_output(path: Path) -> None:
    lowered = str(path).replace("\\", "/").lower()
    if any(token in lowered for token in FORBIDDEN_OUTPUT_TOKENS):
        raise ValueError(f"forbidden output path: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inventory = _synthetic_inventory()
    gaps = validate_scoped_gap_blocks(inventory)
    temporal = validate_per_hypothesis_gates(inventory, [{"effective_month": "2026-09", "roster_sha256": "a" * 64}])
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
        "horizon_keys": list(PRIMARY_FAMILY_KEYS), "primary_p_value_keys": list(PRIMARY_FAMILY_KEYS),
        "primary_p_value_count": len(PRIMARY_FAMILY_KEYS), "horizon_sha256": "h" * 64, "amendment_sha256": "a" * 64,
        "frozen_implementation_commit": FROZEN_IMPLEMENTATION_COMMIT,
        "frozen_source_tree_sha256": FROZEN_SOURCE_TREE_SHA256,
        "frozen_registry_sha256": FROZEN_REGISTRY_SHA256,
        "scientific_root": FROZEN_SCIENTIFIC_ROOT,
        "launch_manifest_sha256": FROZEN_LAUNCH_MANIFEST_SHA256,
        "launch_seal_status": "SEALED",
        "source_available_rule": "source_available_time < next_executable_open_time",
    }
    family = validate_primary_family_metadata(amendment, horizon_map, manifest)
    actual_horizon = json.loads(HORIZON_MAP.read_text(encoding="utf-8"))
    actual_manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual_horizon["artifact_sha256"] = hashlib.sha256(HORIZON_MAP.read_bytes()).hexdigest()
    actual_amendment = {"text": AMENDMENT.read_text(encoding="utf-8"), "amendment_sha256": hashlib.sha256(AMENDMENT.read_bytes()).hexdigest(), "evaluation_horizon_alternatives": []}
    actual_family = validate_primary_family_metadata(actual_amendment, actual_horizon, actual_manifest)
    matrix_sha = hashlib.sha256(MATRIX.read_bytes()).hexdigest() if MATRIX.is_file() else None
    result = {
        "status": "PASS", "metadata_only": True, "root_accessed": False,
        "gap_scope_count": len(gaps["gap_blocks_by_scope"]),
        "hypothesis_count": len(temporal["hypotheses"]),
        "primary_family_keys": family["primary_family_keys"],
        "actual_primary_family_keys": actual_family["primary_family_keys"],
        "matrix": str(MATRIX), "matrix_sha256": matrix_sha,
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        _safe_output(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise ValueError(f"refusing to overwrite {output}")
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
