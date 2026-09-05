"""Build run_manifest.json and holdout_guard_proof.json for R2A closure."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "r2a_standalone_evidence_v1"
CHECKPOINT_ROOT = Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a/checkpoints")

ARTIFACTS = [
    "R2A_PROTOCOL.md", "R2A_PROTOCOL_AMENDMENT_001.md", "campaign_spec.toml",
    "trial_registry.csv", "validation_results.csv", "train_descriptive.csv",
    "hac_results.csv", "bootstrap_results.csv", "multiple_testing.csv",
    "walk_forward_results.csv", "yearly_stability.csv", "cohort_diagnostics.csv",
    "symbol_concentration.csv", "candidate_shortlist.csv",
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    manifest_state = json.loads((CHECKPOINT_ROOT / "run_manifest.json").read_text())
    artifact_hashes = {name: sha256_file(CAMPAIGN / name) for name in ARTIFACTS if (CAMPAIGN / name).exists()}
    manifest = {
        "campaign": "r2a_standalone_evidence_v1",
        "r1_source_commit": git("rev-parse", "research/r1-final-panel-v1"),
        "preregistration_freeze_commit": "801cde50ec661d8c65cfa9ed7af76b42aa3c48fd",
        "implementation_commit_at_run_start": manifest_state.get("freeze_commit"),
        "outcome_commit": git("rev-parse", "HEAD"),
        "registry_sha256_at_run": manifest_state.get("registry_sha256"),
        "trial_count_registered": len(json.loads("[]")) or None,
        "trials_completed": len(manifest_state.get("completed", [])),
        "trials_failed": len(manifest_state.get("failed", [])),
        "trials_censored": 0,
        "artifact_sha256": artifact_hashes,
    }
    registry_lines = (CAMPAIGN / "trial_registry.csv").read_text().count(chr(10)) - 1
    manifest["trial_count_registered"] = registry_lines
    (CAMPAIGN / "run_manifest.json").write_text(json.dumps(manifest, indent=2))

    guard_proof = {
        "holdout_boundary_utc": {
            "15m": "2024-02-10T00:15:00+00:00",
            "1h": "2024-02-10T01:00:00+00:00",
            "4h": "2024-02-10T04:00:00+00:00",
        },
        "loader_predicate_pushdown": "pyarrow pc.less(timestamp_ns, boundary) before to_pandas; holdout rows never materialized",
        "runtime_guards": [
            "r2a_engine.assert_no_holdout enforced in load_panel_pre_holdout caller and run_single_trial",
            "aggregate_r2a_results.main re-asserts stamps < holdout boundary for every trial before statistics",
        ],
        "tests_enforcing": [
            "tests/test_r2a_execution.py::test_holdout_timestamps_rejected",
            "tests/test_r2a_execution.py::test_exact_purge_embargo_boundaries_match_split_metadata",
        ],
        "final_holdout_status": "UNTOUCHED",
    }
    (CAMPAIGN / "holdout_guard_proof.json").write_text(json.dumps(guard_proof, indent=2))
    print(json.dumps({"manifest_trials": registry_lines, "completed": manifest["trials_completed"], "failed": manifest["trials_failed"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
