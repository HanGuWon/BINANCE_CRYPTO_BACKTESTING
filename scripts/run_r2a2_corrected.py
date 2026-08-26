"""R2A.2 corrected runner: per-symbol execution, fold causal warmup, cached signals.

Fixes R2A2_ERRATUM_001: per-symbol state isolation, strictly-prior warmup
included in validation signal computation (warmup rows never scored/executed),
756-trial registry, committed implementation, signal caching for performance.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from r2a_engine import assert_no_holdout, load_panel_pre_holdout  # noqa: E402
from r2a_engine import compute_signal  # noqa: E402
from r2a2_folds import fold_bounds, STEP  # noqa: E402
from verify_r2a2_registry import HORIZONS_BY_TF  # noqa: E402

CAMPAIGN = ROOT / "campaigns" / "r2a2_temporal_horizon_v1"
DATA_ROOT = Path("data/processed/r1_gap_safe_cohort")
CHECKPOINT_ROOT = Path("D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a2/checkpoints_v1")
MARKETS = ("spot", "um")
TIMEFRAMES = ("15m", "1h", "4h")
COSTS = {"spot": {"fee": 10.0 / 10_000, "slip_total": 2 * 5.0 / 10_000}, "um": {"fee": 5.0 / 10_000, "slip_total": 2 * 5.0 / 10_000}}
HORIZON_BARS_24H = {"15m": 96, "1h": 24, "4h": 6}
OPERATIONAL_EMBARGO_BARS = 1
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


def execute_per_symbol(
    symbol_group: pd.DataFrame,
    *,
    feature_id: str,
    variant: str,
    market: str,
    side: str,
    horizon_bars: int,
    validation_start: pd.Timestamp,
    universe_top50: set[tuple[str, str, str]],
    funding_events: pd.DataFrame | None,
) -> pd.DataFrame:
    """Execute one trial on ONE SYMBOL with per-symbol state and causal warmup.

    symbol_group must contain the FULL pre-holdout history (strictly before
    holdout) for this symbol. Signals are computed causally over the whole
    history so the first validation bar has correct indicator values (fold
    causal warmup). Only rows with decision timestamp >= validation_start are
    scored; earlier rows initialize state only.
    """
    direction_base = 1 if side == "LONG" else -1
    fee_total = 2 * COSTS[market]["fee"]
    slip_total = COSTS[market]["slip_total"]
    group = symbol_group.reset_index(drop=True)
    signal = compute_signal(group, feature_id, variant, market)
    if len(signal) != len(group):
        raise ValueError("signal length mismatch")
    stamps = pd.to_datetime(group["timestamp"], utc=True)
    eligible = (group["row_class"] == "RESEARCH_ELIGIBLE").to_numpy() if "row_class" in group else np.ones(len(group), dtype=bool)
    months = group["universe_month"].to_numpy() if "universe_month" in group else np.array([""] * len(group))
    opens = group["open"].astype(float).to_numpy()
    records: list[dict[str, object]] = []
    next_available = 0  # per-symbol non-overlap state
    n = len(group)
    for decision in range(n):
        raw = float(signal.iloc[decision]) if decision < len(signal) and np.isfinite(float(signal.iloc[decision])) else 0.0
        if raw == 0.0 or not eligible[decision] or decision < next_available:
            continue
        if stamps.iloc[decision] < validation_start:
            continue  # warmup/context rows: state only, never scored
        month_key = str(months[decision])
        symbol_key = str(group["symbol"].iloc[0])
        if (market, month_key, symbol_key) not in universe_top50:
            continue
        entry_index = decision + 1  # canonical next-open
        exit_index = entry_index + horizon_bars
        if exit_index >= n or not np.isfinite(opens[entry_index]) or opens[entry_index] <= 0:
            continue
        gross = direction_base * (opens[exit_index] / opens[entry_index] - 1)
        funding_cashflow = 0.0
        if market == "um" and funding_events is not None and len(funding_events):
            crossed = funding_events[(funding_events.timestamp > stamps.iloc[entry_index]) & (funding_events.timestamp <= stamps.iloc[exit_index])]
            funding_cashflow = -direction_base * float(crossed.funding_rate.sum())
        net = gross - fee_total - slip_total + funding_cashflow
        records.append({
            "market": market, "timeframe": str(group["timeframe"].iloc[0]), "side": side, "symbol": symbol_key,
            "universe_month": month_key,
            "decision_time": stamps.iloc[decision].isoformat(),
            "entry_time": stamps.iloc[entry_index].isoformat(),
            "exit_time": stamps.iloc[exit_index].isoformat(),
            "gross_return": gross, "net_return": net, "funding_cashflow": funding_cashflow,
        })
        next_available = exit_index
    return pd.DataFrame.from_records(records)


def main() -> int:
    started = time.time()
    CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)
    registry = pd.read_csv(CAMPAIGN / "trial_registry.csv")
    folds = pd.read_csv(CAMPAIGN / "fold_registry.csv")
    registry_sha = _sha256_file(CAMPAIGN / "trial_registry.csv")
    implementation_sha = _git("rev-parse", "HEAD")
    manifest_path = CHECKPOINT_ROOT / "run_manifest.json"
    state: dict[str, object] = {}
    if manifest_path.exists():
        state = json.loads(manifest_path.read_text())
        if state.get("registry_sha256") != registry_sha or state.get("implementation_sha") != implementation_sha:
            raise RuntimeError("checkpoint settings mismatch; refusing resume with changed code/registry")
        print("resuming existing corrected run", flush=True)
    else:
        state = {
            "registry_sha256": registry_sha,
            "implementation_sha": implementation_sha,
            "checkpoint_root": str(CHECKPOINT_ROOT),
            "completed_units": [],
            "failed_units": [],
        }
        manifest_path.write_text(json.dumps(state, indent=2))
    completed = set(state["completed_units"])
    total_units = len(registry) * len(folds)
    print(f"R2A.2 corrected run: trials={len(registry)} folds={len(folds)} units={total_units}", flush=True)
    print(f"registry sha256={registry_sha[:16]} implementation={implementation_sha[:12]}", flush=True)
    universes = {m: _load_universe_top50(m) for m in MARKETS}
    # Cache funding events per symbol for the whole run.
    from r2a_engine import _funding_events as load_funding_events
    funding_cache_all: dict[str, pd.DataFrame | None] = {}
    def get_funding(symbol: str):
        if symbol not in funding_cache_all:
            funding_cache_all[symbol] = load_funding_events(symbol)
        return funding_cache_all[symbol]
    panels: dict[tuple[str, str], pd.DataFrame] = {}
    done_count = 0
    failed_before = len(state["failed_units"])
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
                    panels[key] = load_panel_pre_holdout(DATA_ROOT, trial.market, trial.timeframe, columns=None)
                    assert_no_holdout(panels[key], timeframe=trial.timeframe, context=f"panel {key}")
                panel = panels[key]
                validation_start, validation_end = fold_bounds(str(fold_row.fold_id))
                step = STEP[trial.timeframe]
                validation_end_exclusive = validation_end - step
                all_trades = []
                for symbol, symbol_group in panel.groupby("symbol", sort=True):
                    trades = execute_per_symbol(
                        symbol_group,
                        feature_id=trial.feature_id, variant=trial.variant,
                        market=trial.market, side=trial.side,
                        horizon_bars=int(trial.horizon_bars),
                        validation_start=validation_start + OPERATIONAL_EMBARGO_BARS * step,
                        universe_top50=universes[trial.market],
                        funding_events=get_funding(str(symbol)) if trial.market == "um" else None,
                    )
                    if not trades.empty:
                        trades = trades[trades.exit_time <= validation_end_exclusive.isoformat()]
                    if not trades.empty:
                        all_trades.append(trades)
                combined = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
                out = CHECKPOINT_ROOT / f"{trial.trial_id}_{fold_row.fold_id}_trades.parquet"
                combined.to_parquet(out, index=False)
                state["completed_units"].append(unit)
            except Exception as exc:
                state["failed_units"].append({"unit": unit, "error": repr(exc)})
                print(f"{unit} FAILED {exc!r}", flush=True)
            manifest_path.write_text(json.dumps(state, indent=2))
            done_count += 1
            if done_count % 250 == 0:
                print(f"progress {done_count}/{total_units} completed_units={len(state['completed_units'])}", flush=True)
    print(f"DONE elapsed={time.time()-started:.0f}s completed={len(set(state['completed_units']))}/{total_units} failed={len(state['failed_units'])-failed_before}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
