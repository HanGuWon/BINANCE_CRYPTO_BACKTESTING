from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

@pytest.fixture
def bars() -> pd.DataFrame:
    n = 500
    rng = np.random.default_rng(1729)
    returns = rng.normal(0.0002, 0.004, n)
    close = 100 * np.exp(np.cumsum(returns))
    open_ = np.r_[close[0], close[:-1]]
    spread = rng.uniform(0.05, 0.30, n)
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.lognormal(4.0, 0.4, n)
    taker = volume * rng.uniform(0.35, 0.65, n)
    open_time = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({
        "open_time": open_time,
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "close_time": open_time + pd.Timedelta(hours=1) - pd.Timedelta(milliseconds=1),
        "quote_volume": volume * close, "trade_count": np.arange(n) + 100,
        "taker_buy_volume": taker, "taker_buy_quote_volume": taker * close,
        "bid_price": close - 0.01, "ask_price": close + 0.01,
        "bid_qty": rng.uniform(1, 10, n), "ask_qty": rng.uniform(1, 10, n),
        "open_interest": 1_000 + np.cumsum(rng.normal(0, 2, n)),
        "funding_rate": np.where(np.arange(n) % 8 == 0, rng.normal(0.00005, 0.00002, n), 0.0),
        "premium": rng.normal(0, 0.0005, n),
        "btc_close": close,
        "breadth_pct_above_ema": rng.uniform(0.2, 0.8, n),
        "symbol": "BTCUSDT",
    })
