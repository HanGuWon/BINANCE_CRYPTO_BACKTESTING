"""Outcome-blind historical parity through the repaired R3 discovery path.

This command is intentionally separate from the production executor.  It uses
the same month-scoped Binance Vision inventory and verifier, but writes only to
a fresh D-backed qualification root and emits a compact parity receipt.  It
never reads outcome or holdout artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from scripts import prepare_r3_post_boundary_launch as executor
from scripts.qualify_r3_forward_ranking import build_forward_ranking_from_verified_source, ranking_semantic_sha256
from binance_research.r3_universe import build_causal_monthly_roster, replay_roster_artifact


DEFAULT_WORK_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_forward_rank_work_discovery_preflight")
DEFAULT_RAW_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\raw")
DEFAULT_CENSUS_DIR = executor.REPO_ROOT / "data/census/r1_full_history_v1"
DEFAULT_ROSTER = executor.REPO_ROOT / "campaigns/r3_prospective_context_v1/rosters/2026-08.json"
DEFAULT_RECEIPT = executor.REPO_ROOT / "campaigns/r3_prospective_context_v1/R3_AUGUST_DISCOVERY_PATH_HISTORICAL_PARITY_RECEIPT.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fresh_d_root(path: Path) -> Path:
    resolved = Path(path).resolve()
    if resolved.drive.upper() != "D:":
        raise ValueError(f"qualification root must be D-backed: {resolved}")
    if resolved.exists() and any(resolved.iterdir()):
        raise ValueError(f"qualification root is not fresh: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _base_receipt(*, source_month: str, effective_month: str, work_root: Path) -> dict[str, Any]:
    implementation = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    return {
        "source_month": source_month,
        "effective_month": effective_month,
        "work_root": str(work_root),
        "implementation_commit": implementation,
        "source_tree_sha256": executor._source_tree_sha256(),
        "registry_sha256": executor._registry_identity(),
        "ranking_input": "AUTHORITATIVE_MONTH_SCOPED_DISCOVERY",
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_STARTED",
    }


def _inventory_counts(inventory: dict[str, Any]) -> dict[str, int]:
    objects = inventory.get("discovered_objects", [])
    monthly = {str(item.get("symbol", "")).upper() for item in objects if item.get("source_mode") == "MONTHLY_ARCHIVE"}
    daily = {str(item.get("symbol", "")).upper() for item in objects if item.get("source_mode") == "DAILY_ARCHIVE_FALLBACK"}
    return {
        "historical_taxonomy_symbol_count": int(inventory.get("historical_taxonomy_symbol_count", 0)),
        "discovered_symbol_count": int(len(inventory.get("discovered_symbols", []))),
        "monthly_source_symbol_count": len(monthly),
        "daily_fallback_symbol_count": len(daily),
        "no_historical_source_symbol_count": int(inventory.get("no_historical_source_symbol_count", 0)),
    }


def run_preflight(*, source_month: str, effective_month: str, work_root: Path, raw_root: Path, census_dir: Path, committed_roster: Path, receipt_path: Path) -> dict[str, Any]:
    work_root = _fresh_d_root(work_root)
    receipt = _base_receipt(source_month=source_month, effective_month=effective_month, work_root=work_root)
    context = {
        "control_root": str(work_root),
        "source_output_dir": str(work_root / "source"),
        "raw_root": str(raw_root),
        "census_dir": str(census_dir),
        "source_month": source_month,
    }
    acquisition: dict[str, Any] | None = None
    try:
        acquisition = executor._acquire_month_source(context, source_month)
        inventory = json.loads(Path(acquisition["inventory_path"]).read_text(encoding="utf-8"))
        receipt.update(_inventory_counts(inventory))
        receipt["discovery_inventory_path"] = acquisition["inventory_path"]
        receipt["discovery_inventory_sha256"] = _sha256(Path(acquisition["inventory_path"]))
        verification = executor._verify_month_source({**context, "AUGUST_SOURCE_ACQUISITION": acquisition}, source_month)
        verification_path = Path(verification["receipt_path"])
        verification_payload = json.loads(verification_path.read_text(encoding="utf-8"))
        receipt.update({
            "verified_source_manifest_path": acquisition["manifest_path"],
            "verified_source_manifest_sha256": _sha256(Path(acquisition["manifest_path"])),
            "verified_source_receipt_path": verification["receipt_path"],
            "verified_source_receipt_sha256": _sha256(verification_path),
            "complete_source_eligible_symbol_count": int(verification_payload.get("complete_source_eligible_symbol_count", 0)),
            "partial_source_symbol_count": int(verification_payload.get("partial_source_symbol_count", 0)),
            "source_integrity_blocker_count": int(verification_payload.get("source_integrity_blocker_count", 0)),
        })
        ranking_dir = work_root / "ranking"
        ranking_path = build_forward_ranking_from_verified_source(verification_path, census_dir, ranking_dir, effective_month=effective_month)
        ranking_frame = pd.read_csv(ranking_path)
        generated = build_causal_monthly_roster(ranking_path, effective_month=effective_month)
        committed = replay_roster_artifact(committed_roster, effective_month=effective_month)
        parity = generated.symbols == committed.symbols and generated.roster_sha256 == committed.roster_sha256
        receipt.update({
            "ranking_artifact_path": str(ranking_path.resolve()),
            "ranking_artifact_sha256": _sha256(ranking_path),
            "ranking_semantic_sha256": ranking_semantic_sha256(ranking_frame, effective_month=effective_month, selected_only=False),
            "resulting_roster_logical_sha256": generated.roster_sha256,
            "committed_roster_logical_sha256": committed.roster_sha256,
            "resulting_roster_symbol_count": len(generated.symbols),
            "committed_roster_symbol_count": len(committed.symbols),
            "parity": "PASS" if parity else "FAIL",
            "status": "PASS" if parity else "BLOCKED",
            "terminal_state": "R3_READY_DISCOVERY_PATH_PARITY" if parity else "R3_BLOCKED_DISCOVERY_PATH_PARITY",
        })
        if not parity:
            receipt["parity_mismatch_symbols"] = sorted(set(generated.symbols) ^ set(committed.symbols))
    except executor.PostBoundaryBlocked as exc:
        receipt.update({"status": "BLOCKED", "terminal_state": "R3_BLOCKED_DISCOVERY_PATH_PARITY", "block_code": exc.code, "block_reason": exc.reason})
    except Exception as exc:
        receipt.update({"status": "BLOCKED", "terminal_state": "R3_BLOCKED_DISCOVERY_PATH_PARITY", "block_code": type(exc).__name__, "block_reason": str(exc)})
    receipt_path = Path(receipt_path)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Outcome-blind R3 discovery-path parity preflight")
    parser.add_argument("--source-month", default="2026-07")
    parser.add_argument("--effective-month", default="2026-08")
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--census-dir", type=Path, default=DEFAULT_CENSUS_DIR)
    parser.add_argument("--committed-roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIP)
    args = parser.parse_args(argv)
    result = run_preflight(source_month=args.source_month, effective_month=args.effective_month, work_root=args.work_root, raw_root=args.raw_root, census_dir=args.census_dir, committed_roster=args.committed_roster, receipt_path=args.receipt)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
