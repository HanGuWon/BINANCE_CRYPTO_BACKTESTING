# Phase 1 — production adapter wiring

Introduce explicit `control_root` and `scientific_root` configuration. Build a
production callback factory that delegates to existing qualified project
functions while keeping network/process actions behind adapters. Stage receipts
are immutable control evidence; the scientific root is checked only immediately
before activation.

Implementation note (commit `eaf7581`): the production factory now delegates
to canonical project adapters, while tests retain explicit fixture injection.
