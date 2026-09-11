from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .data import load_kline_archive, normalize_timestamp
from .features import CORE_FEATURE_SPECS, CoreFeatureEngine, compute_gap_safe_features
from .predictability import HORIZON_BARS, build_forward_labels, evaluate_walk_forward, fit_logistic_model, mature_training_mask, resolve_horizon_bars


def _load_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    elif path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, float_precision="round_trip")
    elif path.suffix.lower() == ".zip":
        frame = load_kline_archive(path)
    else:
        raise ValueError("input must be CSV, Parquet, or an official kline ZIP")
    for column in ("open_time", "close_time"):
        if column in frame:
            numeric = pd.to_numeric(frame[column], errors="coerce")
            frame[column] = normalize_timestamp(numeric) if numeric.notna().all() else pd.to_datetime(frame[column], utc=True, errors="raise")
    return frame.sort_values("open_time", kind="stable").reset_index(drop=True) if "open_time" in frame else frame.reset_index(drop=True)


def _feature_frame(frame: pd.DataFrame, timeframe: str) -> tuple[pd.DataFrame, list[str]]:
    features = compute_gap_safe_features(CoreFeatureEngine(), frame, timeframe)
    enriched = pd.concat([frame.reset_index(drop=True), features.reset_index(drop=True)], axis=1)
    columns: list[str] = []
    for spec in CORE_FEATURE_SPECS:
        columns.extend(column for column in spec.continuous_columns if column in enriched and column not in columns)
    return enriched, columns


def _prepare_output(path: Path) -> None:
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    path.mkdir(parents=True, exist_ok=True)


def audit(args: argparse.Namespace) -> int:
    frame = _load_frame(args.input)
    enriched, columns = _feature_frame(frame, args.timeframe)
    required = {"open", "close", "open_time"}
    missing = sorted(required - set(enriched.columns))
    report = {
        "status": "PASS" if not missing and len(enriched) > 0 and columns else "BLOCKED",
        "rows": int(len(enriched)),
        "timeframe": args.timeframe,
        "first_time": str(enriched["open_time"].min()) if "open_time" in enriched else None,
        "last_time": str(enriched["open_time"].max()) if "open_time" in enriched else None,
        "feature_count": len(columns),
        "features": columns,
        "missing_required_columns": missing,
        "feature_missing_fraction": {column: float(enriched[column].isna().mean()) for column in columns},
        "evidence_status": "DEVELOPMENT_AUDIT_ONLY",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"] == "PASS" else 1


def run_development(args: argparse.Namespace) -> int:
    frame = _load_frame(args.input)
    enriched, columns = _feature_frame(frame, args.timeframe)
    if not columns:
        raise ValueError("no registered feature columns are available in the input")
    results = evaluate_walk_forward(enriched, columns, horizons=tuple(args.horizons), minimum_train=args.minimum_train, validation_size=args.validation_size, step_size=args.step_size, regularization=args.regularization, source_timeframe=args.timeframe)
    _prepare_output(args.output)
    results.to_csv(args.output / "predictability_results.csv", index=False)
    metadata = {"status": "completed" if not results.empty else "INSUFFICIENT EVIDENCE", "data_scope": "development_only", "timeframe": args.timeframe, "horizons": list(args.horizons), "feature_count": len(columns), "rows": len(enriched), "regularization": args.regularization, "results_rows": len(results), "final_holdout": "UNTOUCHED"}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    report_lines = ["# Predictability development report", "", "Evidence status: " + metadata["status"], "", "The result is development-only and does not establish future profitability.", "", json.dumps(metadata, indent=2), ""]
    (args.output / "predictability_report.md").write_text("\n".join(report_lines), encoding="utf-8")
    print(json.dumps({"status": metadata["status"], "output": str(args.output), "results": len(results)}, indent=2))
    return 0


def _resolve_train_end(frame: pd.DataFrame, args: argparse.Namespace) -> int:
    if args.train_rows is not None:
        if not 8 <= args.train_rows < len(frame):
            raise ValueError("train_rows must leave at least one forward row")
        return args.train_rows
    if not args.train_end:
        raise ValueError("provide --train-rows or --train-end")
    cutoff = pd.Timestamp(args.train_end)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    times = pd.to_datetime(frame["open_time"], utc=True)
    position = int(times.searchsorted(cutoff, side="left"))
    if position < 8 or position >= len(frame):
        raise ValueError("train_end must leave at least one forward row and eight training rows")
    return position


def record_forward(args: argparse.Namespace) -> int:
    frame = _load_frame(args.input)
    enriched, columns = _feature_frame(frame, args.timeframe)
    train_end = _resolve_train_end(enriched, args)
    baseline = pd.DataFrame(index=enriched.index)
    close = pd.to_numeric(enriched["close"], errors="coerce")
    baseline["baseline_return_1"] = close.pct_change(fill_method=None)
    baseline["baseline_volatility_16"] = close.pct_change(fill_method=None).rolling(16, min_periods=8).std()
    rows: list[dict[str, object]] = []
    for horizon in args.horizons:
        horizon_bars = resolve_horizon_bars(args.timeframe, horizon)
        label_frame = build_forward_labels(enriched, horizon_bars, source_timeframe=args.timeframe, horizon=horizon)
        labels = label_frame["direction_up"]
        for feature in columns:
            names = ["baseline_return_1", "baseline_volatility_16", feature]
            training = pd.concat([baseline, enriched[[feature]]], axis=1).iloc[:train_end]
            first_prediction_time = label_frame.iloc[train_end]["decision_time"]
            if pd.isna(first_prediction_time):
                raise ValueError("forward recording requires valid decision_time timestamps")
            valid = mature_training_mask(label_frame.iloc[:train_end], first_prediction_time).set_axis(labels.iloc[:train_end].index)
            try:
                model = fit_logistic_model(training.loc[valid], labels.iloc[:train_end].loc[valid], names, args.regularization)
            except ValueError:
                continue
            future = pd.concat([baseline, enriched[[feature]]], axis=1).iloc[train_end:]
            probabilities = model.predict_proba(future)
            for offset, probability in enumerate(probabilities, start=train_end):
                rows.append({"decision_index": offset, "horizon": horizon, "feature_id": feature, "model": "B1+I", "probability_up": float(probability), "prediction_time": str(enriched.loc[offset, "open_time"])})
    _prepare_output(args.output)
    predictions = pd.DataFrame.from_records(rows)
    predictions.to_csv(args.output / "forward_predictions.csv", index=False)
    metadata = {"status": "RECORDED_OUTCOME_BLIND", "train_end_index": train_end, "prediction_rows": len(predictions), "final_holdout": "UNTOUCHED"}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


def evaluate_forward(args: argparse.Namespace) -> int:
    frame = _load_frame(args.input)
    predictions = pd.read_csv(args.predictions)
    from .predictability import probability_metrics
    rows: list[dict[str, object]] = []
    for horizon, group in predictions.groupby("horizon"):
        horizon_name = str(horizon)
        horizon_bars = resolve_horizon_bars(args.timeframe, horizon_name)
        label_frame = build_forward_labels(frame, horizon_bars, source_timeframe=args.timeframe, horizon=horizon_name)
        labels = label_frame["direction_up"]
        group = group.copy()
        group["decision_index"] = pd.to_numeric(group["decision_index"], errors="coerce").astype("Int64")
        group = group.dropna(subset=["decision_index", "probability_up"])
        group["direction_up"] = group["decision_index"].astype(int).map(labels)
        group = group.dropna(subset=["direction_up"])
        for feature, feature_group in group.groupby("feature_id"):
            metrics = probability_metrics(feature_group["direction_up"], feature_group["probability_up"])
            rows.append({"horizon": horizon, "feature_id": feature, "model": str(feature_group["model"].iloc[0]), **metrics})
    result = pd.DataFrame.from_records(rows)
    _prepare_output(args.output)
    result.to_csv(args.output / "forward_evaluation.csv", index=False)
    metadata = {"status": "EVALUATED_AFTER_LABEL_COMPLETION", "rows": len(result), "predictions": str(args.predictions), "final_holdout": "UNTOUCHED"}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


def add_predictability_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("predictability", help="evaluate causal indicator predictability")
    children = parser.add_subparsers(dest="predictability_command", required=True)
    audit_parser = children.add_parser("audit")
    audit_parser.add_argument("--input", type=Path, required=True)
    audit_parser.add_argument("--timeframe", choices=("15m", "1h", "4h"), default="15m")
    audit_parser.add_argument("--output", type=Path)
    audit_parser.set_defaults(handler=audit)
    run_parser = children.add_parser("run-development")
    run_parser.add_argument("--input", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--timeframe", choices=("15m", "1h", "4h"), default="15m")
    run_parser.add_argument("--horizons", nargs="+", choices=tuple(HORIZON_BARS), default=list(HORIZON_BARS))
    run_parser.add_argument("--minimum-train", type=int, default=256)
    run_parser.add_argument("--validation-size", type=int, default=96)
    run_parser.add_argument("--step-size", type=int, default=96)
    run_parser.add_argument("--regularization", type=float, default=1.0)
    run_parser.set_defaults(handler=run_development)
    record_parser = children.add_parser("record-forward")
    record_parser.add_argument("--input", type=Path, required=True)
    record_parser.add_argument("--output", type=Path, required=True)
    record_parser.add_argument("--timeframe", choices=("15m", "1h", "4h"), default="15m")
    record_parser.add_argument("--horizons", nargs="+", choices=tuple(HORIZON_BARS), default=list(HORIZON_BARS))
    record_parser.add_argument("--train-rows", type=int)
    record_parser.add_argument("--train-end")
    record_parser.add_argument("--regularization", type=float, default=1.0)
    record_parser.set_defaults(handler=record_forward)
    eval_parser = children.add_parser("evaluate-forward")
    eval_parser.add_argument("--input", type=Path, required=True)
    eval_parser.add_argument("--predictions", type=Path, required=True)
    eval_parser.add_argument("--timeframe", choices=("15m", "1h", "4h"), default="15m")
    eval_parser.add_argument("--output", type=Path, required=True)
    eval_parser.set_defaults(handler=evaluate_forward)
