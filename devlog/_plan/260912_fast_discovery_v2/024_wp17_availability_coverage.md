# WP17 — Historical availability and partial coverage

S0 complete-result rows now carry explicit source coverage fields per feature: `first_observed_time`, `last_observed_time`, `valid_rows`, `valid_symbols`, `valid_months`, and `coverage_fraction`. Missing causal label columns or absent features remain `HISTORICAL_UNAVAILABLE` and receive zero valid coverage; one feature's absence does not suppress unrelated candidates. Partial NaN coverage is reported rather than silently promoted to full availability.

Verification: targeted S0/S1/Fast Discovery regression tests passed (15 focused; 51 complete Fast Discovery family). No historical R2B outcome run or holdout access occurred.
