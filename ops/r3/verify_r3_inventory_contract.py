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

from ops.r3.check_r3_evaluation_readiness import PRIMARY_HYPOTHESES, validate_per_hypothesis_gates, validate_scoped_gap_blocks


MATRIX = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "R3_SOURCE_DEPENDENCY_MATRIX_V2_FORCEORDER.json"
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
    matrix_sha = hashlib.sha256(MATRIX.read_bytes()).hexdigest() if MATRIX.is_file() else None
    result = {
        "status": "PASS", "metadata_only": True, "root_accessed": False,
        "gap_scope_count": len(gaps["gap_blocks_by_scope"]),
        "hypothesis_count": len(temporal["hypotheses"]),
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
