# WP8 — Provenance recomputation
MODIFY provenance helpers in src/binance_research/forward.py/CLI; NEW tamper tests and receipt.
Independently hash dataset snapshot, source tree, feature registry, baseline, config, cohort, and model; expected SHA mismatch fails closed.
Activation: mutate each byte source and assert rejection before prediction/evaluation.
