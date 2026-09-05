# R3 production-v2 expected-set erratum

Date: 2026-09-01 KST

Production-v2 remains immutable and blocked. Its first failure was during
`AUGUST_SOURCE_ACQUISITION`: the executor treated every historically observed
UM perpetual as an August-2026 download requirement. That conflated historical
taxonomy with month-scoped source availability and caused a 404 on
`1000BTTCUSDT`, which has historical 2022 archive evidence but no current
August-2026 public object.

The repaired contract must discover actual August 2026 UM 1d objects first,
classify symbols with no object or partial coverage as eligibility states, and
reserve campaign-wide blocking for an authoritative discovered object whose
retrieval, checksum, archive, or content integrity fails. The existing frozen
ranking formula and complete-prior-month requirement remain unchanged.

Evidence preserved without rewrite:

- v2 temporal gate SHA256:
  `778e0a4c797d399638316f349dc2a8cae6d7ad0e6108ebaf9901b1b10b32ee71`
- v2 partial root: `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v2`
- v2 file count at audit: `4`
- v1 temporal SHA256 unchanged:
  `5bb38de8c19175784e8e8a8561ca233b3951338962a245e039d9acc4199f0e6b`
- downstream ranking, roster, scientific collection, and outcomes: `NOT_STARTED`

This erratum supersedes neither the original blocker receipt nor the v2
partial artifacts. Production-v2 must not be resumed; any execution after the
repair uses a new production-v3 root and implementation identity.
