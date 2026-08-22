from __future__ import annotations

import argparse
import asyncio
import json
import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .backtest import CostModel, run_backtest
from .collector import AppendOnlyEventStore, ForwardCollector
from .data import ArchiveRequest, BinanceArchiveClient, dataset_hash, load_kline_archive, normalize_timestamp, validate_klines
from .experiments import fit_quantile_model, predictive_study
from .features import CORE_FEATURE_SPECS, CoreFeatureEngine, compute_gap_safe_features, preregistered_rule_variants
from .registry import ExperimentRecord, ExperimentRegistry, code_hash
from .regimes import classify_regimes, fit_regime_thresholds
from .reporting import ArtifactWriter
from .splits import expanding_walk_forward
from .statistics import correlation_matrix, deflated_sharpe_probability, hierarchical_feature_clusters, trade_overlap_matrix
from .synthetic import generate_synthetic_bars

TIMEFRAME_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720, "1d": 1440}


def _load_config(path: Path | None) -> dict[str, Any]:
    return tomllib.loads((path or Path("configs/core.toml")).read_text(encoding="utf-8"))


def _load_bars(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet": frame = pd.read_parquet(path)
    elif path.suffix.lower() == ".csv": frame = pd.read_csv(path, float_precision="round_trip")
    elif path.suffix.lower() == ".zip": frame = load_kline_archive(path)
    else: raise ValueError("input must be CSV, Parquet, or an official kline ZIP")
    for column in ("open_time", "close_time"):
        if column in frame and not isinstance(frame[column].dtype, pd.DatetimeTZDtype):
            numeric = pd.to_numeric(frame[column], errors="coerce")
            frame[column] = normalize_timestamp(numeric) if numeric.notna().all() else pd.to_datetime(frame[column], utc=True, errors="raise")
    numeric_columns = frame.select_dtypes(include=["number"]).columns
    if len(numeric_columns):
        # Canonicalize decimal text round-trips so a tail-only rewrite cannot perturb prior rows.
        frame[numeric_columns] = frame[numeric_columns].round(8)
        for column in ("quote_volume", "taker_buy_quote_volume"):
            if column in frame:
                frame[column] = frame[column].round(6)
    return frame.sort_values("open_time", kind="stable").reset_index(drop=True) if "open_time" in frame else frame


def _cost_model(config: dict[str, Any]) -> CostModel:
    costs = config["costs"]
    return CostModel(float(costs["maker_fee_bps"]), float(costs["taker_fee_bps"]), float(costs["spread_bps"]), float(costs["slippage_bps"]), int(costs["latency_bars"]))


def _backtest_summaries(frame: pd.DataFrame, signals: pd.DataFrame, cost: CostModel, rule: dict[str, Any], timeframe: int, market: str) -> tuple[pd.DataFrame, list[pd.DataFrame], dict[str, pd.DataFrame]]:
    records: list[dict[str, object]] = []; trades: list[pd.DataFrame] = []; returns: dict[str, pd.DataFrame] = {}
    for signal_id in signals:
        result = run_backtest(frame, signals[signal_id], cost, int(rule["holding_bars"]), str(rule["fee_mode"]), timeframe, market)
        records.append({"feature_id": signal_id, **result.summary})
        if not result.trades.empty:
            table = result.trades.assign(feature_id=signal_id); trades.append(table)
            returns[signal_id] = table.set_index("entry_time")[["net_return"]].rename(columns={"net_return": signal_id})
    return pd.DataFrame.from_records(records), trades, returns


def _regime_table(trades: list[pd.DataFrame], regimes: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for table in trades:
        for _, trade in table.iterrows():
            if int(trade["entry_bar"]) >= len(regimes): continue
            for column in regimes:
                records.append({"feature_id": trade["feature_id"], "regime_type": column, "regime": regimes.iloc[int(trade["entry_bar"])][column], "net_return": trade["net_return"]})
    if not records: return pd.DataFrame([{"status": "INSUFFICIENT EVIDENCE"}])
    return pd.DataFrame(records).groupby(["feature_id", "regime_type", "regime"], dropna=False)["net_return"].agg(trade_count="count", mean_trade="mean", net_return="sum").reset_index()


def _family_stability(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty: return summary
    result = summary.copy()
    result["parameter_family"] = result["feature_id"].astype(str).str.split("_", n=1).str[0]
    finite = result.dropna(subset=["net_return"])
    family = finite.groupby("parameter_family")["net_return"].agg(family_best_net_return="max", family_median_net_return="median", family_positive_fraction=lambda x: float((x > 0).mean())).reset_index()
    return result.merge(family, on="parameter_family", how="left")


def _outer_positions(n: int, config: dict[str, Any]) -> tuple[int, int, int, int]:
    split = config["split"]; train_end = int(n * float(split["train_fraction"])); validation_end = int(n * (float(split["train_fraction"]) + float(split["validation_fraction"])))
    validation_start = min(train_end + int(split.get("embargo_bars", 0)), validation_end); test_start = min(validation_end + int(split.get("embargo_bars", 0)), n)
    return train_end, validation_start, validation_end, test_start


def _selected_walk_forward(development: pd.DataFrame, variants: pd.DataFrame, cost: CostModel, rule: dict[str, Any], timeframe: int, market: str, embargo: int) -> pd.DataFrame:
    folds = expanding_walk_forward(len(development), max(50, len(development) // 2), max(10, len(development) // 10), max(10, len(development) // 10), embargo_bars=embargo)
    records: list[dict[str, object]] = []
    for fold in folds:
        validation = development.iloc[fold.validation_start:fold.validation_end]; validation_signals = variants.iloc[fold.validation_start:fold.validation_end]
        candidate, _, _ = _backtest_summaries(validation, validation_signals, cost, rule, timeframe, market)
        eligible = candidate[(candidate["trade_count"] > 0) & candidate["net_return"].notna()]
        base = {"fold": fold.fold, **asdict(fold), "selection_criterion": "validation_net_return", "data_scope": "development_only"}
        if eligible.empty:
            records.append({**base, "status": "INSUFFICIENT EVIDENCE"}); continue
        selected = eligible.sort_values("net_return", ascending=False).iloc[0]
        test = development.iloc[fold.test_start:fold.test_end]
        result = run_backtest(test, variants.iloc[fold.test_start:fold.test_end][str(selected["feature_id"])], cost, int(rule["holding_bars"]), str(rule["fee_mode"]), timeframe, market)
        records.append({**base, "selected_feature": str(selected["feature_id"]), "validation_score": float(selected["net_return"]), **result.summary})
    return pd.DataFrame.from_records(records) if records else pd.DataFrame([{"status": "INSUFFICIENT EVIDENCE", "data_scope": "development_only"}])


def run_research(args: argparse.Namespace) -> int:
    config = _load_config(args.config); bars = _load_bars(args.input)
    train_end, validation_start, validation_end, test_start = _outer_positions(len(bars), config)
    pretest = bars.iloc[:validation_end].copy(); pretest = pd.concat([pretest, compute_gap_safe_features(CoreFeatureEngine(), pretest, args.timeframe)], axis=1)
    train, validation = pretest.iloc[:train_end].copy(), pretest.iloc[validation_start:validation_end].copy()
    development = pd.concat([train, validation], ignore_index=True)
    issues = validate_klines(pretest, args.timeframe)
    if any(issue.severity == "ERROR" for issue in issues): raise ValueError("data integrity errors: " + "; ".join(issue.detail for issue in issues if issue.severity == "ERROR"))
    timeframe = TIMEFRAME_MINUTES[args.timeframe]; cost = _cost_model(config); rule = config["rule"]
    horizon_minutes = [int(v) for v in config["research"]["horizons_minutes"] if int(v) >= timeframe]; horizon_bars = sorted({max(1, v // timeframe) for v in horizon_minutes})
    feature_columns = [column for spec in CORE_FEATURE_SPECS for column in spec.continuous_columns if column in development]
    predictive_tables: list[pd.DataFrame] = []
    for feature_id in feature_columns:
        try: model = fit_quantile_model(train[feature_id], int(config["research"]["quantiles"]))
        except ValueError: continue
        predictive_tables.append(predictive_study(validation, validation[feature_id], horizon_bars, model, feature_id, "validation"))
    predictive = pd.concat(predictive_tables, ignore_index=True) if predictive_tables else pd.DataFrame([{"status": "INSUFFICIENT EVIDENCE"}])
    signal_columns = [column for column in development if column.startswith("sig_")]
    summary, trade_tables, return_series = _backtest_summaries(validation, validation[signal_columns], cost, rule, timeframe, args.market)
    previous = np.sign(validation["close"].pct_change(fill_method=None)); previous_summary, previous_trades, previous_returns = _backtest_summaries(validation, pd.DataFrame({"baseline_previous_return_sign": previous}, index=validation.index), cost, rule, timeframe, args.market)
    summary = pd.concat([summary, previous_summary], ignore_index=True); trade_tables.extend(previous_trades); return_series.update(previous_returns)
    buy_hold_gross = float(validation["close"].iloc[-1] / validation["open"].iloc[0] - 1) if len(validation) else np.nan; buy_hold_cost = 2 * cost.taker_fee_bps / 10_000 + cost.fallback_spread_bps / 10_000 + 2 * cost.slippage_bps / 10_000
    if args.market in {"um", "cm"} and "funding_rate" in validation: buy_hold_cost += float(validation["funding_rate"].fillna(0).sum())
    summary = pd.concat([summary, pd.DataFrame([{ "feature_id": "baseline_no_position", "trade_count": 0, "gross_return": 0.0, "net_return": 0.0, "evidence_status": "BASELINE"}, {"feature_id": "baseline_buy_and_hold", "trade_count": 1, "gross_return": buy_hold_gross, "net_return": buy_hold_gross - buy_hold_cost, "evidence_status": "BASELINE"}])], ignore_index=True)
    symbol = str(bars["symbol"].iloc[0]) if "symbol" in bars and len(bars) else args.symbol; by_symbol = summary.assign(symbol=symbol)
    by_year = pd.concat([table.assign(year=pd.to_datetime(table["entry_time"], utc=True).dt.year).groupby(["feature_id", "year"])["net_return"].agg(trade_count="count", mean_trade="mean", net_return="sum").reset_index() for table in trade_tables], ignore_index=True) if trade_tables else pd.DataFrame([{"status": "INSUFFICIENT EVIDENCE"}])
    by_month = pd.concat([table.assign(month=pd.to_datetime(table["entry_time"], utc=True).dt.strftime("%Y-%m")).groupby(["feature_id", "month"])["net_return"].agg(trade_count="count", mean_trade="mean", net_return="sum").reset_index() for table in trade_tables], ignore_index=True) if trade_tables else pd.DataFrame([{"status": "INSUFFICIENT EVIDENCE"}])
    try: by_regime = _regime_table(trade_tables, classify_regimes(validation, fit_regime_thresholds(train)))
    except ValueError: by_regime = pd.DataFrame([{"status": "INSUFFICIENT EVIDENCE"}])
    variants = preregistered_rule_variants(development); parameter_summary, _, _ = _backtest_summaries(validation, variants.iloc[len(train):], cost, rule, timeframe, args.market); parameter_summary = _family_stability(parameter_summary)
    if not parameter_summary.empty and "sharpe" in parameter_summary:
        trial_sharpes = parameter_summary["sharpe"]; parameter_summary["deflated_sharpe_probability"] = parameter_summary.apply(lambda row: deflated_sharpe_probability(float(row["sharpe"]), trial_sharpes, len(validation)) if pd.notna(row.get("sharpe")) else np.nan, axis=1)
    primary = validation["sig_ema20_50"]; cost_records = []
    for slippage in (0.0, 1.0, 2.0, 5.0):
        model = CostModel(cost.maker_fee_bps, cost.taker_fee_bps, cost.fallback_spread_bps, slippage, cost.latency_bars); result = run_backtest(validation, primary, model, int(rule["holding_bars"]), str(rule["fee_mode"]), timeframe, args.market); cost_records.append({"feature_id": "sig_ema20_50", "slippage_bps": slippage, **result.summary})
    walk_forward = _selected_walk_forward(development, variants, cost, rule, timeframe, args.market, int(config["split"].get("embargo_bars", 0)))
    if args.final_holdout:
        full = pd.concat([bars, compute_gap_safe_features(CoreFeatureEngine(), bars, args.timeframe)], axis=1); test = full.iloc[test_start:]; final_summary, _, _ = _backtest_summaries(test, test[signal_columns], cost, rule, timeframe, args.market); final_holdout = final_summary.assign(status="ACCESSED_AFTER_EXPLICIT_OPT_IN")
    else: final_holdout = pd.DataFrame([{ "status": "UNTOUCHED", "reason": "pass --final-holdout only after candidate freeze"}])
    feature_corr = correlation_matrix(validation[feature_columns]); clusters = hierarchical_feature_clusters(feature_corr).rename_axis("feature_id").reset_index() if len(feature_corr) > 1 else pd.DataFrame(columns=["feature_id", "cluster"]); signal_corr = correlation_matrix(validation[signal_columns]); overlap = trade_overlap_matrix(validation[signal_columns]); returns = pd.concat(return_series.values(), axis=1, sort=False) if return_series else pd.DataFrame(); return_corr = correlation_matrix(returns, method="pearson", minimum_periods=3)
    writer = ArtifactWriter(args.output); tables = {"indicator_summary.csv": summary, "indicator_by_symbol.csv": by_symbol, "indicator_by_regime.csv": by_regime, "indicator_by_year.csv": by_year, "indicator_by_month.csv": by_month, "predictive_horizons.csv": predictive, "parameter_robustness.csv": parameter_summary, "feature_correlation.csv": feature_corr, "feature_clusters.csv": clusters, "signal_correlation.csv": signal_corr, "trade_overlap.csv": overlap, "return_series_correlation.csv": return_corr, "cost_sensitivity.csv": pd.DataFrame(cost_records), "walk_forward.csv": walk_forward, "final_holdout.csv": final_holdout}; artifact_paths = writer.write_tables(tables)
    metadata = {
        "verification_status": "UNVERIFIED_BY_EXPERIMENT_RUN",
        "harness_verification_status": "REQUIRES_EXTERNAL_VERIFICATION",
        "experiment_evidence_status": "INSUFFICIENT EVIDENCE",
        "campaign_readiness": "SEE_EXTERNAL_VERIFICATION_REPORT",
        "market": args.market, "symbol": symbol, "timeframe": args.timeframe,
        "rows": len(development), "outer_test_start": test_start,
        "integrity_issues": [asdict(issue) for issue in issues],
        "train_rows": len(train), "validation_rows": len(validation),
        "test_rows": len(bars) - test_start,
        "embargo_rows": validation_start - train_end + test_start - validation_end,
        "trial_count": len(parameter_summary),
        "data_scope": "full_dataset_only_when_final_holdout_opted_in",
        "final_holdout_accessed": bool(args.final_holdout), "config": config,
    }
    report_path = writer.write_report(metadata); artifact_paths.append(report_path); root = Path(__file__).resolve().parents[2]
    record = ExperimentRecord.create(feature_id="core22", code_hash=code_hash(root), dataset_hash=dataset_hash(bars if args.final_holdout else development), market=args.market, symbol_universe=(symbol,), timeframe=args.timeframe, date_range=(str(development["open_time"].min()), str(development["open_time"].max())), parameters={"preregistered_trials": list(parameter_summary.get("feature_id", []))}, target_horizon=str(horizon_minutes), execution_assumptions={"entry": "next_bar_open", "holding_bars": rule["holding_bars"]}, fee_model={"mode": rule["fee_mode"], "maker_bps": cost.maker_fee_bps, "taker_bps": cost.taker_fee_bps}, slippage_model={"bps": cost.slippage_bps, "spread_bps": cost.fallback_spread_bps, "latency_bars": cost.latency_bars}, funding_model={"required_for_futures": True, "column": "funding_rate"}, split_boundaries={"train_end": train_end, "validation_end": validation_end, "outer_test_start": test_start, "embargo_bars": config["split"]["embargo_bars"], "walk_forward_scope": "development_only"}, result_artifact_paths=tuple(str(path) for path in artifact_paths), final_holdout_accessed=bool(args.final_holdout))
    ExperimentRegistry(args.output / "experiment_registry.jsonl").append(record); print(json.dumps({"status": "completed", "report": str(report_path), "experiment_id": record.experiment_id, "final_holdout": "accessed" if args.final_holdout else "untouched"}, indent=2)); return 0


def download_archive(args: argparse.Namespace) -> int:
    request = ArchiveRequest(args.market, args.dataset, args.symbol, args.year, args.month, args.interval, args.cadence, args.day); path, manifest = BinanceArchiveClient(args.raw_root).download(request); processed = None
    if args.processed_output:
        if not (args.dataset.lower().endswith("klines") or args.dataset.lower() == "klines"): raise ValueError("--processed-output currently normalizes kline archives only")
        frame = load_kline_archive(path); args.processed_output.parent.mkdir(parents=True, exist_ok=True); frame.to_parquet(args.processed_output, index=False); processed = str(args.processed_output)
    print(json.dumps({"raw": str(path), "processed": processed, "manifest": manifest.to_dict()}, indent=2)); return 0

def validate_data(args: argparse.Namespace) -> int:
    bars = _load_bars(args.input); issues = validate_klines(bars, args.timeframe); print(json.dumps({"rows": len(bars), "issues": [asdict(issue) for issue in issues]}, indent=2)); return 1 if any(issue.severity == "ERROR" for issue in issues) else 0

def collect_snapshot(args: argparse.Namespace) -> int:
    paths = ForwardCollector(AppendOnlyEventStore(args.output)).collect_um_snapshot(args.symbol); print(json.dumps({"status": "collected", "files": [str(path) for path in paths]}, indent=2)); return 0

async def _stream_for_duration(collector: ForwardCollector, symbol: str, seconds: float) -> int:
    count = 0
    try:
        async with asyncio.timeout(seconds):
            async for _ in collector.stream_liquidations(symbol): count += 1
    except TimeoutError: pass
    return count

def collect_liquidations(args: argparse.Namespace) -> int:
    count = asyncio.run(_stream_for_duration(ForwardCollector(AppendOnlyEventStore(args.output)), args.symbol, args.seconds)); print(json.dumps({"status": "completed", "events": count, "duration_seconds": args.seconds}, indent=2)); return 0

def generate_synthetic(args: argparse.Namespace) -> int:
    frame = generate_synthetic_bars(args.rows, TIMEFRAME_MINUTES[args.timeframe], args.seed); args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix.lower() == ".parquet": frame.to_parquet(args.output, index=False)
    elif args.output.suffix.lower() == ".csv": frame.to_csv(args.output, index=False)
    else: raise ValueError("synthetic output must be CSV or Parquet")
    print(json.dumps({"status": "generated", "rows": len(frame), "output": str(args.output), "evidence": "NON_EVIDENTIARY"}, indent=2)); return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="binance-research", description="Research-only Binance indicator harness"); sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download"); download.add_argument("--market", choices=["spot", "um", "cm"], required=True); download.add_argument("--dataset", required=True); download.add_argument("--symbol", required=True); download.add_argument("--interval"); download.add_argument("--year", type=int, required=True); download.add_argument("--month", type=int, choices=range(1, 13), required=True); download.add_argument("--cadence", choices=["monthly", "daily"], default="monthly"); download.add_argument("--day", type=int, choices=range(1, 32)); download.add_argument("--raw-root", type=Path, default=Path("data/raw")); download.add_argument("--processed-output", type=Path); download.set_defaults(handler=download_archive)
    validate = sub.add_parser("validate-data"); validate.add_argument("--input", type=Path, required=True); validate.add_argument("--timeframe", choices=TIMEFRAME_MINUTES, required=True); validate.set_defaults(handler=validate_data)
    run = sub.add_parser("run"); run.add_argument("--input", type=Path, required=True); run.add_argument("--output", type=Path, required=True); run.add_argument("--market", choices=["spot", "um", "cm"], default="spot"); run.add_argument("--symbol", default="UNKNOWN"); run.add_argument("--timeframe", choices=TIMEFRAME_MINUTES, default="1h"); run.add_argument("--config", type=Path); run.add_argument("--final-holdout", action="store_true"); run.set_defaults(handler=run_research)
    collect = sub.add_parser("collect"); collect.add_argument("--symbol", required=True); collect.add_argument("--output", type=Path, default=Path("data/raw/forward")); collect.set_defaults(handler=collect_snapshot)
    liquidations = sub.add_parser("collect-liquidations"); liquidations.add_argument("--symbol", default="ALL"); liquidations.add_argument("--seconds", type=float, default=60.0); liquidations.add_argument("--output", type=Path, default=Path("data/raw/forward")); liquidations.set_defaults(handler=collect_liquidations)
    synthetic = sub.add_parser("generate-synthetic"); synthetic.add_argument("--rows", type=int, default=1000); synthetic.add_argument("--timeframe", choices=TIMEFRAME_MINUTES, default="1h"); synthetic.add_argument("--seed", type=int, default=1729); synthetic.add_argument("--output", type=Path, required=True); synthetic.set_defaults(handler=generate_synthetic)
    return parser

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv); return int(args.handler(args))

if __name__ == "__main__": raise SystemExit(main())
