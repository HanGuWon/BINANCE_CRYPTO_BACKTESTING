from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_bars(rows: int = 1_000, timeframe_minutes: int = 60, seed: int = 1729) -> pd.DataFrame:
    """Deterministic integrity/smoke fixture. It is not empirical market evidence."""
    if rows < 250:
        raise ValueError("at least 250 rows are required for core feature warmups")
    if timeframe_minutes < 1:
        raise ValueError("timeframe_minutes must be positive")
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(0.0, 0.004, rows)
    close = 50_000 * np.exp(np.cumsum(log_returns))
    open_ = np.r_[close[0], close[:-1]]
    range_width = close * rng.uniform(0.0005, 0.004, rows)
    high = np.maximum(open_, close) + range_width
    low = np.minimum(open_, close) - range_width
    volume = rng.lognormal(3.5, 0.6, rows)
    taker_buy = volume * rng.uniform(0.30, 0.70, rows)
    open_time = pd.date_range("2022-01-01", periods=rows, freq=f"{timeframe_minutes}min", tz="UTC")
    close_time = open_time + pd.Timedelta(minutes=timeframe_minutes) - pd.Timedelta(milliseconds=1)
    return pd.DataFrame({
        "open_time": open_time, "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "close_time": close_time, "quote_volume": volume * close,
        "trade_count": rng.integers(100, 10_000, rows), "taker_buy_volume": taker_buy,
        "taker_buy_quote_volume": taker_buy * close, "bid_price": close - 0.5,
        "ask_price": close + 0.5, "bid_qty": rng.uniform(0.1, 20, rows),
        "ask_qty": rng.uniform(0.1, 20, rows), "open_interest": 100_000 + np.cumsum(rng.normal(0, 50, rows)),
        "funding_rate": np.where(np.arange(rows) % 8 == 0, rng.normal(0.00005, 0.00003, rows), 0.0),
        "premium": rng.normal(0, 0.0005, rows), "btc_close": close,
        "breadth_pct_above_ema": rng.uniform(0.2, 0.8, rows), "symbol": "SYNTHETIC",
        "data_source": "synthetic_non_evidentiary",
    })
