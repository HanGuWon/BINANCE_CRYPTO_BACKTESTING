"""Check recorded v8 identity metadata without touching the live process/root."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX = REPO_ROOT / "campaigns/r3_prospective_context_v1/operations/SOL_AUDIT_WP3_PROVENANCE_INDEX_20260905.json"
CAMPAIGN = REPO_ROOT / "campaigns/r3_prospective_context_v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-only", action="store_true", required=True)
    args = parser.parse_args(argv)
    if not args.metadata_only:
        raise SystemExit("--metadata-only is required")
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    identity = index["active_v8_identity"]
    spec = (CAMPAIGN / "campaign_spec.toml").read_text(encoding="utf-8")
    expected = {
        "implementation_commit": "ecebc49dff41eeec33af62c2c85a75c5a0bd2922",
        "source_tree_sha256": "b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688",
        "registry_sha256": "c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a",
        "causal_or_data_root": "D:/BINANCE_CRYPTO_BACKTESTING_DATA/r3_prospective_context_v1/scientific_raw_v8",
        "launch_manifest_sha256": "cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659",
        "seal_sha256": "ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85",
        "status": "CURRENT_FROZEN",
    }
    mismatches = {key: {"expected": value, "actual": identity.get(key)} for key, value in expected.items() if identity.get(key) != value}
    guards = {
        "final_holdout_status": index.get("final_holdout_status"),
        "outcome_values_accessed": index.get("outcome_values_accessed"),
        "r2b2_status": index.get("r2b2_status"),
        "campaign_spec_has_un_touched_holdout": 'final_holdout_status = "UNTOUCHED"' in spec,
        "campaign_spec_has_not_started_outcomes": 'r2b2_status = "NOT_STARTED"' in spec and 'outcome_analysis_status = "NOT_STARTED"' in spec,
    }
    result = {
        "status": "PASS" if not mismatches and guards["final_holdout_status"] == "UNTOUCHED" and guards["outcome_values_accessed"] is False and guards["r2b2_status"] == "NOT_STARTED" and guards["campaign_spec_has_un_touched_holdout"] and guards["campaign_spec_has_not_started_outcomes"] else "FAIL",
        "metadata_only": True,
        "process_touched": False,
        "raw_root_opened": False,
        "checkpoint_paths_checked": False,
        "active_identity": identity,
        "guards": guards,
        "mismatches": mismatches,
        "index_sha256": _sha256(INDEX),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
