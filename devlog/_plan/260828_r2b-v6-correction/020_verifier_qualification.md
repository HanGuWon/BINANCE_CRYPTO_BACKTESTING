# Verifier and qualification implementation unit

Scope: `scripts/verify_r2b_checkpoints.py`,
`scripts/r2b_realdata_qualification.py`, and regression tests.

The verifier will independently recompute exact timestamp-step execution,
horizon, sign, source-availability, overlap, net-return, January/holdout,
schema, trade-file hash, and source/registry/fold/causal identities, failing on
any nonzero count. Funding coverage must distinguish an empty event interval
from an unavailable/corrupt archive and fail closed in the latter case.

Qualification must compare optimized and slow reference execution on synthetic
membership/original-segment/price-gap fixtures and real UM 15m/1h/4h,
LONG/SHORT, both features/variants, all registered horizons, actual positive
and negative funding, no event, and next-open/gap boundaries. Run twice and
require identical receipts; no historical outcome is used by this unit.
