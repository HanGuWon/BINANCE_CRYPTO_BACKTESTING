# WP12 — Adversarial tests
NEW/MODIFY tests only in tests/test_predictability_*.
Cover target sentinel, T0/T1/T2, immutable timestamps, no historical tail, shadow isolation, metadata high-water, same-cutoff no-op, B1 comparator, paired loss, inference, Holm, model/dataset/config/registry/prediction tamper, holdout rejection, restart, crash recovery, and synchronized blocks.
Activation: each named test fails on the pre-fix behavior and passes after fix; receipt lists all 20.
