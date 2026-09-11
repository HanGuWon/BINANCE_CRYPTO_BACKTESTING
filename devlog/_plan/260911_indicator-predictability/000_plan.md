# Indicator predictability campaign

## Objective

Add a reproducible, research-only predictability path for the existing 22 causal
features on USDT-margined futures. The path measures probability quality and
incremental information against explicit baselines at 15m, 1h, 4h, and 24h.

## Constraints

- Preserve the existing `run` command and all R3 sealed evidence.
- Do not read or modify final holdout material.
- Use only dependencies already present in the base package.
- Keep future labels, scaling, and model fitting strictly out of evaluation data.
- Treat observed up-rate as distinct from predicted direction accuracy.

## Work phases

1. Add pure prediction primitives and deterministic statistical metrics.
2. Add development/forward CLI commands and report artifacts.
3. Add focused regression tests and run the affected/full test suites.
