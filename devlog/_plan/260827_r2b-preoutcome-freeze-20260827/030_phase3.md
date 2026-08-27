# 030 — Phase 3: formal semantics and registry freeze

## MODIFY / NEW / DELETE map

- NEW `campaigns/r2b_restricted_derivatives_v1/R2B_SIGNAL_SEMANTICS_AMENDMENT_002.md`
  with exact strict-sign equations for raw premium and premium_zscore90, two
  named polarities, NaN/warmup/gap behavior, and LONG/SHORT execution gates.
- MODIFY `campaign_spec.toml`, `R2B_PROTOCOL.md`, `multiple_testing_plan.md`,
  `metrics_contract.md`, `promotion_policy.md`, and
  `reproducibility_manifest.json` to reference amendment 002 and the 72-row
  family while retaining the old blocked lineage.
- NEW `scripts/generate_r2b_registry.py`; COPY the old 36-row file to
  `trial_registry.blocked_v1_20260827.csv`; regenerate canonical
  `trial_registry.csv` deterministically with `signal_variant` and 72 rows.

## TESTS

- Registry generation and hash verification; count every hypothesis variant;
  expected SHA256 `3c61d923fe2cf88714c8cd2592264800ef2880db894dd2a21170fdf4fcc85302`
  and preserved old SHA256
  `8c302f31a54ccf783010f48a7e964c4ce6871ac8757965dde603b029f2ef0238`.

## Verification (C)

- Commit the semantics freeze before implementation qualification; otherwise
  document the blocked state and do not force a registry.
