# Predictability V1 multiple-testing plan

The primary family is frozen before any real-data campaign and is defined by HOLM_PRIMARY_FAMILY_V1.json (SHA256
8e89af6180faa8071addbc1b9741e972ad70c027299549a14b23b682e11162fd).

Each evaluated (horizon, feature_id, model=B1+I) member contributes one paired
delta-log-loss p-value. Holm step-down adjustment is applied at alpha 0.05 to
the complete observed family; family membership cannot be added after outcomes.
No historical outcomes or final-holdout rows are part of this artifact.
