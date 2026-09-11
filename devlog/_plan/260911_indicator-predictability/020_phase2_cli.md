# Phase 2 — CLI and artifacts

## Files

- MODIFY `src/binance_research/cli.py`
- MODIFY `README.md`
- NEW `tests/test_predictability_cli.py`

## Behavior

- Add `predictability audit`, `predictability run-development`,
  `predictability record-forward`, and `predictability evaluate-forward`.
- Write deterministic CSV/JSON/Markdown outputs without overwriting prior runs.
- Forward recording contains predictions and provenance but no realized labels.

## Acceptance

- Existing commands parse and behave unchanged.
- Synthetic data completes audit and development run without network access.
- Forward evaluation rejects missing or post-outcome predictions and reports
  evidence status rather than silently treating absent data as failure.
