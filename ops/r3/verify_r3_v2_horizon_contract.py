"""Verify the frozen R3 V2 horizon/estimand contract without market data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / "campaigns/r3_prospective_context_v1"
V1 = CAMPAIGN / "R3_EVALUATION_AMENDMENT_V1.md"
PRIOR_V2 = CAMPAIGN / "R3_EVALUATION_AMENDMENT_V2.md"
PRIOR_MANIFEST = CAMPAIGN / "R3_EVALUATION_AMENDMENT_V2_REPRODUCIBILITY_MANIFEST.json"
V2 = CAMPAIGN / "R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL.md"
MAP = CAMPAIGN / "R3_EVALUATION_HORIZON_MAP_V1.json"
MANIFEST = CAMPAIGN / "R3_EVALUATION_AMENDMENT_V2_ADVERSARIAL_REPRODUCIBILITY_MANIFEST.json"
SUPERSEDED_MAP = CAMPAIGN / "R3_EVALUATION_HORIZON_MAP_V1_SUPERSEDED_20260905.json"

EXPECTED_V1 = "27276b4d3b66d25c987fadbac531df3cfd741dbd43625406fdc342e89c2f1c39"
EXPECTED_PRIOR_V2 = "8f12263c107e8b1fb2596c72f5c3e0c741a17339a42f95aab67df86b87738c38"
EXPECTED_PRIOR_MANIFEST = "ee840ad17dfaf246991f758d6420fd790f8bfcfaa0279ef4d2626ed5d93543a7"
EXPECTED_IMPLEMENTATION = "ecebc49dff41eeec33af62c2c85a75c5a0bd2922"
EXPECTED_SOURCE_TREE = "b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688"
EXPECTED_REGISTRY = "c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a"
EXPECTED_ROOT = r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8"
EXPECTED_LAUNCH_MANIFEST = "cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> dict[str, object]:
    required = [V1, PRIOR_V2, PRIOR_MANIFEST, V2, MAP, MANIFEST, SUPERSEDED_MAP]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"missing contract artifact(s): {missing}")
    if sha256(V1) != EXPECTED_V1:
        raise ValueError("V1 amendment hash changed")
    if sha256(PRIOR_V2) != EXPECTED_PRIOR_V2:
        raise ValueError("prior single-15m V2 hash changed")
    if sha256(PRIOR_MANIFEST) != EXPECTED_PRIOR_MANIFEST:
        raise ValueError("prior reproducibility manifest hash changed")
    horizon = json.loads(MAP.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    v2_text = V2.read_text(encoding="utf-8")
    keys = list(horizon.get("horizons", {}))
    if keys != ["H01", "H02", "H03", "H04", "H05", "H06"]:
        raise ValueError(f"horizon map keys are not exactly H01-H06: {keys}")
    if any(not horizon["horizons"][key].get("primary") for key in keys):
        raise ValueError("every horizon must be primary")
    if manifest.get("horizon_keys") != keys or manifest.get("primary_p_value_keys") != keys:
        raise ValueError("manifest does not pin the exact six-key family")
    if manifest.get("horizon_sha256") != sha256(MAP) or manifest.get("amendment_sha256") != sha256(V2):
        raise ValueError("manifest hash pins do not match current bytes")
    if manifest.get("superseded_single_15m_v2_manifest_sha256") != EXPECTED_PRIOR_MANIFEST:
        raise ValueError("old manifest supersession hash is missing")
    if manifest.get("superseded_horizon_sha256") != sha256(SUPERSEDED_MAP):
        raise ValueError("superseded map hash is missing")
    if manifest.get("frozen_implementation_commit") != EXPECTED_IMPLEMENTATION:
        raise ValueError("frozen implementation identity mismatch")
    if manifest.get("frozen_source_tree_sha256") != EXPECTED_SOURCE_TREE:
        raise ValueError("frozen source-tree identity mismatch")
    if manifest.get("frozen_registry_sha256") != EXPECTED_REGISTRY:
        raise ValueError("frozen registry identity mismatch")
    if str(manifest.get("scientific_root", "")).casefold() != EXPECTED_ROOT.casefold():
        raise ValueError("scientific root identity mismatch")
    if manifest.get("launch_manifest_sha256") != EXPECTED_LAUNCH_MANIFEST or manifest.get("launch_seal_status") != "SEALED":
        raise ValueError("launch manifest/seal identity mismatch")
    if horizon.get("source_available_rule") != "source_available_time < next_executable_open_time":
        raise ValueError("strict source availability rule is not frozen")
    v2_lower = " ".join(v2_text.lower().split())
    required_phrases = (
        "rank exactly 2",
        "the four cells",
        "candidate forceorder event universe",
        "h04 endpoint",
        "finite, nonzero btc return",
        "inclusive two-sided tail",
        "count(|t_boot| >= |t_obs|)",
        "exactly six",
    )
    missing_phrases = [phrase for phrase in required_phrases if phrase not in v2_lower]
    if missing_phrases:
        raise ValueError(f"V2 is missing required frozen rule(s): {missing_phrases}")
    return {
        "status": "PASS",
        "horizon_keys": keys,
        "primary_p_value_count": manifest.get("primary_p_value_count"),
        "v1_sha256": sha256(V1),
        "prior_v2_sha256": sha256(PRIOR_V2),
        "prior_manifest_sha256": sha256(PRIOR_MANIFEST),
        "v2_sha256": sha256(V2),
        "horizon_map_sha256": sha256(MAP),
        "superseded_map_sha256": sha256(SUPERSEDED_MAP),
        "outcome_values_accessed": False,
        "final_holdout_status": "UNTOUCHED",
        "r2b2_status": "NOT_STARTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(json.dumps(verify(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
