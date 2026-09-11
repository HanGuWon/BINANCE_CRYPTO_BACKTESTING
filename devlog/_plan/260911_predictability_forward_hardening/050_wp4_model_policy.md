# WP4 — Frozen-model policy
MODIFY campaigns/predictability_v1/campaign_spec.toml or isolated equivalent, src/binance_research/forward.py; NEW policy receipt.
Freeze FROZEN_MODEL_FORWARD_V1, training cutoff, model SHA, source dataset/features, regularization, and B0/B1/B1+I specification; reject unapproved refit.
Activation: second invocation with changed training prefix must fail closed unless explicit new campaign identity.
