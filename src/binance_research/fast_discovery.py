"""Outcome-blind Fast Discovery funnel with deterministic cached screening."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Callable, Iterable
import numpy as np
import pandas as pd
from .predictability import evaluate_walk_forward

DEFAULT_PRIMITIVES = ("donchian_breakout20", "roc6", "rvol20", "vwap_deviation20", "taker_buy_sell_ratio", "cvd_slope6", "bb_bandwidth20", "premium", "premium_zscore90")
S1_COMBINATIONS = (("donchian_breakout20", "ema20_slope_5", "rvol20"), ("roc6", "sig_ema20_50", "taker_buy_sell_ratio"), ("bb_bandwidth20", "donchian_breakout20", "rvol20"), ("premium_zscore90", "sig_ema20_50", "rvol20"))

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

def build_s1_registry() -> pd.DataFrame:
    return pd.DataFrame([{"combination_id": f"S1_{i+1:02d}", "components": "|".join(c), "component_count": len(c), "trigger": c[0], "regime_filter": c[1], "participation_modifier": c[2]} for i, c in enumerate(S1_COMBINATIONS)])

def _evaluate_s1(frame: pd.DataFrame, s0: pd.DataFrame, *, timeframe: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for i, combo in enumerate(S1_COMBINATIONS, 1):
        if not all(f in frame.columns for f in combo) or not s0["feature_id"].isin(combo).any():
            rows.append({"combination_id": f"S1_{i:02d}", "status": "REJECTED", "reason": "component unavailable or not an S0 survivor"}); continue
        name = f"S1_{i:02d}_signal"; values = frame[list(combo)].apply(pd.to_numeric, errors="coerce").mean(axis=1); work = frame.copy(); work[name] = values
        result = evaluate_walk_forward(work, [name], horizons=("1h", "4h", "24h"), minimum_train=64, validation_size=32, step_size=32, source_timeframe=timeframe)
        result = result[result["model"].eq("I:" + name)] if not result.empty else result
        if result.empty: rows.append({"combination_id": f"S1_{i:02d}", "status": "REJECTED", "reason": "no valid causal folds"}); continue
        delta = pd.to_numeric(result["log_loss_improvement"], errors="coerce").dropna()
        rows.append({"combination_id": f"S1_{i:02d}", "status": "SURVIVOR" if float(delta.mean()) > 0 else "REJECTED", "aggregate_delta_log_loss": float(delta.mean()), "independent_block_count": _independent_blocks(result), "trade_rows": 0})
    return pd.DataFrame(rows)

def run_campaign(frame: pd.DataFrame, output: Path, *, timeframe: str = "1h", market: str = "um", split_manifest: dict | None = None) -> dict[str, int]:
    output.mkdir(parents=True, exist_ok=True); cache = FeatureCache(); s0_survivors, rejected = screen_s0(frame, timeframe=timeframe, cache=cache, market=market)
    primitive_results = s0_survivors.copy(); primitive_results.to_csv(output / "S0_PRIMITIVE_RESULTS.csv", index=False); s0_survivors.to_csv(output / "S0_SURVIVORS.csv", index=False); rejected.to_csv(output / "S0_REJECTIONS.csv", index=False)
    pd.DataFrame([{"feature_id": f, "role": "primitive", "historical_status": "registered"} for f in DEFAULT_PRIMITIVES]).to_csv(output / "FEATURE_REGISTRY.csv", index=False)
    build_s1_registry().to_csv(output / "COMBINATION_REGISTRY.csv", index=False)
    policy = {"policy_id": "FAST_DISCOVERY_S0_S1_S2_V1", "positive_aggregate_delta": True, "majority_positive_folds": True, "minimum_independent_blocks": 2, "top_n": 10, "trade_rows_in_s0": False, "final_holdout": "UNTOUCHED"}
    (output / "SCREENING_POLICY.json").write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    s1_results = _evaluate_s1(frame, s0_survivors, timeframe=timeframe) if not s0_survivors.empty else pd.DataFrame(columns=["combination_id", "status", "reason"])
    s1_results.to_csv(output / "S1_COMBINATION_RESULTS.csv", index=False); s1_results[s1_results.get("status", pd.Series(dtype=str)).eq("SURVIVOR")].to_csv(output / "S1_SURVIVORS.csv", index=False)
    finalists = s1_results[s1_results.get("status", pd.Series(dtype=str)).eq("SURVIVOR")].copy(); finalists.insert(0, "candidate_id", finalists.get("combination_id", pd.Series(dtype=str))); finalists["trade_rows"] = 0; finalists.to_csv(output / "S2_FINALIST_RESULTS.csv", index=False)
    if split_manifest is None: split_manifest = {"split_id": "development-only", "final_holdout": "UNTOUCHED", "final_holdout_times": []}
    (output / "SPLIT_MANIFEST.json").write_text(json.dumps(split_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    provenance = {"market": market, "timeframe": timeframe, "input_rows": int(len(frame)), "source_columns": sorted(frame.columns.tolist()), "source_sha256": _source_hash(frame)}
    (output / "PROVENANCE_MANIFEST.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "FAST_DISCOVERY_PROTOCOL.md").write_text("# Fast Discovery V1\nDevelopment-only, outcome-blind S0/S1/S2 screening. S0 emits aggregate rows only; no trade rows are materialized.\n", encoding="utf-8")
    (output / "PREREGISTRATION.json").write_text(json.dumps({"protocol": "FAST_DISCOVERY_V1", "hypotheses": list(DEFAULT_PRIMITIVES), "holdout": "UNTOUCHED"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {"s0_candidates": len(DEFAULT_PRIMITIVES), "s0_survivors": int(len(s0_survivors)), "s1_combinations": len(S1_COMBINATIONS), "s1_survivors": int(len(finalists)), "s2_finalists": int(len(finalists)), "cache_hits": cache.hits, "cache_misses": cache.misses, "trade_rows": 0}
    (output / "BENCHMARK_REPORT.md").write_text(json.dumps({"rows_read": len(frame), "cache_hits": cache.hits, "cache_misses": cache.misses, "development_only": True}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "FINAL_REPORT.md").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n" + ("NO CANDIDATES SURVIVED\n" if not finalists.shape[0] else "SHORTLIST GENERATED; NO TRADE ROWS\n"), encoding="utf-8")
    return summary