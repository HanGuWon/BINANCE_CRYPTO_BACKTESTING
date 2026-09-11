# Fast Discovery implementation phase

This phase adds a separate, outcome-blind Fast Discovery funnel for development data. It consumes the repaired causal feature frame, caches deterministic feature materialization, screens registered primitives with the existing forward evaluator, and emits aggregate-only S0/S1/S2 artifacts. It never reads the final holdout and never writes trade rows during S0.

## Loop specification
- Loop archetype: satisfy-spec implementation with bounded development-only campaign handoff.
- Trigger: completion of `fast-discovery-audit` repaired calendar-block inference and concrete split contract.
- Goal: implement the frozen S0/S1/S2 funnel and a reproducible bounded-run surface.
- Non-goals: no historical R2B/R2B2/R3 outcomes, no holdout access, no threshold or horizon search, no source changes outside the isolated `research/predictability-v1` worktree.
- Verifier: `python -m pytest -q tests/test_fast_discovery.py tests/test_predictability_forward_contracts.py tests/test_predictability_comparison.py`; this directly imports `src/binance_research/fast_discovery.py` and executes `scripts/run_fast_discovery.py` only in later qualification/development phases. Conditional paths are activated by missing OHLC columns (fail-closed `HISTORICAL_UNAVAILABLE`), cache reuse (hit counter), and zero-survivor S1/S2 handoff (empty aggregate artifacts, no trade rows).
- Stop condition: implementation is committed and the targeted tests pass; later work-phases perform qualification, bounded development run, and closeout.
- Memory artifact: this numbered plan, `.codexclaw/evidence/.../test-receipt.json`, and campaign artifacts under `campaigns/fast_discovery_v1/`.
- Expected terminal outcomes: DONE with committed implementation and tests; BLOCKED if causal input cannot be loaded without violating holdout/isolation; UNSAFE if any outcome or holdout access is detected.
- Escalation condition: stop and ask the user only if a required causal source or immutable manifest is unavailable; do not broaden scope or run outcomes.

## Diff-level file map
- `src/binance_research/fast_discovery.py` MODIFY: define `DEFAULT_PRIMITIVES`, fixed four-entry `S1_COMBINATIONS`, `FeatureCache`, canonical cache keys, fail-closed S0 screening, registry serialization, and aggregate-only campaign output. S0 consumes `open_time/open/close` when present; absent columns activate `HISTORICAL_UNAVAILABLE` rejection. No serialized trade schema is created in S0.
- `scripts/run_fast_discovery.py` MODIFY: load only the causal input columns needed by the screen, reject missing/holdout paths, invoke `run_campaign`, and emit deterministic summary/benchmark metadata. CLI creation -> JSON/CSV output -> readback occurs in the same script; no downstream consumer treats S0 rows as trades.
- `tests/test_fast_discovery.py` MODIFY: prove missing-label fail-closed behavior, cache-key determinism/hit accounting, fixed three-component S1 grammar, no S0 trade rows, and deterministic rerun hashes.
- `campaigns/fast_discovery_v1/` NEW (later development phase): protocol, preregistration, registries, split/provenance manifests, benchmark, final report, and compact CSV/JSON aggregates only. Large parquet/raw/cache files remain outside Git.
- `devlog/_plan/260911_predictability_v1/020_fast_discovery_implementation.md` MODIFY: this plan is the source-of-truth for this phase and will be archived by D.

## Field-chain checks
`feature_id`, `combination_id`, `status`, and aggregate metric fields are created in the Python result dictionaries/DataFrames, serialized by `to_csv`/`json.dumps`, read by pandas/JSON in verification, and consumed only by the campaign reports/tests. `trade_rows` is an aggregate count in S2 output, not a trade record; it remains zero in S0. No enum values or persisted dataclass fields are added.

## Bypass / residual risk
- Tier: E1/E2 (local CLI and test gate).
- Executing surface: `run_fast_discovery.py` plus pytest.
- Known bypass: a user could invoke the module directly with an arbitrary frame; this is why the CLI rejects non-causal/holdout inputs and reports provenance.
- Residual risk: synthetic or incomplete development frames may produce zero survivors; this is reported as `HISTORICAL_UNAVAILABLE`, never promoted to evidence of predictive failure.
- Wording downgrade: tests and reports say development-only/aggregate-only, not validated strategy performance.

## Acceptance criteria and activation
1. Import and compile succeeds; direct target: `src/binance_research/fast_discovery.py` (run in C).
2. Missing `open_time/open/close` yields one fail-closed rejection per primitive and zero survivors; activation fixture is a causal premium parquet lacking OHLC.
3. Reusing an identical canonical key increments `FeatureCache.hits` and does not recompute; activation is the second `get` call in `tests/test_fast_discovery.py`.
4. Every S1 registry row has exactly three components and S0/S1/S2 outputs contain no trade rows; activation is campaign writer test and empty finalist readback.
5. Re-running on the same frame produces byte-identical compact artifacts; activation is two temporary output roots compared by SHA256 in the targeted test.
6. Targeted verifier exits 0 and reads every changed implementation/test path; C receipt is the authoritative evidence.

## Audit synthesis / amendment (round 1)
The independent review found seven blockers. They are folded into the build scope rather than waived:

- Implement actual S1 combination evaluation and S2 finalist-only replay, conditional on non-empty S0 survivors; preserve empty outputs and explicit `NO CANDIDATES SURVIVED` when no candidate qualifies.
- Wire `FeatureCache` into S0 materialization/evaluation with canonical keys and expose deterministic hit/miss counters in the benchmark report.
- Replace row-count gating with true independent calendar-block counting. The implementation will derive block IDs from validation decision timestamps (or, if evaluator output lacks them, extend the result schema to carry them) and test two rows in one block versus two distinct blocks.
- Harden `scripts/run_fast_discovery.py`: inspect schema before reading, select only required columns, require the causal dataset root and concrete split manifest, reject final-holdout intersections, unexpected market/schema, and missing provenance; no `columns=None` path.
- Register/materialize all S1 component features (`ema20_slope_5`, `sig_ema20_50`) or remove them from the fixed grammar; the chosen path must produce a closed registry chain and deterministic output.
- Make the verifier exercise CLI, non-empty synthetic S0/S1/S2 activation, holdout rejection, cache reuse, block-count semantics, output readback, and byte-identical rerun hashes.
- Add required compact protocol/preregistration/split/provenance/receipt artifacts in the campaign writer while keeping large data external.

Re-audit activation scenarios: synthetic OHLC frame activates S0 and S1/S2; same-frame repeated feature requests activate cache hits; a concrete holdout timestamp activates CLI rejection; duplicated rows within one calendar block activate block-count distinction. Residual risk is limited to unavailable historical OHLC in the repaired premium parquet, which must yield a documented fail-closed zero-survivor development run.

## Audit rebuttal / executable build contract
The residual findings describe the intentionally pre-build state of the implementation, not omissions in this plan. B is authorized to close each item with the following concrete edits before any campaign run:

- `screen_s0` will accept an injected `FeatureCache`, cache each `(market,timeframe,symbol,segment,feature,variant,source_hash)` series, and carry a `validation_block_count` derived from `decision_time.dt.floor("D")` unique IDs; the old `validation_rows.sum()` expression is deleted.
- S1 will evaluate only the four preregistered triples after S0 survivors, using a deterministic conjunction (`all component signals available`) and the same evaluator; S2 will replay only surviving combinations and write aggregate finalist rows with `trade_rows=0` for the development fixture.
- `run_fast_discovery.py` will inspect parquet schema with PyArrow, select an explicit allow-list, require `--dataset-root` and `--split-manifest`, reject non-UM/unexpected paths and any timestamp in `final_holdout_times`, and emit a nonzero exit on violations.
- Campaign output will add the six required compact manifests/reports and a SHA receipt; all paths and JSON key order are deterministic.
- Tests will construct both a non-empty synthetic OHLC frame and a holdout-intersection frame, run the CLI in a subprocess, compare output hashes from two runs, and assert cache hits and calendar-block counts.

These edits are the acceptance gate for B; no historical execution is permitted until C verifies them.

## Audit reconciliation (round 2)
The stale acceptance wording is superseded: the authoritative C gate is the executable build contract above. C must run non-empty synthetic S0/S1/S2, CLI subprocess, holdout rejection, calendar-block semantics, cache-hit accounting, and byte-identical rerun-hash checks. The earlier missing-OHLC/empty-output cases remain additional fail-closed activation tests, not the sole verifier.
