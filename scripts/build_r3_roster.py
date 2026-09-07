"""Build a content-addressed causal R3 monthly UM roster."""

from __future__ import annotations

import argparse
from pathlib import Path

from binance_research.r3_universe import build_causal_monthly_roster, write_roster_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="completed prior-month ranking CSV")
    parser.add_argument("--effective-month", required=True, help="roster month, YYYY-MM")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roster = build_causal_monthly_roster(args.source, effective_month=args.effective_month)
    write_roster_artifact(roster, args.output, source_path=args.source)
    print(f"effective_month={roster.effective_month}")
    print(f"symbols={len(roster.symbols)}")
    print(f"source_sha256={roster.source_sha256}")
    print(f"roster_sha256={roster.roster_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
