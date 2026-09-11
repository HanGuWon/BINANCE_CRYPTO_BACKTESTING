from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import load_kline_archive, normalize_timestamp
from .features import CORE_FEATURE_SPECS, CoreFeatureEngine, compute_gap_safe_features
from .forward import append_predictions_write_once, guard_final_holdout_path, prediction_identity, write_model_artifact
from .predictability import HORIZON_BARS, build_forward_labels, constant_probability, evaluate_walk_forward, fit_logistic_model, mature_training_mask, resolve_horizon_bars, schedule_forward_times


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


def _prepare_output(path: Path, *, mode: str | None = None) -> None:
    if path.exists():
        if not path.is_dir():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
        entries = list(path.iterdir())
        if entries and mode != "prospective":
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
        if mode == "prospective":
            allowed = {"forward_predictions.csv", "metadata.json", "models"}
            unexpected = [entry.name for entry in entries if entry.name not in allowed]
            if unexpected:
                raise FileExistsError(f"unexpected files in prospective output: {unexpected}")
    path.mkdir(parents=True, exist_ok=True)


def _write_json_once(path: Path, payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError(f"refusing to overwrite immutable metadata: {path}")
        return
    path.write_text(encoded, encoding="utf-8")


def audit(args: argparse.Namespace) -> int:
    frame = _load_frame(args.input)
    enriched, columns = _feature_frame(frame, args.timeframe)
    required = {"open", "close", "open_time"}
    missing = sorted(required - set(enriched.columns))
    report = {"status": "PASS" if not missing and len(enriched) > 0 and columns else "BLOCKED", "rows": int(len(enriched)), "timeframe": args.timeframe, "first_time": str(enriched["open_time"].min()) if "open_time" in enriched else None, "last_time": str(enriched["open_time"].max()) if "open_time" in enriched else None, "feature_count": len(columns), "features": columns, "missing_required_columns": missing, "feature_missing_fraction": {column: float(enriched[column].isna().mean()) for column in columns}, "evidence_status": "DEVELOPMENT_AUDIT_ONLY"}
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
    _write_json_once(args.output / "metadata.json", metadata)
    (args.output / "predictability_report.md").write_text("# Predictability development report\n\nEvidence status: " + metadata["status"] + "\n\n" + json.dumps(metadata, indent=2), encoding="utf-8")
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
    position = int(pd.to_datetime(frame["open_time"], utc=True).searchsorted(cutoff, side="left"))
    if position < 8 or position >= len(frame):
        raise ValueError("train_end must leave at least one forward row and eight training rows")
    return position


def _fit_with_metadata(frame: pd.DataFrame, target: pd.Series, names: list[str], args: argparse.Namespace, cutoff: object, horizon: str):
    try:
        return fit_logistic_model(frame, target, names, args.regularization, training_cutoff=str(cutoff), source_timeframe=args.timeframe, horizon=horizon)
    except TypeError as exc:
        # Compatibility for test doubles/legacy adapters only: immediately attach
        # the same immutable provenance fields instead of silently dropping them.
        if "unexpected keyword" not in str(exc):
            raise
        model = fit_logistic_model(frame, target, names, args.regularization)
        for key, value in {"training_cutoff": str(cutoff), "source_timeframe": args.timeframe, "horizon": horizon}.items():
            try:
                setattr(model, key, value)
            except Exception as error:
                raise TypeError("fitter must preserve required provenance metadata") from error
        return model


def record_forward(args: argparse.Namespace) -> int:
    guard_final_holdout_path(args.input)
    guard_final_holdout_path(args.output)
    mode = "SHADOW_REPLAY_NON_PROSPECTIVE" if args.mode in {"shadow-replay", "SHADOW_REPLAY_NON_PROSPECTIVE"} else args.mode
    if mode not in {"SHADOW_REPLAY_NON_PROSPECTIVE", "prospective"}:
        raise ValueError("mode must be shadow-replay or prospective")
    _prepare_output(args.output, mode=("prospective" if mode == "prospective" else None))
    frame = _load_frame(args.input)
    enriched, columns = _feature_frame(frame, args.timeframe)
    train_end = _resolve_train_end(enriched, args)
    baseline = pd.DataFrame(index=enriched.index)
    close = pd.to_numeric(enriched["close"], errors="coerce")
    baseline["baseline_return_1"] = close.pct_change(fill_method=None)
    baseline["baseline_volatility_16"] = close.pct_change(fill_method=None).rolling(16, min_periods=8).std()
    if "volume" in enriched:
        baseline["baseline_volume_change"] = pd.to_numeric(enriched["volume"], errors="coerce").pct_change(fill_method=None)
    recorded_at = pd.Timestamp.now(tz="UTC").isoformat()
    rows: list[dict[str, object]] = []
    model_shas: dict[str, str] = {}
    for horizon in args.horizons:
        horizon_bars = resolve_horizon_bars(args.timeframe, horizon)
        training_labels = build_forward_labels(enriched.iloc[:train_end].copy(), horizon_bars, source_timeframe=args.timeframe, horizon=horizon)
        labels = training_labels["direction_up"]
        first_prediction_time = schedule_forward_times(enriched, train_end, horizon_bars, source_timeframe=args.timeframe)["decision_time"]
        if pd.isna(first_prediction_time):
            raise ValueError("forward recording requires valid decision_time timestamps")
        valid = mature_training_mask(training_labels, first_prediction_time)
        base_names = list(baseline.columns)
        try:
            base_model = _fit_with_metadata(baseline.iloc[:train_end].loc[valid], labels.iloc[:train_end].loc[valid], base_names, args, first_prediction_time, horizon)
        except ValueError:
            continue
        baseline_probability = constant_probability(labels.iloc[:train_end].loc[valid])
        base_probabilities = base_model.predict_proba(baseline.iloc[train_end:])
        for feature in columns:
            names = base_names + [feature]
            training = pd.concat([baseline, enriched[[feature]]], axis=1)
            try:
                model = _fit_with_metadata(training.iloc[:train_end].loc[valid], labels.iloc[:train_end].loc[valid], names, args, first_prediction_time, horizon)
            except ValueError:
                continue
            model_id = f"B1+I:{feature}:{horizon}"
            model_path = args.output / "models" / (model_id.replace(":", "_") + ".json")
            model_shas[model_id] = write_model_artifact(model_path, model, allow_identical=(mode == "prospective"), market=args.market, symbol=args.symbol, timeframe=args.timeframe, horizon=horizon, campaign_id=args.campaign_id, dataset_sha256=args.dataset_sha256, source_tree_sha256=args.source_tree_sha256, feature_registry_sha256=args.feature_registry_sha256, config_sha256=args.config_sha256)
            combined_probabilities = model.predict_proba(training.iloc[train_end:])
            for offset, (b0, b1, b1i) in enumerate(zip(np.full(len(combined_probabilities), baseline_probability), base_probabilities, combined_probabilities), start=train_end):
                schedule = schedule_forward_times(enriched, offset, horizon_bars, source_timeframe=args.timeframe)
                decision_time = schedule["decision_time"]
                rows.append({"prediction_id": prediction_identity(market=args.market, symbol=args.symbol, timeframe=args.timeframe, decision_time=decision_time, horizon=horizon, model_id=model_id, campaign_id=args.campaign_id, model_artifact_sha256=model_shas[model_id], dataset_sha256=args.dataset_sha256, mode=mode, source_tree_sha256=args.source_tree_sha256, feature_registry_sha256=args.feature_registry_sha256, config_sha256=args.config_sha256), "campaign_id": args.campaign_id, "market": args.market, "symbol": args.symbol, "timeframe": args.timeframe, "decision_time": str(decision_time), "feature_time": str(decision_time), "prediction_recorded_at": recorded_at, "next_executable_open": str(schedule["next_executable_open"]), "target_exit_time": str(schedule["target_exit_time"]), "horizon": horizon, "feature_id": feature, "model": "B1+I", "model_id": model_id, "model_artifact_sha256": model_shas[model_id], "mode": mode, "dataset_sha256": args.dataset_sha256, "source_tree_sha256": args.source_tree_sha256, "b0_probability_up": float(b0), "b1_probability_up": float(b1), "b1_plus_i_probability_up": float(b1i), "probability_up": float(b1i)})
    predictions = pd.DataFrame.from_records(rows)
    append_predictions_write_once(args.output / "forward_predictions.csv", predictions, allow_replay=(mode == "prospective"))
    metadata = {"status": "RECORDED_OUTCOME_BLIND", "mode": mode, "market": args.market, "symbol": args.symbol, "train_end_index": train_end, "prediction_rows": len(predictions), "model_artifact_shas": model_shas, "campaign_id": args.campaign_id, "dataset_sha256": args.dataset_sha256, "source_tree_sha256": args.source_tree_sha256, "feature_registry_sha256": args.feature_registry_sha256, "config_sha256": args.config_sha256, "final_holdout": "UNTOUCHED"}
    _write_json_once(args.output / "metadata.json", metadata)
    print(json.dumps(metadata, indent=2))
    return 0


def evaluate_forward(args: argparse.Namespace) -> int:
    guard_final_holdout_path(args.input)
    guard_final_holdout_path(args.predictions)
    guard_final_holdout_path(args.output)
    frame = _load_frame(args.input)
    predictions = pd.read_csv(args.predictions)
    from .predictability import probability_metrics
    required = {"prediction_id", "decision_time", "probability_up", "market", "symbol", "timeframe", "model_id", "campaign_id", "horizon"}
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(f"prediction store missing immutable fields: {', '.join(sorted(missing))}")
    rows: list[dict[str, object]] = []
    for horizon, group in predictions.groupby("horizon"):
        horizon_name = str(horizon)
        horizon_bars = resolve_horizon_bars(args.timeframe, horizon_name)
        label_frame = build_forward_labels(frame, horizon_bars, source_timeframe=args.timeframe, horizon=horizon_name)
        label_values = label_frame["direction_up"].to_numpy()
        labels = pd.Series(label_values, index=pd.to_datetime(label_frame["decision_time"], utc=True, errors="coerce"))
        group = group.copy()
        group["decision_time"] = pd.to_datetime(group["decision_time"], utc=True, errors="coerce")
        expected_ids = group.apply(lambda row: prediction_identity(market=row["market"], symbol=row["symbol"], timeframe=row["timeframe"], decision_time=row["decision_time"], horizon=horizon_name, model_id=row["model_id"], campaign_id=row["campaign_id"], mode=row.get("mode"), model_artifact_sha256=row.get("model_artifact_sha256"), dataset_sha256=row.get("dataset_sha256"), source_tree_sha256=row.get("source_tree_sha256"), feature_registry_sha256=row.get("feature_registry_sha256"), config_sha256=row.get("config_sha256")), axis=1)
        if not (expected_ids.astype(str).to_numpy() == group["prediction_id"].astype(str).to_numpy()).all():
            raise ValueError("prediction identity mismatch")
        group["direction_up"] = group["decision_time"].map(labels)
        group = group.dropna(subset=["decision_time", "direction_up", "probability_up"])
        for feature, feature_group in group.groupby("feature_id"):
            metrics = probability_metrics(feature_group["direction_up"], feature_group["probability_up"])
            rows.append({"horizon": horizon_name, "feature_id": feature, "model": str(feature_group["model"].iloc[0]), **metrics})
    result = pd.DataFrame.from_records(rows)
    _prepare_output(args.output)
    result.to_csv(args.output / "forward_evaluation.csv", index=False)
    _write_json_once(args.output / "metadata.json", {"status": "EVALUATED_AFTER_LABEL_COMPLETION", "rows": len(result), "predictions": str(args.predictions), "final_holdout": "UNTOUCHED"})
    print(json.dumps({"status": "EVALUATED_AFTER_LABEL_COMPLETION", "rows": len(result)}, indent=2))
    return 0


def add_predictability_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("predictability", help="evaluate causal indicator predictability")
    children = parser.add_subparsers(dest="predictability_command", required=True)
    audit_parser = children.add_parser("audit", help="development-only feature/data audit")
    audit_parser.add_argument("--input", type=Path, required=True)
    audit_parser.add_argument("--timeframe", choices=("15m", "1h", "4h"), default="15m")
    audit_parser.add_argument("--output", type=Path)
    audit_parser.set_defaults(handler=audit)
    run_parser = children.add_parser("run-development", help="development-only walk-forward analysis")
    run_parser.add_argument("--input", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--timeframe", choices=("15m", "1h", "4h"), default="15m")
    run_parser.add_argument("--horizons", nargs="+", choices=tuple(HORIZON_BARS), default=list(HORIZON_BARS))
    run_parser.add_argument("--minimum-train", type=int, default=256)
    run_parser.add_argument("--validation-size", type=int, default=96)
    run_parser.add_argument("--step-size", type=int, default=96)
    run_parser.add_argument("--regularization", type=float, default=1.0)
    run_parser.set_defaults(handler=run_development)
    record_parser = children.add_parser("record-forward", help="outcome-blind shadow/prospective prediction recording")
    record_parser.add_argument("--input", type=Path, required=True)
    record_parser.add_argument("--output", type=Path, required=True)
    record_parser.add_argument("--timeframe", choices=("15m", "1h", "4h"), default="15m")
    record_parser.add_argument("--horizons", nargs="+", choices=tuple(HORIZON_BARS), default=list(HORIZON_BARS))
    record_parser.add_argument("--train-rows", type=int)
    record_parser.add_argument("--train-end")
    record_parser.add_argument("--regularization", type=float, default=1.0)
    record_parser.add_argument("--market", choices=("spot", "um", "cm"), default="spot")
    record_parser.add_argument("--symbol", default="UNKNOWN")
    record_parser.add_argument("--campaign-id", default="predictability-v1")
    record_parser.add_argument("--mode", choices=("shadow-replay", "SHADOW_REPLAY_NON_PROSPECTIVE", "prospective"), default="shadow-replay")
    for name in ("dataset-sha256", "source-tree-sha256", "feature-registry-sha256", "config-sha256"):
        record_parser.add_argument("--" + name, dest=name.replace("-", "_"))
    record_parser.set_defaults(handler=record_forward)
    eval_parser = children.add_parser("evaluate-forward", help="evaluate completed labels by immutable prediction identity")
    eval_parser.add_argument("--input", type=Path, required=True)
    eval_parser.add_argument("--predictions", type=Path, required=True)
    eval_parser.add_argument("--timeframe", choices=("15m", "1h", "4h"), default="15m")
    eval_parser.add_argument("--output", type=Path, required=True)
    eval_parser.set_defaults(handler=evaluate_forward)


