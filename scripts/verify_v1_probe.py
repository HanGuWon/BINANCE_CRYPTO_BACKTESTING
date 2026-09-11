import json
path='campaigns/fast_discovery_v1/V1_PROBE_RECEIPT.json'
data=json.load(open(path))
assert data['registered_primitives']==9 and data['historical_unavailable']==9 and data['scored_primitives']==0 and data['s0_predictive_tests']==0 and data['s1_evaluations']==0 and data['s2_trading_replays']==0
print('WP0 probe verification PASS')