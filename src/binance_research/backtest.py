from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    fallback_spread_bps: float = 1.0
    slippage_bps: float = 1.0
    latency_bars: int = 0

    def __post_init__(self) -> None:
        if min(self.maker_fee_bps, self.taker_fee_bps, self.fallback_spread_bps, self.slippage_bps) < 0:
            raise ValueError("cost assumptions must be non-negative")
        if self.latency_bars < 0:
            raise ValueError("latency_bars must be non-negative")


@dataclass(frozen=True)
class BacktestResult:
    trades: pd.DataFrame
    summary: dict[str, object]
    by_direction: pd.DataFrame
    timeline: pd.Series


def _trade_excursions(
    highs: np.ndarray,
    lows: np.ndarray,
    entry_price: float,
    direction: int,
) -> tuple[float, float, int, int]:
    high_returns = direction * (highs / entry_price - 1)
    low_returns = direction * (lows / entry_price - 1)
    candidates = np.column_stack([high_returns, low_returns])
    favorable_per_bar = np.nanmax(candidates, axis=1)
    adverse_per_bar = np.nanmin(candidates, axis=1)
    return (
        float(np.nanmax(favorable_per_bar)),
        float(np.nanmin(adverse_per_bar)),
        int(np.nanargmax(favorable_per_bar)) + 1,
        int(np.nanargmin(adverse_per_bar)) + 1,
    )


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan
    equity = (1 + returns.astype(float)).cumprod()
    return float((equity / equity.cummax() - 1).min())


def _risk_metrics(timeline: pd.Series, periods_per_year: float) -> dict[str, float]:
    if timeline.empty:
        return {"sharpe": np.nan, "sortino": np.nan, "maximum_drawdown": np.nan, "calmar": np.nan}
    values = pd.to_numeric(timeline, errors="coerce").fillna(0.0)
    mean_return = float(values.mean())
    std = float(values.std(ddof=0))
    downside_deviation = float(np.sqrt(np.mean(np.minimum(values.to_numpy(), 0.0) ** 2)))
    maximum_drawdown = _max_drawdown(values)
    annual_return = mean_return * periods_per_year
    return {
        "sharpe": float(np.sqrt(periods_per_year) * mean_return / std) if std > 0 else np.nan,
        "sortino": float(np.sqrt(periods_per_year) * mean_return / downside_deviation) if downside_deviation > 0 else np.nan,
        "maximum_drawdown": maximum_drawdown,
        "calmar": float(annual_return / abs(maximum_drawdown)) if maximum_drawdown < 0 else np.nan,
    }


def summarize_trades(
    trades: pd.DataFrame,
    periods_per_year: float,
    total_bars: int,
    holding_bars: int,
    timeline: pd.Series | None = None,
) -> dict[str, object]:
    """Return trade metrics plus timeline risk metrics when a timeline is supplied."""
    risk = _risk_metrics(timeline if timeline is not None else pd.Series(dtype=float), periods_per_year)
    if trades.empty:
        return {
            "trade_count": 0, "exposure": 0.0, "turnover": 0.0,
            "gross_return": np.nan, "net_return": np.nan, "mean_trade": np.nan,
            "median_trade": np.nan, "expectancy": np.nan, "win_rate": np.nan,
            "average_win": np.nan, "average_loss": np.nan, "payoff_ratio": np.nan,
            "profit_factor": np.nan, "cvar_05": np.nan, "mean_mfe": np.nan,
            "mean_mae": np.nan, "median_holding_bars": np.nan,
            "long_trade_count": 0, "short_trade_count": 0,
            "evidence_status": "INSUFFICIENT EVIDENCE", **risk,
        }
    net = pd.to_numeric(trades["net_return"], errors="coerce")
    gross = pd.to_numeric(trades["gross_return"], errors="coerce")
    wins = net[net > 0]
    losses = net[net < 0]
    tail_cutoff = net.quantile(0.05)
    return {
        "trade_count": int(len(trades)),
        "exposure": float(min(1.0, len(trades) * holding_bars / max(total_bars, 1))),
        "turnover": float(2 * len(trades)),
        "gross_return": float((1 + gross).prod() - 1),
        "net_return": float((1 + net).prod() - 1),
        "mean_trade": float(net.mean()), "median_trade": float(net.median()),
        "expectancy": float(net.mean()), "win_rate": float((net > 0).mean()),
        "average_win": float(wins.mean()) if len(wins) else np.nan,
        "average_loss": float(losses.mean()) if len(losses) else np.nan,
        "payoff_ratio": float(wins.mean() / abs(losses.mean())) if len(wins) and len(losses) and losses.mean() else np.nan,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() else np.nan,
        **risk,
        "cvar_05": float(net[net <= tail_cutoff].mean()),
        "mean_mfe": float(trades["mfe"].mean()), "mean_mae": float(trades["mae"].mean()),
        "median_holding_bars": float(trades["holding_bars"].median()),
        "long_trade_count": int((trades["direction"] == 1).sum()),
        "short_trade_count": int((trades["direction"] == -1).sum()),
        "evidence_status": "ANALYZED",
    }


def _execution_scope(market_type: str) -> str:
    if market_type == "spot":
        return "spot_long_only"
    if market_type in {"um", "cm"}:
        return "futures_long_short"
    raise ValueError("market_type must be spot, um, or cm")


def _build_timeline(
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    fee_bps: float,
    slippage_bps: float,
    spread: np.ndarray,
    funding: np.ndarray,
) -> pd.Series:
    """Build one open-to-open return for every bar, including inactive bars."""
    timeline = pd.Series(0.0, index=bars.index, dtype=float)
    if trades.empty:
        return timeline
    opens = pd.to_numeric(bars["open"], errors="coerce").to_numpy(dtype=float)
    for trade in trades.itertuples(index=False):
        entry = int(trade.entry_bar)
        exit_bar = int(trade.exit_bar)
        direction = int(trade.direction)
        for bar in range(entry, exit_bar):
            if bar + 1 >= len(opens):
                continue
            period_return = direction * (opens[bar + 1] / opens[bar] - 1)
            period_return -= direction * float(funding[bar])
            if bar == entry:
                period_return -= fee_bps / 10_000
                period_return -= float(spread[entry]) / 2 / 10_000
                period_return -= slippage_bps / 10_000
            if bar == exit_bar - 1:
                period_return -= fee_bps / 10_000
                period_return -= float(spread[exit_bar]) / 2 / 10_000
                period_return -= slippage_bps / 10_000
            timeline.iloc[bar] += period_return
    return timeline


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "decision_bar", "entry_bar", "exit_bar", "decision_time", "entry_time", "exit_time",
        "direction", "entry_price", "exit_price", "gross_return", "fee_cost", "spread_cost",
        "slippage_cost", "funding_cost", "net_return", "mfe", "mae", "time_to_mfe",
        "time_to_mae", "holding_bars",
    ])


def run_backtest(
    bars: pd.DataFrame,
    signal: pd.Series,
    cost_model: CostModel,
    holding_bars: int = 4,
    fee_mode: str = "taker",
    interval_minutes: int = 60,
    market_type: str = "spot",
) -> BacktestResult:
    scope = _execution_scope(market_type)
    if holding_bars < 1:
        raise ValueError("holding_bars must be positive")
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    if fee_mode not in {"maker", "taker"}:
        raise ValueError("fee_mode must be maker or taker")
    required = {"open", "high", "low", "close"}
    if missing := required - set(bars.columns):
        raise ValueError(f"missing backtest columns: {', '.join(sorted(missing))}")
    signal_values = pd.to_numeric(signal.reindex(bars.index), errors="coerce").fillna(0.0)
    if market_type == "spot":
        signal_values = signal_values.clip(lower=0.0)
    if market_type in {"um", "cm"} and "funding_rate" not in bars:
        raise ValueError("futures backtests require an aligned funding_rate column; zero funding is not assumed")

    fee_bps = cost_model.taker_fee_bps if fee_mode == "taker" else cost_model.maker_fee_bps
    opens = pd.to_numeric(bars["open"], errors="coerce").to_numpy(dtype=float)
    highs = pd.to_numeric(bars["high"], errors="coerce").to_numpy(dtype=float)
    lows = pd.to_numeric(bars["low"], errors="coerce").to_numpy(dtype=float)
    funding_series = pd.to_numeric(bars.get("funding_rate", pd.Series(0.0, index=bars.index)), errors="coerce")
    raw_funding = funding_series.to_numpy(dtype=float)
    funding = np.nan_to_num(raw_funding, nan=0.0)
    spread = pd.to_numeric(bars.get("spread_bps", pd.Series(cost_model.fallback_spread_bps, index=bars.index)), errors="coerce").fillna(cost_model.fallback_spread_bps).to_numpy(dtype=float)
    timestamps = bars.get("open_time", pd.Series(bars.index, index=bars.index))
    records: list[dict[str, object]] = []
    next_available = 0
    for decision, raw_signal in enumerate(signal_values.to_numpy(dtype=float)):
        if not np.isfinite(raw_signal) or raw_signal == 0 or decision < next_available:
            continue
        direction = int(np.sign(raw_signal))
        entry = decision + 1 + cost_model.latency_bars
        exit_bar = entry + holding_bars
        if exit_bar >= len(bars) or opens[entry] <= 0 or opens[exit_bar] <= 0:
            continue
        if market_type in {"um", "cm"} and not np.isfinite(raw_funding[entry:exit_bar]).all():
            raise ValueError("funding_rate contains missing observations crossed by a futures position")
        entry_price = opens[entry]
        exit_price = opens[exit_bar]
        gross = direction * (exit_price / entry_price - 1)
        fee_cost = 2 * fee_bps / 10_000
        spread_cost = (spread[entry] + spread[exit_bar]) / 2 / 10_000
        slippage_cost = 2 * cost_model.slippage_bps / 10_000
        funding_cost = direction * float(np.sum(funding[entry:exit_bar]))
        mfe, mae, time_mfe, time_mae = _trade_excursions(highs[entry:exit_bar], lows[entry:exit_bar], entry_price, direction)
        records.append({
            "decision_bar": decision, "entry_bar": entry, "exit_bar": exit_bar,
            "decision_time": timestamps.iloc[decision], "entry_time": timestamps.iloc[entry], "exit_time": timestamps.iloc[exit_bar],
            "direction": direction, "entry_price": entry_price, "exit_price": exit_price,
            "gross_return": gross, "fee_cost": fee_cost, "spread_cost": spread_cost,
            "slippage_cost": slippage_cost, "funding_cost": funding_cost,
            "net_return": gross - fee_cost - spread_cost - slippage_cost - funding_cost,
            "mfe": mfe, "mae": mae, "time_to_mfe": time_mfe, "time_to_mae": time_mae,
            "holding_bars": holding_bars,
        })
        next_available = exit_bar

    trades = pd.DataFrame.from_records(records) if records else _empty_trades()
    periods_per_year = 365 * 24 * 60 / interval_minutes
    timeline = _build_timeline(bars, trades, fee_bps, cost_model.slippage_bps, spread, funding)
    summary = summarize_trades(trades, periods_per_year, len(bars), holding_bars, timeline)
    summary.update({
        "market_type": market_type, "execution_scope": scope,
        "funding_model": "bar_aligned_observations" if market_type in {"um", "cm"} else "not_applicable_spot",
        "funding_approximation": "funding_rate is charged for each crossed open-to-open bar; event-time funding requires event-level alignment",
        "fee_mode": fee_mode, "periods_per_year": periods_per_year,
        "timeline_observations": int(len(timeline)),
        "active_timeline_observations": int((timeline != 0).sum()),
        **{f"cost_{key}": value for key, value in asdict(cost_model).items()},
    })

    by_direction_records: list[dict[str, object]] = []
    for direction, label in ((1, "long"), (-1, "short")):
        group = trades[trades["direction"] == direction]
        if group.empty:
            continue
        direction_timeline = _build_timeline(bars, group, fee_bps, cost_model.slippage_bps, spread, funding)
        by_direction_records.append({
            "direction": label,
            **summarize_trades(group, periods_per_year, len(bars), holding_bars, direction_timeline),
        })
    return BacktestResult(trades, summary, pd.DataFrame.from_records(by_direction_records), timeline)
