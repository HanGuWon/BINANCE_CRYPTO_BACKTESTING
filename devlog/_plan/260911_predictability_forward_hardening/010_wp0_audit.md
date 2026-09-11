# WP0 — Integrated audit
MODIFY/NEW: devlog/_plan/260911_predictability_forward_hardening/010_wp0_audit.md; NEW audit receipt under same unit.
Audit src/binance_research/predictability_cli.py and src/binance_research/forward.py against all eight suspected gaps. Build counterexample fixtures for any confirmed defect; if refuted, cite call chain and passing assertion.
IN: audit and tests only. OUT: production behavior changes.
Verifier activation: run the audit fixture; each suspected path must either raise the expected failure or emit a proof record.
