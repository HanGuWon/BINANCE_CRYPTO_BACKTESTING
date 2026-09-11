# WP0 — Integrated audit
MODIFY/NEW: devlog/_plan/260911_predictability_forward_hardening/010_wp0_audit.md; NEW audit receipt under same unit.
Audit src/binance_research/predictability_cli.py and src/binance_research/forward.py against all eight suspected gaps. Build counterexample fixtures for any confirmed defect; if refuted, cite call chain and passing assertion.
IN: audit and tests only. OUT: production behavior changes.
Verifier activation: run the audit fixture; each suspected path must either raise the expected failure or emit a proof record.

## Static audit evidence (2026-09-11)
Observed in src/binance_research/predictability_cli.py:125-176: record_forward calls build_forward_labels(enriched, ...) before prediction generation, uses full-frame labels, emits target_exit_time from label_frame, and iterates every row after train_end; this confirms prediction-region target access and historical-tail generation.
Observed at predictability_cli.py:136,174-175: one invocation timestamp is assigned to every row and immutable metadata.json is rewritten with changing prediction_rows; repeated runs can conflict.
Observed at predictability_cli.py:180-213: evaluate_forward rebuilds labels on the full input and scores probability_up only; it does not consume stored b1_probability_up as a paired baseline and does not call block-bootstrap or Holm helpers.
Observed at forward.py:67-82: holm_adjust and calendar_block_bootstrap exist as helpers, but static call-chain search found no evaluator call site.
Counterexample plan: WP1 sentinel, WP3 T0/T1/T2, WP5 comparator, WP6 inference, WP7 Holm, WP8-10 provenance/manifest tests will convert each confirmed point into executable proof.
