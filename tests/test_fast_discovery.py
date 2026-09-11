import pandas as pd
from binance_research.fast_discovery import FeatureCache, build_s1_registry, canonical_cache_key, run_campaign, screen_s0

def test_s0_missing_label_columns_fails_closed():
    survivors, rejected = screen_s0(pd.DataFrame({"premium":[0.1]}))
    assert survivors.empty
    assert set(rejected.status) == {"HISTORICAL_UNAVAILABLE"}

def test_cache_key_and_s1_grammar():
    cache = FeatureCache(); key = canonical_cache_key("um","1h","BTCUSDT","seg","roc6","raw","abc")
    assert cache.get(key, lambda: pd.Series([1])) is cache.get(key, lambda: pd.Series([2]))
    assert cache.hits == 1 and len(build_s1_registry()) == 4
    assert (build_s1_registry()["components"] <= 3).all()

def test_campaign_writes_zero_trade_finalist_artifacts(tmp_path):
    frame = pd.DataFrame({"premium":[0.1,0.2], "symbol":["BTCUSDT"]*2})
    summary = run_campaign(frame, tmp_path)
    assert summary["s0_survivors"] == 0
    assert (tmp_path/"S2_FINALIST_RESULTS.csv").exists()
