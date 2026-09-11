import pandas as pd
from binance_research.forward import calendar_block_bootstrap

def test_multisymbol_synchronized_blocks_and_gap():
    times = pd.date_range("2025-01-01", periods=4, freq="15min", tz="UTC").tolist() + pd.date_range("2025-01-02", periods=4, freq="15min", tz="UTC").tolist()
    values = [0.1, -0.2, 0.3, -0.1] * 2
    stamps = times
    low, high = calendar_block_bootstrap(values, stamps, block_days=1, samples=32, seed=1729)
    assert low <= high
    assert len(set(pd.Timestamp(t).date() for t in stamps)) == 2
