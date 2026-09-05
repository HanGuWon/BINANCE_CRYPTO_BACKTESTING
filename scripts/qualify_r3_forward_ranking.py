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
from binance_research.panel import select_verified_causal_liquidity_universe

SEMANTIC_FIELDS = ("market", "symbol", "volume_month", "universe_month", "coverage_ratio",
                   "prior_month_quote_volume", "eligibility_reason", "rank", "selected_top50")


def _semantic_rows(frame: pd.DataFrame, *, effective_month: str, selected_only: bool = False) -> list[dict[str, object]]:
    rows = frame[(frame["market"].astype(str).str.lower() == "um") &
                 (frame["universe_month"].astype(str) == effective_month)].copy()
    if selected_only:
        rows = rows[rows["selected_top50"].astype(str).str.lower().isin({"true", "1"})]
    normalized: list[dict[str, object]] = []
    for record in rows.to_dict(orient="records"):
        item = {field: record.get(field) for field in SEMANTIC_FIELDS}
        item["market"] = str(item["market"]).lower()
        item["symbol"] = str(item["symbol"]).upper()
        item["volume_month"] = str(item["volume_month"])
        item["universe_month"] = str(item["universe_month"])
        item["eligibility_reason"] = str(item["eligibility_reason"])
        item["coverage_ratio"] = None if pd.isna(item["coverage_ratio"]) else round(float(item["coverage_ratio"]), 12)
        item["prior_month_quote_volume"] = None if pd.isna(item["prior_month_quote_volume"]) else float(item["prior_month_quote_volume"])
        item["rank"] = None if pd.isna(item["rank"]) else int(item["rank"])
        item["selected_top50"] = str(item["selected_top50"]).lower() in {"true", "1"}
        normalized.append(item)
    return sorted(normalized, key=lambda row: (row["symbol"], row["volume_month"], row["rank"] is None, row["rank"] or 0))


def ranking_semantic_sha256(frame: pd.DataFrame, *, effective_month: str, selected_only: bool = True) -> str:
    payload = json.dumps(_semantic_rows(frame, effective_month=effective_month, selected_only=selected_only),
                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compare_um_rankings(reconstructed: Path, historical: Path, *, effective_month: str) -> dict[str, object]:
    left = pd.read_csv(reconstructed)
    right = pd.read_csv(historical)
    left_rows = _semantic_rows(left, effective_month=effective_month, selected_only=False)
    right_rows = _semantic_rows(right, effective_month=effective_month, selected_only=False)
    left_by_symbol = {row["symbol"]: row for row in left_rows}
    right_by_symbol = {row["symbol"]: row for row in right_rows}
    common = sorted(set(left_by_symbol) & set(right_by_symbol))
    mismatches = {field: sum(left_by_symbol[symbol][field] != right_by_symbol[symbol][field] for symbol in common)
                  for field in SEMANTIC_FIELDS if field not in {"market", "symbol"}}
    top50_left = {row["symbol"] for row in left_rows if row["selected_top50"]}
    top50_right = {row["symbol"] for row in right_rows if row["selected_top50"]}
    missing_eligible = [symbol for symbol in set(right_by_symbol) - set(left_by_symbol)
                        if right_by_symbol[symbol]["eligibility_reason"] == "ELIGIBLE_COMPLETE_PRIOR_MONTH"]
    return {
        "effective_month": effective_month, "common_row_count": len(common),
        "missing_historical_symbols": sorted(set(right_by_symbol) - set(left_by_symbol)),
        "missing_eligible_historical_symbols": sorted(missing_eligible),
        "extra_reconstructed_symbols": sorted(set(left_by_symbol) - set(right_by_symbol)),
        "field_mismatches": mismatches, "top50_mismatches": sorted(top50_left ^ top50_right),
        "reconstructed_selected_top50_count": len(top50_left), "historical_selected_top50_count": len(top50_right),
        "reconstructed_ranking_semantic_sha256": ranking_semantic_sha256(left, effective_month=effective_month),
        "historical_ranking_semantic_sha256": ranking_semantic_sha256(right, effective_month=effective_month),
        "semantic_parity": not (missing_eligible or any(mismatches.values()) or top50_left ^ top50_right),
    }


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


def build_forward_ranking_from_verified_source(receipt_path: Path, census_dir: Path, output_dir: Path, *, effective_month: str) -> Path:
    """Rank only the exact verified August source objects, independent of transport cadence.

    The receipt is the authority boundary: filesystem objects not listed there
    are intentionally invisible to the ranking calculation.
    """
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    if receipt.get("status") != "PASS" or receipt.get("market") != "um" or receipt.get("interval") != "1d":
        raise RuntimeError("R3_RANKING_INPUT_NOT_VERIFIED")
    inputs = receipt.get("verified_inputs")
    expected = {str(symbol).upper() for symbol in receipt.get("expected_symbols", [])}
    if not isinstance(inputs, list) or not inputs:
        raise RuntimeError("R3_RANKING_INPUT_NOT_VERIFIED")
    by_symbol: dict[str, list[dict[str, object]]] = {}
    for item in inputs:
        symbol = str(item.get("symbol", "")).upper()
        path = Path(str(item.get("path", "")))
        if not symbol or not path.is_file():
            raise RuntimeError("R3_RANKING_INPUT_MISSING_OBJECT")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != str(item.get("sha256", "")):
            raise RuntimeError("R3_RANKING_INPUT_CHECKSUM_MISMATCH")
        by_symbol.setdefault(symbol, []).append(item)
    verified = set(by_symbol)
    if expected and verified != expected:
        raise RuntimeError(f"R3_RANKING_INPUT_SYMBOL_SET_MISMATCH:expected={sorted(expected)}:verified={sorted(verified)}")
    prior_month = str(pd.Period(effective_month, freq="M") - 1)
    expected_days = set(
        pd.date_range(
            f"{prior_month}-01",
            periods=pd.Period(prior_month, freq="M").days_in_month,
            freq="D",
            tz="UTC",
        )
    )
    rows: list[dict[str, object]] = []
    for symbol in sorted(verified):
        candles = pd.concat([load_kline_archive(Path(str(item["path"]))) for item in by_symbol[symbol]], ignore_index=True)
        days = pd.to_datetime(candles["open_time"], utc=True).dt.floor("D")
        if candles.empty or set(days) != expected_days or days.duplicated().any():
            raise RuntimeError(f"R3_RANKING_INPUT_INCOMPLETE:{symbol}")
        quote_volume = float(pd.to_numeric(candles["quote_volume"], errors="coerce").fillna(0).sum())
        rows.append({"market": "um", "symbol": symbol, "archive_month": prior_month, "raw_path": str(by_symbol[symbol][0]["path"]), "published_sha256": str(by_symbol[symbol][0]["sha256"]), "computed_sha256": str(by_symbol[symbol][0]["sha256"]), "integrity_status": "PASS", "row_count": int(len(candles)), "verified_quote_volume": quote_volume})
    taxonomy = pd.read_csv(Path(census_dir) / "um_archive_symbol_census.csv")
    taxonomy["market"] = "um"
    volumes = pd.DataFrame(rows)
    volumes["volume_month"] = prior_month
    volumes["prior_month_expected_days"] = pd.Period(prior_month, freq="M").days_in_month
    volumes["prior_month_observed_days"] = volumes["prior_month_expected_days"]
    volumes["coverage_ratio"] = 1.0
    volumes["prior_month_quote_volume"] = volumes.pop("verified_quote_volume")
    volumes["volume_integrity_status"] = "PASS"
    volumes["issue_codes"] = ""
    volumes = volumes.merge(taxonomy[["market", "symbol", "first_archive_month"]].rename(columns={"first_archive_month": "first_archive_observed"}), on=["market", "symbol"], how="left")
    volumes["universe_month"] = (pd.PeriodIndex(volumes["volume_month"], freq="M") + 1).astype(str)
    volumes["first_observed"] = pd.to_datetime(volumes["first_archive_observed"].astype(str) + "-01", utc=True, errors="coerce")
    ranked = select_verified_causal_liquidity_universe(volumes, top_n=50, minimum_coverage_ratio=1.0)
    output_dir.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(output_dir / "universe_monthly.csv", index=False)
    if ranked.empty:
        raise RuntimeError("RAW_RANKING_EMPTY")
    return output_dir / "universe_monthly.csv"


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
