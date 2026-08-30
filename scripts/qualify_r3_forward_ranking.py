"""Outcome-blind parity qualification for the causal R3 monthly ranker."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from binance_research.r3_universe import build_causal_monthly_roster, replay_roster_artifact
from binance_research.data import load_kline_archive, validate_klines
from build_r16_1d_universe import _summarize_1d_archive, build_monthly_cohorts


def build_forward_ranking_from_raw(raw_root: Path, census_dir: Path, output_dir: Path, *, effective_month: str) -> Path:
    """Rebuild a causal ranking from verified native 1d archives."""
    prior_month = str(pd.Period(effective_month, freq="M") - 1)
    rows: list[dict[str, object]] = []
    for path in sorted(Path(raw_root).glob(f"um/klines/*/1d/*-1d-{prior_month}.zip")):
        market = path.parts[-5]
        if market != "um":
            raise RuntimeError(f"R3_RANKING_SCOPE_MISMATCH:{path}")
        symbol = path.parent.parent.name
        sidecar = path.with_suffix(path.suffix + ".manifest.json")
        if not sidecar.is_file():
            raise RuntimeError(f"MISSING_ARCHIVE_MANIFEST:{path}")
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        computed = hashlib.sha256(path.read_bytes()).hexdigest()
        if metadata.get("market_type") != market or metadata.get("dataset") != "klines" or metadata.get("interval") != "1d":
            raise RuntimeError(f"ARCHIVE_MANIFEST_SCOPE_MISMATCH:{path}")
        if metadata.get("computed_sha256") != computed or metadata.get("published_sha256") != computed:
            raise RuntimeError(f"CHECKSUM_MISMATCH:{path}")
        issues = validate_klines(load_kline_archive(path), "1d")
        errors = [issue for issue in issues if issue.severity == "ERROR"]
        if errors:
            raise RuntimeError(f"INVALID_1D_ARCHIVE:{path}:{';'.join(issue.code for issue in errors)}")
        summary = _summarize_1d_archive(path)
        expected_days = pd.Period(prior_month, freq="M").days_in_month
        if int(summary["observed_days"]) != expected_days:
            # The canonical selector only admits complete prior months. Keep
            # the object in the audit manifest, but exclude it from rank.
            rows.append({"market": market, "symbol": symbol, "archive_month": prior_month,
                         "raw_path": str(path), "published_sha256": computed,
                         "computed_sha256": computed, "integrity_status": "PARTIAL",
                         "issue_codes": "INCOMPLETE_PRIOR_MONTH", "row_count": summary["row_count"]})
            continue
        rows.append({"market": market, "symbol": symbol, "archive_month": prior_month,
                     "raw_path": str(path), "published_sha256": computed,
                     "computed_sha256": computed, "integrity_status": summary["integrity_status"],
                     "issue_codes": summary["issue_codes"], "row_count": summary["row_count"]})
    if not rows:
        raise RuntimeError(f"NO_RAW_1D_ARCHIVES:{prior_month}")
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_dir / "raw_1d_manifest.csv", index=False)
    taxonomy = pd.read_csv(census_dir / "um_archive_symbol_census.csv")
    taxonomy["market"] = "um"
    ranked = build_monthly_cohorts(pd.DataFrame(rows), taxonomy, output_dir, census_dir=census_dir)
    ranked_path = output_dir / "universe_monthly.csv"
    if not ranked_path.is_file() or ranked.empty:
        raise RuntimeError("RAW_RANKING_EMPTY")
    return ranked_path


def qualify(source: Path, august_roster: Path, *, months: tuple[str, ...] = ("2025-06", "2025-08", "2026-07", "2026-08")) -> dict[str, object]:
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
    parser.add_argument("--raw-root", type=Path, help="root containing native um/klines/*/1d archives")
    parser.add_argument("--census-dir", type=Path, default=Path("data/census/r1_full_history_v1"))
    parser.add_argument("--effective-month", default="2026-08")
    args = parser.parse_args()
    if args.raw_root is not None:
        with TemporaryDirectory(prefix="r3-forward-ranking-") as temp:
            ranked = build_forward_ranking_from_raw(args.raw_root, args.census_dir, Path(temp), effective_month=args.effective_month)
            result = qualify(ranked, args.august_roster, months=(args.effective_month,))
            result["ranking_input"] = "native_raw_1d_archives"
            result["raw_manifest_sha256"] = hashlib.sha256((Path(temp) / "raw_1d_manifest.csv").read_bytes()).hexdigest()
    else:
        result = qualify(args.source, args.august_roster)
        result["ranking_input"] = "precomputed_artifact_control_only"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
