"""Outcome-blind parity qualification for the causal R3 monthly ranker."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from binance_research.r3_universe import build_causal_monthly_roster, replay_roster_artifact


def qualify(source: Path, august_roster: Path) -> dict[str, object]:
    months = ("2025-06", "2025-08", "2026-07", "2026-08")
    results = []
    for month in months:
        roster = build_causal_monthly_roster(source, effective_month=month)
        results.append({"effective_month": month, "symbols": len(roster.symbols), "roster_sha256": roster.roster_sha256})
    generated = build_causal_monthly_roster(source, effective_month="2026-08")
    committed = replay_roster_artifact(august_roster, effective_month="2026-08")
    if generated.roster_sha256 != committed.roster_sha256 or generated.symbols != committed.symbols:
        raise AssertionError("forward ranker does not reproduce committed August roster")
    return {"status": "PASS", "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "months": results, "august_roster_sha256": generated.roster_sha256, "september_roster": "NOT_BUILT_BEFORE_BOUNDARY", "outcomes_accessed": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--august-roster", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.source, args.august_roster)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
