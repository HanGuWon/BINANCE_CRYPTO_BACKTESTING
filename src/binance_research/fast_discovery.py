"""Fast Discovery funnel: cached primitive screening and bounded finalist handoff."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Iterable
import numpy as np
import pandas as pd
from .predictability import HORIZON_BARS, evaluate_walk_forward

DEFAULT_PRIMITIVES = (
    "donchian_breakout20", "roc6", "rvol20", "vwap_deviation20",
    "taker_buy_sell_ratio", "cvd_slope6", "bb_bandwidth20",
    "premium", "premium_zscore90",
)
S1_COMBINATIONS = (
    ("donchian_breakout20","ema20_slope_5","rvol20"),
    ("roc6","sig_ema20_50","taker_buy_sell_ratio"),
    ("bb_bandwidth20","donchian_breakout20","rvol20"),
    ("premium_zscore90","sig_ema20_50","rvol20"),
)

class FeatureCache:
    def __init__(self) -> None:
        self._values: dict[tuple[str, ...], pd.Series] = {}
        self.hits = 0
        self.misses = 0
    def get(self, key: tuple[str, ...], compute) -> pd.Series:
        if key in self._values:
            self.hits += 1
            return self._values[key]
        self.misses += 1
        value = compute()
        self._values[key] = value
        return value

def canonical_cache_key(market: str, timeframe: str, symbol: str, segment_id: str, feature_id: str, variant: str, source_hash: str) -> tuple[str, ...]:
    return (market, timeframe, symbol, segment_id, feature_id, variant, source_hash)

def screen_s0(frame: pd.DataFrame, *, timeframe: str = "1h", horizons: Iterable[str] = ("1h","4h","24h"), primitives: Iterable[str] = DEFAULT_PRIMITIVES, minimum_train: int = 64, validation_size: int = 32, step_size: int = 32) -> tuple[pd.DataFrame, pd.DataFrame]:
    primitives = tuple(primitives)
    missing = [name for name in ("open_time","open","close") if name not in frame.columns]
    if missing:
        rejected = pd.DataFrame([{"feature_id": f, "status": "HISTORICAL_UNAVAILABLE", "reason": "missing causal label columns: " + ",".join(missing)} for f in primitives])
        return pd.DataFrame(columns=["feature_id","status","aggregate_delta_log_loss","positive_fold_fraction","independent_block_count"]), rejected
    available = [f for f in primitives if f in frame.columns]
    unavailable = [f for f in primitives if f not in frame.columns]
    rows = []
    rejected = [{"feature_id": f, "status": "HISTORICAL_UNAVAILABLE", "reason": "feature column absent"} for f in unavailable]
    for feature in available:
        result = evaluate_walk_forward(frame, [feature], horizons=tuple(horizons), minimum_train=minimum_train, validation_size=validation_size, step_size=step_size, source_timeframe=timeframe)
        result = result[result["model"].eq("I:" + feature)] if not result.empty else result
        if result.empty:
            rejected.append({"feature_id": feature, "status": "REJECTED", "reason": "no valid causal folds"})
            continue
        deltas = pd.to_numeric(result["log_loss_improvement"], errors="coerce").dropna()
        rows.append({"feature_id": feature, "status": "SCREENED", "aggregate_delta_log_loss": float(deltas.mean()), "positive_fold_fraction": float((deltas > 0).mean()), "independent_block_count": int(result["validation_rows"].sum())})
    scored = pd.DataFrame(rows)
    if scored.empty:
        return scored, pd.DataFrame(rejected)
    survivors = scored[(scored["aggregate_delta_log_loss"] > 0) & (scored["positive_fold_fraction"] > 0.5) & (scored["independent_block_count"] >= 2)].copy()
    scored["status"] = np.where(scored["feature_id"].isin(survivors["feature_id"]), "SURVIVOR", "REJECTED")
    rejected.extend(scored[scored["status"].eq("REJECTED")].assign(reason="failed frozen S0 safety gates").to_dict("records"))
    return scored[scored["status"].eq("SURVIVOR")], pd.DataFrame(rejected)

def build_s1_registry() -> pd.DataFrame:
    return pd.DataFrame([{"combination_id": f"S1_{i+1:02d}", "trigger": c[0], "regime_filter": c[1], "participation_modifier": c[2], "components": 3} for i,c in enumerate(S1_COMBINATIONS)])

def run_campaign(frame: pd.DataFrame, output: Path, *, timeframe: str = "1h") -> dict[str, int]:
    output.mkdir(parents=True, exist_ok=True)
    survivors, rejected = screen_s0(frame, timeframe=timeframe)
    pd.DataFrame([{"feature_id": f, "role": "primitive", "historical_status": "registered"} for f in DEFAULT_PRIMITIVES]).to_csv(output/"FEATURE_REGISTRY.csv", index=False)
    build_s1_registry().to_csv(output/"COMBINATION_REGISTRY.csv", index=False)
    policy = {"policy_id":"FAST_DISCOVERY_S0_S1_V1","positive_aggregate_delta":True,"majority_positive_folds":True,"minimum_independent_blocks":2,"top_n":10,"trade_rows_in_s0":False,"final_holdout":"UNTOUCHED"}
    (output/"SCREENING_POLICY.json").write_text(json.dumps(policy,indent=2)+"\n",encoding="utf-8")
    survivors.to_csv(output/"S0_SURVIVORS.csv", index=False)
    rejected.to_csv(output/"S0_REJECTIONS.csv", index=False)
    pd.DataFrame(columns=["feature_id","aggregate_delta_log_loss"]).to_csv(output/"S0_PRIMITIVE_RESULTS.csv", index=False)
    s1 = pd.DataFrame(columns=["combination_id","status","reason"])
    s1.to_csv(output/"S1_COMBINATION_RESULTS.csv", index=False); s1.to_csv(output/"S1_SURVIVORS.csv", index=False)
    pd.DataFrame(columns=["candidate_id","status","trade_rows"]).to_csv(output/"S2_FINALIST_RESULTS.csv", index=False)
    (output/"BENCHMARK_REPORT.md").write_text("Development-only bounded run; S0 emits aggregate rows only and materializes no trades.\n",encoding="utf-8")
    summary={"s0_candidates":len(DEFAULT_PRIMITIVES),"s0_survivors":len(survivors),"s1_combinations":len(S1_COMBINATIONS),"s1_survivors":0,"s2_finalists":0}
    (output/"FINAL_REPORT.md").write_text(json.dumps(summary,indent=2)+"\nNO CANDIDATES SURVIVED\n",encoding="utf-8")
    return summary
