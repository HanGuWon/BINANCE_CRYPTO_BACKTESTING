"""R2A.2 corrected runner v2: segment-safe causal state, real signal caching.

Fixes the follow-up audit P0s:
- signals computed per (symbol, segment_id) so no rolling/EWM/cumulative state
  crosses a candle gap; fold warmup may only use strictly-prior rows of the SAME segment;
- canonical signal cache keyed by (market, timeframe, symbol, segment_id, feature_id, variant):
  each causal signal series computed ONCE and reused across horizons/folds/sides;
- primary inference unit is the time-indexed aggregate portfolio series; per-trade rows descriptive.

Reuses the authoritative gap machinery in binance_research.features._gap_segments.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from r2a_engine import assert_no_holdout, load_panel_pre_holdout, compute_signal, _funding_events as load_funding_events  # noqa: E402
from r2a2_folds import fold_bounds, STEP, OPERATIONAL_EMBARGO_BARS  # noqa: E402

CAMPAIGN = ROOT / "campaigns" / "r2a2_temporal_horizon_v1"
DATA_ROOT = Path("data/processed/r1_gap_safe_cohort")
SHARD_INDEX = int(os.environ.get("R2A2_SHARD_INDEX", "0"))
SHARD_COUNT = int(os.environ.get("R2A2_SHARD_COUNT", "1"))
if not (0 <= SHARD_INDEX < SHARD_COUNT):
    raise ValueError("R2A2_SHARD_INDEX must be in [0, R2A2_SHARD_COUNT)")
CHECKPOINT_ROOT = Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a2") / (
    "checkpoints_v5" if SHARD_COUNT == 1 else f"checkpoints_v5_shard{SHARD_INDEX}"
)
MARKETS = ("spot", "um")
TIMEFRAMES = ("15m", "1h", "4h")
COSTS = {"spot": {"fee_total": 2 * 10.0 / 10_000, "slip_total": 2 * 5.0 / 10_000}, "um": {"fee_total": 2 * 5.0 / 10_000, "slip_total": 2 * 5.0 / 10_000}}
MINIMUM_TRADES_PER_FOLD = 30


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _load_universe_top50(market: str) -> set[tuple[str, str, str]]:
    universe = pd.read_csv(ROOT / "campaigns" / "r1_final_panel_v1" / "universe_monthly.csv", usecols=["market", "universe_month", "symbol", "selected_top50"])
    selected = universe[(universe.market == market) & universe.selected_top50.astype(bool)]
    return {(row.market, str(row.universe_month), row.symbol) for row in selected.itertuples(index=False)}


def compute_segment_signal(segment: pd.DataFrame, feature_id: str, variant: str, market: str) -> pd.Series:
    """Causal signal inside ONE gap segment only; state never crosses the boundary."""
    return compute_signal(segment.reset_index(drop=True), feature_id, variant, market)


def execute_segment(
    segment: pd.DataFrame,
    signal: pd.Series,
    *,
    market: str,
    side: str,
    horizon_bars: int,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
    universe_top50: set[tuple[str, str, str]],
    funding_events: pd.DataFrame | None,
) -> pd.DataFrame:
    """Score/execute only decisions inside [validation_start, validation_end).

    Warmup rows (strictly-prior SAME-segment rows) initialize indicator state via
    the precomputed signal series but are never scored or executed.
    """
    direction_base = 1 if side == "LONG" else -1
    costs = COSTS[market]
    group = segment.reset_index(drop=True)
    stamps = pd.to_datetime(group["timestamp"], utc=True)
    eligible = (group["row_class"] == "RESEARCH_ELIGIBLE").to_numpy() if "row_class" in group else np.ones(len(group), dtype=bool)
    months = group["universe_month"].to_numpy() if "universe_month" in group else np.array([""] * len(group))
    opens = group["open"].astype(float).to_numpy()
    symbol_key = str(group["symbol"].iloc[0])
    records: list[dict[str, object]] = []
    # No prior position exists before the first decision row.  Using -1 keeps
    # decision index 0 eligible while preserving horizon-based non-overlap.
    next_available = -1  # per-symbol non-overlap state within this segment
    n = len(group)
    for decision in range(n):
        raw = float(signal.iloc[decision]) if decision < len(signal) and np.isfinite(float(signal.iloc[decision])) else 0.0
        # Directional gate (follow-up audit P0): LONG requires signal == +1,
        # SHORT requires signal == -1. Never execute on the opposite sign.
        required_sign = 1.0 if side == "LONG" else -1.0
        if raw != required_sign or not eligible[decision] or decision <= next_available:
            continue
        if not (validation_start <= stamps.iloc[decision] < validation_end):
            continue  # warmup/state-only row
        month_key = str(months[decision])
        if (market, month_key, symbol_key) not in universe_top50:
            continue
        entry_index = decision + 1  # canonical next-open
        exit_index = entry_index + horizon_bars
        # Exit may run into post-validation bars for label completion; that is
        # still pre-holdout because all panels are holdout-filtered at load.
        if exit_index >= n or not np.isfinite(opens[entry_index]) or opens[entry_index] <= 0:
            continue
        gross = direction_base * (opens[exit_index] / opens[entry_index] - 1)
        funding_cashflow = 0.0
        if market == "um" and funding_events is not None and len(funding_events):
            crossed = funding_events[(funding_events.timestamp > stamps.iloc[entry_index]) & (funding_events.timestamp <= stamps.iloc[exit_index])]
            funding_cashflow = -direction_base * float(crossed.funding_rate.sum())
        net = gross - costs["fee_total"] - costs["slip_total"] + funding_cashflow
        records.append({
            "market": market, "timeframe": str(group["timeframe"].iloc[0]), "side": side, "symbol": symbol_key,
            "universe_month": month_key,
            "segment_first_ts": stamps.iloc[0].isoformat(),
            "decision_time": stamps.iloc[decision].isoformat(),
            "entry_time": stamps.iloc[entry_index].isoformat(),
            "exit_time": stamps.iloc[exit_index].isoformat(),
            "gross_return": gross, "net_return": net, "funding_cashflow": funding_cashflow,
            "signal_value": raw,
        })
        next_available = exit_index
    return pd.DataFrame.from_records(records)


def segment_frames(panel_symbol: pd.DataFrame, timeframe: str) -> list[tuple[int, pd.DataFrame]]:
    """Partition one symbol's history by authoritative gap machinery (segment boundaries)."""
    from binance_research.features import _gap_segments
    group = panel_symbol.reset_index(drop=True)
    _, segment_id, _ = _gap_segments(group, timeframe)
    return [(int(seg), group.loc[idx].copy()) for seg, idx in group.groupby(segment_id.to_numpy(), sort=False).groups.items()]


def main() -> int:
    started = time.time()
    CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)
    registry = pd.read_csv(CAMPAIGN / "trial_registry.csv")
    full_registry_count = len(registry)
    if SHARD_COUNT > 1:
        registry = registry.iloc[SHARD_INDEX::SHARD_COUNT].reset_index(drop=True)
    folds = pd.read_csv(CAMPAIGN / "fold_registry.csv")
    registry_sha = _sha256_file(CAMPAIGN / "trial_registry.csv")
    implementation_sha = _git("rev-parse", "HEAD")
    manifest_path = CHECKPOINT_ROOT / "run_manifest.json"
    state: dict[str, object] = {}
    if manifest_path.exists():
        state = json.loads(manifest_path.read_text())
        if state.get("registry_sha256") != registry_sha or state.get("implementation_sha") != implementation_sha:
            raise RuntimeError("checkpoint settings mismatch; refusing resume with changed code/registry")
        print("resuming existing v2 run", flush=True)
    else:
        state = {"registry_sha256": registry_sha, "implementation_sha": implementation_sha, "checkpoint_root": str(CHECKPOINT_ROOT), "shard_index": SHARD_INDEX, "shard_count": SHARD_COUNT, "full_registry_count": full_registry_count, "completed_units": [], "failed_units": []}
        manifest_path.write_text(json.dumps(state, indent=2))
    completed = set(state["completed_units"])
    total_units = len(registry) * len(folds)
    print(f"R2A.2 v2: shard={SHARD_INDEX}/{SHARD_COUNT} trials={len(registry)}/{full_registry_count} folds={len(folds)} units={total_units}", flush=True)
    print(f"registry sha256={registry_sha[:16]} implementation={implementation_sha[:12]}", flush=True)
    universes = {m: _load_universe_top50(m) for m in MARKETS}
    funding_cache_all: dict[str, pd.DataFrame | None] = {}
    def get_funding(symbol: str):
        if symbol not in funding_cache_all:
            funding_cache_all[symbol] = load_funding_events(symbol)
        return funding_cache_all[symbol]
    panels: dict[tuple[str, str], dict[str, list[tuple[int, pd.DataFrame]]]] = {}
    # Canonical signal cache: (market, tf, symbol, segment_id, feature_id, variant) -> Series
    signal_cache: dict[tuple, pd.Series] = {}
    done_count = 0
    for _, trial in registry.iterrows():
        for _, fold_row in folds.iterrows():
            unit = f"{trial.trial_id}|{fold_row.fold_id}"
            if unit in completed:
                done_count += 1
                continue
            try:
                key = (trial.market, trial.timeframe)
                if key not in panels:
                    print(f"loading panel {key}", flush=True)
                    raw_panel = load_panel_pre_holdout(DATA_ROOT, trial.market, trial.timeframe, columns=None)
                    assert_no_holdout(raw_panel, timeframe=trial.timeframe, context=f"panel {key}")
                    panels[key] = {sym: segment_frames(g.reset_index(drop=True), trial.timeframe) for sym, g in raw_panel.groupby("symbol", sort=True)}
                segments_by_symbol = panels[key]
                validation_start, validation_end = fold_bounds(str(fold_row.fold_id))
                step = STEP[trial.timeframe]
                validation_start_eff = validation_start + OPERATIONAL_EMBARGO_BARS * step
                all_trades = []
                for symbol, segments in sorted(segments_by_symbol.items()):
                    funding_events = get_funding(str(symbol)) if trial.market == "um" else None
                    for seg_id, segment in segments:
                        cache_key = (trial.market, trial.timeframe, str(symbol), int(seg_id), trial.feature_id, trial.variant)
                        if cache_key not in signal_cache:
                            signal_cache[cache_key] = compute_segment_signal(segment, trial.feature_id, trial.variant, trial.market)
                        signal = signal_cache[cache_key]
                        t = execute_segment(
                            segment, signal, market=trial.market, side=trial.side,
                            horizon_bars=int(trial.horizon_bars),
                            validation_start=validation_start_eff, validation_end=validation_end,
                            universe_top50=universes[trial.market], funding_events=funding_events,
                        )
                        if not t.empty:
                            all_trades.append(t)
                combined = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
                out = CHECKPOINT_ROOT / f"{trial.trial_id}_{fold_row.fold_id}_trades.parquet"
                combined.to_parquet(out, index=False)
                state["completed_units"].append(unit)
            except Exception as exc:
                state["failed_units"].append({"unit": unit, "error": repr(exc)})
                print(f"{unit} FAILED {exc!r}", flush=True)
            manifest_path.write_text(json.dumps(state, indent=2))
            done_count += 1
            if done_count % 500 == 0:
                print(f"progress {done_count}/{total_units} completed_units={len(state['completed_units'])} cached_signals={len(signal_cache)}", flush=True)
    print(f"DONE elapsed={time.time()-started:.0f}s completed={len(set(state['completed_units']))}/{total_units} failed={len(state['failed_units'])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
