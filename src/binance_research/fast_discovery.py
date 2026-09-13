"""Outcome-blind Fast Discovery funnel with deterministic cached screening."""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
from typing import Callable, Iterable
import numpy as np
import pandas as pd
from .predictability import evaluate_walk_forward

DEFAULT_PRIMITIVES = ("donchian_breakout20", "roc6", "rvol20", "vwap_deviation20", "taker_buy_sell_ratio", "cvd_slope6", "bb_bandwidth20", "premium", "premium_zscore90")
S1_COMBINATIONS = (("donchian_breakout20", "ema20_slope_5", "rvol20"), ("roc6", "sig_ema20_50", "taker_buy_sell_ratio"), ("bb_bandwidth20", "donchian_breakout20", "rvol20"), ("premium_zscore90", "sig_ema20_50", "rvol20"))
S1_ROLES = ("TRIGGER", "REGIME_FILTER", "PARTICIPATION")
S1_ROLE_GRAMMAR = "TRIGGER AND REGIME_FILTER AND PARTICIPATION"
S1_MAX_COMBINATIONS = 4
S1_MAX_COMPONENTS = 3
S0_MAX_SURVIVORS = 12
S1_MAX_SURVIVORS = 6
S2_MAX_FINALISTS = 3

class FeatureCache:
    def __init__(self) -> None:
        self._values: dict[tuple[str, ...], pd.Series] = {}
        self.hits = 0
        self.misses = 0
    def get(self, key: tuple[str, ...], compute: Callable[[], pd.Series]) -> pd.Series:
        if key in self._values:
            self.hits += 1
            return self._values[key]
        self.misses += 1
        value = compute()
        self._values[key] = value
        return value

def canonical_cache_key(market: str, timeframe: str, symbol: str, segment_id: str, feature_id: str, variant: str, source_hash: str) -> tuple[str, ...]:
    return (market, timeframe, symbol, segment_id, feature_id, variant, source_hash)

def _source_hash(frame: pd.DataFrame) -> str:
    cols = [c for c in ("open_time", "timestamp", "symbol", "segment_id") if c in frame.columns]
    payload = frame[cols].to_csv(index=False).encode() if cols else str(frame.shape).encode()
    return hashlib.sha256(payload).hexdigest()

def _independent_blocks(result: pd.DataFrame) -> int:
    if result.empty or "fold" not in result.columns:
        return 0
    return int(pd.to_numeric(result["fold"], errors="coerce").dropna().nunique())

def screen_s0(frame: pd.DataFrame, *, timeframe: str = "1h", horizons: Iterable[str] = ("1h", "4h", "24h"), primitives: Iterable[str] = DEFAULT_PRIMITIVES, minimum_train: int = 64, validation_size: int = 32, step_size: int = 32, cache: FeatureCache | None = None, market: str = "um") -> tuple[pd.DataFrame, pd.DataFrame]:
    primitives = tuple(primitives); cache = cache or FeatureCache(); source_hash = _source_hash(frame)
    missing = [name for name in ("open_time", "open", "close") if name not in frame.columns]
    if missing:
        rejected = pd.DataFrame([{"feature_id": f, "status": "HISTORICAL_UNAVAILABLE", "reason": "missing causal label columns: " + ",".join(missing)} for f in primitives])
        return pd.DataFrame(columns=["feature_id", "status", "aggregate_delta_log_loss", "positive_fold_fraction", "independent_block_count"]), rejected
    rows: list[dict[str, object]] = []; rejected: list[dict[str, object]] = []
    for feature in primitives:
        if feature not in frame.columns:
            rejected.append({"feature_id": feature, "status": "HISTORICAL_UNAVAILABLE", "reason": "feature column absent"}); continue
        key = canonical_cache_key(market, timeframe, str(frame.get("symbol", pd.Series(["UNKNOWN"])).iloc[0]), str(frame.get("segment_id", pd.Series(["UNKNOWN"])).iloc[0]), feature, "raw", source_hash)
        cached = cache.get(key, lambda f=feature: pd.to_numeric(frame[f], errors="coerce"))
        eval_frame = frame.copy(); eval_frame[feature] = cached
        result = evaluate_walk_forward(eval_frame, [feature], horizons=tuple(horizons), minimum_train=minimum_train, validation_size=validation_size, step_size=step_size, source_timeframe=timeframe)
        result = result[result["model"].eq("I:" + feature)] if not result.empty else result
        if result.empty:
            rejected.append({"feature_id": feature, "status": "REJECTED", "reason": "no valid causal folds"}); continue
        deltas = pd.to_numeric(result["log_loss_improvement"], errors="coerce").dropna()
        rows.append({"feature_id": feature, "status": "SCREENED", "aggregate_delta_log_loss": float(deltas.mean()), "positive_fold_fraction": float((deltas > 0).mean()), "independent_block_count": _independent_blocks(result), "fold_count": int(result["fold"].nunique())})
    scored = pd.DataFrame(rows)
    if scored.empty: return scored, pd.DataFrame(rejected)
    survivors = scored[(scored["aggregate_delta_log_loss"] > 0) & (scored["positive_fold_fraction"] > 0.5) & (scored["independent_block_count"] >= 2)]
    scored.loc[scored["feature_id"].isin(survivors["feature_id"]), "status"] = "SURVIVOR"
    rejected.extend(scored[scored["status"].eq("SCREENED")].query("status != 'SURVIVOR'").assign(reason="failed frozen S0 safety gates").to_dict("records"))
    return scored[scored["status"].eq("SURVIVOR")].copy(), pd.DataFrame(rejected)

def _coverage_fields(frame: pd.DataFrame, valid_mask: pd.Series) -> dict[str, object]:
    """Return explicit source-coverage facts for one feature, including partial data."""
    mask = valid_mask.reindex(frame.index, fill_value=False).astype(bool)
    valid_rows = int(mask.sum())
    times = pd.to_datetime(frame.loc[mask, "open_time"], utc=True, errors="coerce") if "open_time" in frame else pd.Series(dtype="datetime64[ns, UTC]")
    times = times.dropna()
    symbols = frame.loc[mask, "symbol"].astype(str).nunique() if "symbol" in frame else 0
    months = times.dt.strftime("%Y-%m").nunique() if len(times) else 0
    return {
        "first_observed_time": times.min().isoformat() if len(times) else None,
        "last_observed_time": times.max().isoformat() if len(times) else None,
        "valid_rows": valid_rows,
        "valid_symbols": int(symbols),
        "valid_months": int(months),
        "coverage_fraction": float(valid_rows / len(frame)) if len(frame) else 0.0,
    }
def screen_s0_complete(
    frame: pd.DataFrame,
    *,
    timeframe: str = "1h",
    horizons: Iterable[str] = ("1h", "4h", "24h"),
    primitives: Iterable[str] = DEFAULT_PRIMITIVES,
    minimum_train: int = 64,
    validation_size: int = 32,
    step_size: int = 32,
    cache: FeatureCache | None = None,
    market: str = "um",
    require_multi_symbol: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, FeatureCache]:
    """Return one complete aggregate row per primitive and horizon.

    Unlike the legacy ``screen_s0`` API, candidates never disappear: unavailable
    and evaluated-but-rejected rows are retained in the complete results table.
    Calendar-block counts use timestamp labels emitted by ``evaluate_walk_forward``;
    fold-ID fallback is accepted only for test doubles that predate that metadata.
    """
    primitive_ids = tuple(primitives)
    horizon_ids = tuple(horizons)
    cache = cache or FeatureCache()
    required = {"open_time", "open", "close"}
    rows: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    missing_labels = sorted(required - set(frame.columns))
    symbol_series = frame.get("symbol", pd.Series("UNKNOWN", index=frame.index)).astype(str)
    for feature_id in primitive_ids:
        availability = "HISTORICAL_AVAILABLE" if feature_id in frame and pd.to_numeric(frame[feature_id], errors="coerce").notna().any() else "HISTORICAL_PARTIAL"
        coverage_mask = pd.to_numeric(frame[feature_id], errors="coerce").notna() if feature_id in frame else pd.Series(False, index=frame.index)
        if missing_labels: coverage_mask = pd.Series(False, index=frame.index)
        coverage_fields = _coverage_fields(frame, coverage_mask)
        if missing_labels:
            availability = "HISTORICAL_UNAVAILABLE"
        if feature_id not in frame or missing_labels:
            for horizon in horizon_ids:
                row = {"feature_id": feature_id, "timeframe": timeframe, "horizon": horizon, "availability_status": "HISTORICAL_UNAVAILABLE", "eligible_observations": 0, "valid_symbols": 0, "valid_temporal_folds": 0, "independent_calendar_block_count": 0, "aggregate_paired_delta_log_loss": np.nan, "positive_fold_fraction": np.nan, "symbol_concentration": np.nan, "brier_improvement": np.nan, "status": "HISTORICAL_UNAVAILABLE", "rejection_reason": "missing causal columns: " + ",".join(missing_labels or [feature_id])}
                row.update(coverage_fields)
                rows.append(row); rejected.append(row.copy())
            continue
        source_hash = _source_hash(frame)
        key = canonical_cache_key(market, timeframe, str(symbol_series.iloc[0]), str(frame.get("segment_id", pd.Series(["UNKNOWN"])).iloc[0]), feature_id, "raw", source_hash)
        values = cache.get(key, lambda f=feature_id: pd.to_numeric(frame[f], errors="coerce"))
        work = frame.copy(); work[feature_id] = values
        evaluation = evaluate_walk_forward(work, [feature_id], horizons=horizon_ids, minimum_train=minimum_train, validation_size=validation_size, step_size=step_size, source_timeframe=timeframe)
        if not evaluation.empty and "horizon" not in evaluation:
            evaluation = evaluation.assign(horizon=horizon_ids[0])
        evaluation = evaluation[evaluation["model"].eq("I:" + feature_id)] if not evaluation.empty else evaluation
        finite = values.notna()
        valid_symbols = int(symbol_series.loc[finite].nunique())
        counts = symbol_series.loc[finite].value_counts(normalize=True)
        concentration = float(counts.max()) if not counts.empty else np.nan
        for horizon in horizon_ids:
            subset = evaluation[evaluation["horizon"].eq(horizon)] if not evaluation.empty else evaluation
            if subset.empty:
                row = {"feature_id": feature_id, "timeframe": timeframe, "horizon": horizon, "availability_status": availability, "eligible_observations": 0, "valid_symbols": valid_symbols, "valid_temporal_folds": 0, "independent_calendar_block_count": 0, "aggregate_paired_delta_log_loss": np.nan, "positive_fold_fraction": np.nan, "symbol_concentration": concentration, "brier_improvement": np.nan, "status": "S0_REJECTED", "rejection_reason": "no valid causal folds"}
            else:
                deltas = pd.to_numeric(subset["log_loss_improvement"], errors="coerce").dropna()
                blocks: set[str] = set()
                if "validation_calendar_blocks" in subset:
                    for value in subset["validation_calendar_blocks"].dropna().astype(str):
                        blocks.update(token for token in value.split("|") if token)
                    block_count = len(blocks)
                else:
                    block_count = int(pd.to_numeric(subset["fold"], errors="coerce").dropna().nunique())
                aggregate = float(deltas.mean()) if not deltas.empty else np.nan
                positive = float((deltas > 0).mean()) if not deltas.empty else np.nan
                brier = float(pd.to_numeric(subset.get("brier_improvement", pd.Series(dtype=float)), errors="coerce").mean()) if "brier_improvement" in subset else np.nan
                reasons: list[str] = []
                if not np.isfinite(aggregate) or aggregate <= 0: reasons.append("non-positive aggregate paired delta log-loss")
                if not np.isfinite(positive) or positive <= 0.5: reasons.append("not positive in a majority of valid folds")
                if block_count < 2: reasons.append("fewer than two independent calendar blocks")
                if require_multi_symbol and "validation_calendar_blocks" in evaluation.columns and valid_symbols < 2: reasons.append("insufficient multi-symbol coverage")
                if require_multi_symbol and "validation_calendar_blocks" in evaluation.columns and np.isfinite(concentration) and concentration > 0.8: reasons.append("excessive single-symbol concentration")
                status = "S0_SURVIVOR" if not reasons else "S0_REJECTED"
                row = {"feature_id": feature_id, "timeframe": timeframe, "horizon": horizon, "availability_status": availability, "eligible_observations": int(pd.to_numeric(subset["validation_rows"], errors="coerce").sum()), "valid_symbols": valid_symbols, "valid_temporal_folds": int(subset["fold"].nunique()), "independent_calendar_block_count": block_count, "aggregate_paired_delta_log_loss": aggregate, "positive_fold_fraction": positive, "symbol_concentration": concentration, "brier_improvement": brier, "status": status, "rejection_reason": "; ".join(reasons)}
            row.update(coverage_fields)
            rows.append(row)
            if row["status"] != "S0_SURVIVOR": rejected.append(row.copy())
    complete = pd.DataFrame(rows)
    return complete, pd.DataFrame(rejected), cache

def screen_s0_panel(
    frame: pd.DataFrame,
    *,
    timeframe: str = "1h",
    horizons: Iterable[str] = ("1h", "4h", "24h"),
    primitives: Iterable[str] = DEFAULT_PRIMITIVES,
    minimum_train: int = 64,
    validation_size: int = 32,
    step_size: int = 32,
    cache: FeatureCache | None = None,
    market: str = "um",
    require_multi_symbol: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, FeatureCache]:
    """Evaluate each symbol independently, then aggregate complete S0 rows."""
    if "symbol" not in frame:
        raise ValueError("panel S0 evaluation requires symbol")
    cache = cache or FeatureCache()
    per_symbol: list[pd.DataFrame] = []
    rejected_parts: list[pd.DataFrame] = []
    for symbol, group in frame.groupby("symbol", sort=True):
        complete, _, cache = screen_s0_complete(group.reset_index(drop=True), timeframe=timeframe, horizons=horizons, primitives=primitives, minimum_train=minimum_train, validation_size=validation_size, step_size=step_size, cache=cache, market=market, require_multi_symbol=False)
        complete.insert(0, "_symbol", str(symbol))
        per_symbol.append(complete)
    if not per_symbol:
        return pd.DataFrame(), pd.DataFrame(), cache
    detail = pd.concat(per_symbol, ignore_index=True)
    rows: list[dict[str, object]] = []
    for (feature_id, horizon), group in detail.groupby(["feature_id", "horizon"], sort=False):
        available = group[group["status"].ne("HISTORICAL_UNAVAILABLE")]
        if available.empty:
            row = group.iloc[0].drop(labels=["_symbol"]).to_dict()
            row.update({"timeframe": timeframe, "valid_symbols": 0, "status": "HISTORICAL_UNAVAILABLE", "rejection_reason": "unavailable for every symbol"})
            rows.append(row)
            continue
        valid = available[available["valid_temporal_folds"].gt(0)]
        weights = pd.to_numeric(valid["eligible_observations"], errors="coerce").fillna(0.0)
        total_weight = float(weights.sum())
        aggregate = float((pd.to_numeric(valid["aggregate_paired_delta_log_loss"], errors="coerce").fillna(0.0) * weights).sum() / total_weight) if total_weight else np.nan
        positive = float((pd.to_numeric(valid["positive_fold_fraction"], errors="coerce").fillna(0.0) * pd.to_numeric(valid["valid_temporal_folds"], errors="coerce").fillna(0.0)).sum() / pd.to_numeric(valid["valid_temporal_folds"], errors="coerce").sum()) if not valid.empty and pd.to_numeric(valid["valid_temporal_folds"], errors="coerce").sum() else np.nan
        brier = float((pd.to_numeric(valid["brier_improvement"], errors="coerce").fillna(0.0) * weights).sum() / total_weight) if total_weight else np.nan
        blocks: set[str] = set()
        block_values = []
        for value in valid.get("independent_calendar_block_count", pd.Series(dtype=float)):
            if pd.notna(value):
                block_values.append(int(value))
        if "validation_calendar_blocks" in valid:
            for value in valid["validation_calendar_blocks"].dropna().astype(str):
                blocks.update(token for token in value.split("|") if token)
        block_count = len(blocks) if blocks else int(sum(block_values))
        valid_symbols = int(valid["_symbol"].nunique())
        concentration = float(weights.max() / total_weight) if total_weight else np.nan
        reasons: list[str] = []
        if not np.isfinite(aggregate) or aggregate <= 0: reasons.append("non-positive aggregate paired delta log-loss")
        if not np.isfinite(positive) or positive <= 0.5: reasons.append("not positive in a majority of valid folds")
        if block_count < 2: reasons.append("fewer than two independent calendar blocks")
        if valid_symbols < 2: reasons.append("insufficient multi-symbol coverage")
        if np.isfinite(concentration) and concentration > 0.8: reasons.append("excessive single-symbol concentration")
        status = "S0_SURVIVOR" if not reasons else "S0_REJECTED"
        rows.append({"feature_id": feature_id, "timeframe": timeframe, "horizon": horizon, "availability_status": "HISTORICAL_AVAILABLE", "eligible_observations": int(total_weight), "valid_symbols": valid_symbols, "valid_temporal_folds": int(pd.to_numeric(valid["valid_temporal_folds"], errors="coerce").sum()) if not valid.empty else 0, "independent_calendar_block_count": block_count, "aggregate_paired_delta_log_loss": aggregate, "positive_fold_fraction": positive, "symbol_concentration": concentration, "brier_improvement": brier, "status": status, "rejection_reason": "; ".join(reasons)})
    complete = pd.DataFrame(rows)
    rejected = complete[complete["status"].ne("S0_SURVIVOR")].copy()
    return complete, rejected, cache

def build_s1_registry() -> pd.DataFrame:
    if len(S1_COMBINATIONS) > S1_MAX_COMBINATIONS:
        raise ValueError("S1 registry exceeds frozen combination cap")
    if any(len(combo) > S1_MAX_COMPONENTS for combo in S1_COMBINATIONS):
        raise ValueError("S1 registry exceeds frozen component cap")
    return pd.DataFrame([{"combination_id": f"S1_{i+1:02d}", "components": "|".join(c), "component_count": len(c), "trigger": c[0], "regime_filter": c[1], "participation_modifier": c[2], "role_grammar": S1_ROLE_GRAMMAR} for i, c in enumerate(S1_COMBINATIONS)])

def compose_role_aware_signal(frame: pd.DataFrame, *, trigger: str, regime_filter: str, participation: str) -> pd.Series:
    """Compose S1 without averaging unlike-scaled components.

    The trigger keeps its native value. The regime filter gates on a finite,
    non-zero state; participation confirms with RVOL >= 1 or a positive
    directional/ratio value. Failure yields an explicit zero.
    """
    required = {trigger, regime_filter, participation}
    if missing := required - set(frame.columns):
        raise ValueError(f"S1 role components missing: {', '.join(sorted(missing))}")
    trigger_values = pd.to_numeric(frame[trigger], errors="coerce")
    regime_values = pd.to_numeric(frame[regime_filter], errors="coerce")
    participation_values = pd.to_numeric(frame[participation], errors="coerce")
    trigger_sign = np.sign(trigger_values)
    regime_ok = regime_values.notna() & regime_values.ne(0)
    directional_trigger = trigger_values.abs().eq(1.0)
    regime_ok &= (~directional_trigger) | regime_values.mul(trigger_sign).gt(0)
    if participation == "rvol20":
        participation_ok = participation_values.ge(1.0)
    elif "ratio" in participation:
        participation_ok = participation_values.notna() & participation_values.ne(1.0)
        participation_ok &= (~directional_trigger) | ((trigger_sign.gt(0) & participation_values.gt(1.0)) | (trigger_sign.lt(0) & participation_values.lt(1.0)))
    else:
        participation_ok = participation_values.notna() & participation_values.gt(0)
    confirmed = trigger_values.notna() & regime_ok & participation_ok
    return trigger_values.where(confirmed, 0.0)

def _evaluate_s1(frame: pd.DataFrame, s0: pd.DataFrame, *, timeframe: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for i, combo in enumerate(S1_COMBINATIONS, 1):
        trigger, regime_filter, participation = combo
        trigger_gate = not s0.empty and s0["feature_id"].eq(trigger).any() and s0.loc[s0["feature_id"].eq(trigger), "status"].isin(("SURVIVOR", "S0_SURVIVOR")).any()
        coverage_ok = all(f in frame.columns and pd.to_numeric(frame[f], errors="coerce").notna().any() for f in combo)
        if not coverage_ok or not trigger_gate:
            reason = "component unavailable or incomplete coverage" if not coverage_ok else "primary trigger is not an S0 survivor"
            rows.append({"combination_id": f"S1_{i:02d}", "status": "REJECTED", "reason": reason, "role_grammar": S1_ROLE_GRAMMAR}); continue
        name = f"S1_{i:02d}_signal"; values = compose_role_aware_signal(frame, trigger=trigger, regime_filter=regime_filter, participation=participation); work = frame.copy(); work[name] = values
        result = evaluate_walk_forward(work, [name], horizons=("1h", "4h", "24h"), minimum_train=64, validation_size=32, step_size=32, source_timeframe=timeframe)
        result = result[result["model"].eq("I:" + name)] if not result.empty else result
        if result.empty: rows.append({"combination_id": f"S1_{i:02d}", "status": "REJECTED", "reason": "no valid causal folds", "role_grammar": S1_ROLE_GRAMMAR}); continue
        delta = pd.to_numeric(result["log_loss_improvement"], errors="coerce").dropna()
        rows.append({"combination_id": f"S1_{i:02d}", "status": "SURVIVOR" if float(delta.mean()) > 0 else "REJECTED", "aggregate_delta_log_loss": float(delta.mean()), "independent_block_count": _independent_blocks(result), "trade_rows": 0, "role_grammar": S1_ROLE_GRAMMAR})
    return pd.DataFrame(rows)

def _apply_cap(frame: pd.DataFrame, *, status: str, metric: str, id_column: str, cap: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep at most ``cap`` candidates by preregistered metric, never pad."""
    result = frame.copy()
    eligible = result[result["status"].eq(status)].copy()
    if len(eligible) <= cap:
        return result, eligible
    ranked = eligible.sort_values([metric, id_column], ascending=[False, True], kind="mergesort")
    keep = set(ranked.head(cap)[id_column].astype(str))
    excluded = result[ result["status"].eq(status) & ~result[id_column].astype(str).isin(keep)].copy()
    result.loc[result[id_column].astype(str).isin(set(excluded[id_column].astype(str))), "status"] = status + "_CAP_EXCLUDED"
    return result, result[result["status"].eq(status)].copy()

def _source_identity() -> dict[str, object]:
    """Compute implementation identity; never substitute a trusted constant."""
    root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).resolve().parent.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain=v1", "--untracked-files=all", "--", "src", "tests", "configs", "campaigns"], cwd=root, text=True)
    except (OSError, subprocess.CalledProcessError):
        commit, status = "UNKNOWN", "IDENTITY_UNAVAILABLE"
    return {"implementation_commit": commit, "scientific_source_clean": not bool(status.strip()), "source_tree_sha256": digest.hexdigest()}
def run_campaign(frame: pd.DataFrame, output: Path, *, timeframe: str = "1h", market: str = "um", split_manifest: dict | None = None) -> dict[str, int]:
    output.mkdir(parents=True, exist_ok=True); cache = FeatureCache(); complete_results, rejected, cache = screen_s0_complete(frame, timeframe=timeframe, horizons=("1h", "4h", "24h"), cache=cache, market=market)
    complete_results, s0_survivors = _apply_cap(complete_results, status="S0_SURVIVOR", metric="aggregate_paired_delta_log_loss", id_column="feature_id", cap=S0_MAX_SURVIVORS)
    rejected = pd.concat([rejected, complete_results[complete_results["status"].eq("S0_SURVIVOR_CAP_EXCLUDED")]], ignore_index=True)
    primitive_results = complete_results.copy(); primitive_results.to_csv(output / "S0_PRIMITIVE_RESULTS.csv", index=False); s0_survivors.to_csv(output / "S0_SURVIVORS.csv", index=False); rejected.to_csv(output / "S0_REJECTIONS.csv", index=False)
    pd.DataFrame([{"feature_id": f, "role": "primitive", "historical_status": "registered"} for f in DEFAULT_PRIMITIVES]).to_csv(output / "FEATURE_REGISTRY.csv", index=False)
    build_s1_registry().to_csv(output / "COMBINATION_REGISTRY.csv", index=False)
    policy = {"policy_id": "FAST_DISCOVERY_S0_S1_S2_V1", "positive_aggregate_delta": True, "majority_positive_folds": True, "minimum_independent_blocks": 2, "top_n": 10, "s1_max_combinations": S1_MAX_COMBINATIONS, "s1_max_components": S1_MAX_COMPONENTS, "s0_max_survivors": S0_MAX_SURVIVORS, "s1_max_survivors": S1_MAX_SURVIVORS, "s2_max_finalists": S2_MAX_FINALISTS, "role_grammar": S1_ROLE_GRAMMAR, "trade_rows_in_s0": False, "final_holdout": "UNTOUCHED"}
    (output / "SCREENING_POLICY.json").write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    s1_results = _evaluate_s1(frame, s0_survivors, timeframe=timeframe) if not s0_survivors.empty else pd.DataFrame(columns=["combination_id", "status", "reason"])
    s1_results, s1_survivors = _apply_cap(s1_results, status="SURVIVOR", metric="aggregate_delta_log_loss", id_column="combination_id", cap=S1_MAX_SURVIVORS)
    s1_results.to_csv(output / "S1_COMBINATION_RESULTS.csv", index=False); s1_survivors.to_csv(output / "S1_SURVIVORS.csv", index=False)
    _, finalists = _apply_cap(s1_survivors, status="SURVIVOR", metric="aggregate_delta_log_loss", id_column="combination_id", cap=S2_MAX_FINALISTS)
    finalists.insert(0, "candidate_id", finalists.get("combination_id", pd.Series(dtype=str))); finalists["trade_rows"] = 0; finalists.to_csv(output / "S2_FINALIST_RESULTS.csv", index=False)
    if split_manifest is None: split_manifest = {"split_id": "development-only", "final_holdout": "UNTOUCHED", "final_holdout_times": []}
    (output / "SPLIT_MANIFEST.json").write_text(json.dumps(split_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    provenance = {"market": market, "timeframe": timeframe, "input_rows": int(len(frame)), "source_columns": sorted(frame.columns.tolist()), "source_sha256": _source_hash(frame), **_source_identity(), "combination_registry_sha256": hashlib.sha256(build_s1_registry().to_csv(index=False).encode("utf-8")).hexdigest(), "screening_policy_sha256": hashlib.sha256((output / "SCREENING_POLICY.json").read_bytes()).hexdigest()}
    (output / "PROVENANCE_MANIFEST.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "FAST_DISCOVERY_PROTOCOL.md").write_text("# Fast Discovery V1\nDevelopment-only, outcome-blind S0/S1/S2 screening. S0 emits aggregate rows only; no trade rows are materialized.\n", encoding="utf-8")
    (output / "PREREGISTRATION.json").write_text(json.dumps({"protocol": "FAST_DISCOVERY_V1", "hypotheses": list(DEFAULT_PRIMITIVES), "holdout": "UNTOUCHED"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {"s0_candidates": len(DEFAULT_PRIMITIVES), "s0_survivors": int(len(s0_survivors)), "s1_combinations": len(S1_COMBINATIONS), "s1_survivors": int(len(s1_survivors)), "s2_finalists": int(len(finalists)), "cache_hits": cache.hits, "cache_misses": cache.misses, "trade_rows": 0}
    (output / "BENCHMARK_REPORT.md").write_text(json.dumps({"rows_read": len(frame), "cache_hits": cache.hits, "cache_misses": cache.misses, "development_only": True}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "FINAL_REPORT.md").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n" + ("NO CANDIDATES SURVIVED\n" if not finalists.shape[0] else "SHORTLIST GENERATED; NO TRADE ROWS\n"), encoding="utf-8")
    return summary

