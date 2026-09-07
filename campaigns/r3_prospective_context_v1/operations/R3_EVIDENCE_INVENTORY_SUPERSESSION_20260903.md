# R3 evidence-inventory supersession note

The first two uncommitted inventory attempts are preserved with explicit
suffixes rather than silently overwritten:

- `R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_20260903_INVALID.json` counted the
  control stream's `SOURCE_TIME_UNAVAILABLE` state as a gap. It failed its own
  output firewall and is not canonical.
- `R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_20260903_PRE_BOUNDARY_CHECK.json`
  excluded every normalized 15-minute row because it compared availability to
  the row's open time instead of the next absolute executable boundary. It is
  retained as a method-repair trace and is not canonical.
- `R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_20260903_INVALID_BOUNDARY.json` is the
  intermediate strict-boundary attempt retained before the corrected boundary
  interpretation.

The 92-cycle canonical snapshot remains
`R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_20260903.json` for provenance. The final
fresh snapshot is
`R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_20260903_FINAL.json`; it supersedes the
earlier snapshot only by timestamped path and does not alter its bytes. Both
exclude control-only source-time absence from stream-gap counts, use the first
grid boundary after recorded availability, include the authoritative health
gap/restart counters, and contain only timestamps, symbols, schema presence, continuity,
availability, event/input counts, and dependence summaries. No payload values,
forward labels, returns, PnL, rankings, or confirmatory material are retained.
