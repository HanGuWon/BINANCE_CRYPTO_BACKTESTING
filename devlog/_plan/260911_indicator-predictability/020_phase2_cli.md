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

## WP2 provenance/forward continuation audit (2026-09-11)

- Repaired malformed forward-import source and added explicit numpy dependency.
- `record-forward` now separates `shadow-replay` and `prospective` modes, initializes the destination before model writes, rejects unexpected prior files, and uses write-once metadata/model artifacts.
- Prediction identity is canonical SHA-256 over campaign, market, symbol, timeframe, decision time, horizon, and model id; evaluator joins by immutable `decision_time` and recomputes identity (no positional `decision_index`).
- Model artifacts carry schema, model/training metadata, label and regularization contracts, and dataset/source/config/feature provenance hashes.
- Prediction appends are duplicate-refusing and atomically replaced via a temporary sibling file.
- Added focused contract tests covering identity, write-once behavior, duplicate refusal, holdout guard, paired scoring, Holm adjustment, calendar-block bootstrap, zero-return/NaN policy, and mean-loss regularization. Targeted WP1/WP2 regressions: 23 passed including 12 new contract tests.
- Scientific scope remains isolated to `research/predictability-v1`; no R3 process/data or historical outcome artifacts were accessed.
