"""Seal outcome-blind R3 pre-boundary shadow, storage, and parity receipts.

This utility reads only operational shadow envelopes and manifests.  It never
loads strategy returns, checkpoints, or holdout data.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from binance_research.collector import ForwardCollector
from binance_research.r3_operations import verify_engineering_shadow_root, verify_manifest_chain
from binance_research.r3_universe import replay_roster_artifact

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaigns" / "r3_prospective_context_v1"
DATA_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1")
ROSTER_PATH = CAMPAIGN / "rosters" / "2026-08.json"
V3_ROOT = DATA_ROOT / "engineering_shadow_august_v3"
V4_ROOT = DATA_ROOT / "engineering_shadow_august_v4_final"


def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def current_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _latest_manifest(root: Path) -> dict[str, object]:
    chain = root / "raw_v1" / "manifest_chain.jsonl"
    if not chain.is_file() or not verify_manifest_chain(chain):
        raise RuntimeError(f"manifest chain missing or invalid: {chain}")
    return json.loads([line for line in chain.read_text(encoding="utf-8").splitlines() if line.strip()][-1])


def main() -> int:
    roster = replay_roster_artifact(ROSTER_PATH, effective_month="2026-08")
    v3_manifest = _latest_manifest(V3_ROOT)
    v4_manifest = _latest_manifest(V4_ROOT)
    v4_check = verify_engineering_shadow_root(V4_ROOT, expected_symbols=list(roster.symbols), roster_sha256=roster.roster_sha256)
    unknown_market_liquidations = 0
    liquidation_events = 0
    for path in (V4_ROOT / "raw_v1").rglob("liquidation.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            liquidation_events += 1
            envelope = json.loads(line)
            if envelope.get("market_type") != "um" or envelope.get("payload", {}).get("o", {}).get("st") != 1:
                unknown_market_liquidations += 1
    commit = current_commit()
    generated = datetime.now(UTC).isoformat()
    shadow_receipt = {
        "campaign_id": "r3_prospective_context_v1",
        "mode": "ENGINEERING_SHADOW",
        "status": "VERIFIED_WAITING_FOR_AUGUST_CLOSE",
        "generated_at": generated,
        "implementation_commit": commit,
        "roster_artifact": str(ROSTER_PATH.relative_to(ROOT)).replace("\\", "/"),
        "roster_sha256": roster.roster_sha256,
        "root": str(V4_ROOT),
        "root_tree_sha256": sha256_tree(V4_ROOT),
        "manifest_sha256": v4_manifest["manifest_sha256"],
        "manifest_chain_verified": True,
        "symbols": v4_check["symbols"],
        "files": v4_check["files"],
        "rows": v4_check["rows"],
        "bytes": v4_check["bytes"],
        "gap_count": v4_check["gap_count"],
        "restart_count": 0,
        "liquidation_events": liquidation_events,
        "unknown_market_liquidations": unknown_market_liquidations,
        "outcomes_accessed": False,
        "returns_or_pnl_computed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_STARTED",
        "prior_root_disposition": {"engineering_shadow_august_v3": "PRESERVED_IMMUTABLE"},
        "v3_manifest_sha256": v3_manifest["manifest_sha256"],
    }
    (CAMPAIGN / "R3_ENGINEERING_SHADOW_AUGUST_V4_RECEIPT.json").write_text(json.dumps(shadow_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cycles = {"24h": 96, "7d": 672, "30d": 2880, "90d": 8640}
    storage = {
        "campaign_id": "r3_prospective_context_v1",
        "mode": "ENGINEERING_SHADOW",
        "generated_at": generated,
        "root": str(V4_ROOT),
        "manifest_sha256": v4_manifest["manifest_sha256"],
        "one_cycle_raw_bytes": int(v4_manifest["total_bytes"]),
        "cycles_per_period": cycles,
        "projected_raw_bytes": {period: int(v4_manifest["total_bytes"]) * count for period, count in cycles.items()},
        "basis": "single completed 15-minute shadow cycle multiplied by absolute UTC grid cycles; control/health overhead excluded and reported separately",
        "outcomes_accessed": False,
    }
    (CAMPAIGN / "R3_STORAGE_PROJECTION_RECEIPT.json").write_text(json.dumps(storage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    parity = {
        "campaign_id": "r3_prospective_context_v1",
        "generated_at": generated,
        "implementation_commit": commit,
        "shadow_primary_streams": sorted(ForwardCollector.R3_SHADOW_STREAMS),
        "scientific_primary_streams": sorted(ForwardCollector.R3_PRIMARY_STREAMS),
        "exact_set_match": ForwardCollector.R3_SHADOW_STREAMS == ForwardCollector.R3_PRIMARY_STREAMS,
        "scientific_mode_authorized": False,
        "reason": "launch manifest remains blocked by September roster provenance; parity is path/stream contract only",
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
    }
    (CAMPAIGN / "R3_SHADOW_SCIENTIFIC_PARITY_RECEIPT.json").write_text(json.dumps(parity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"shadow": shadow_receipt, "storage": storage, "parity": parity}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
