# WP9 — Model artifact verification
MODIFY evaluator; NEW tests/test_predictability_artifact_verification.py.
At evaluation recompute model artifact SHA and verify campaign identity, feature spec, cutoff, dataset/config lineage; unverifiable predictions are ineligible.
Activation: tamper artifact bytes and assert explicit rejection/ineligibility.
