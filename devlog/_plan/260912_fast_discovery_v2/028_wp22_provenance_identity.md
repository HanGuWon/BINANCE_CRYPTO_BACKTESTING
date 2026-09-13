# WP22 — Computed provenance identities

Fast Discovery provenance manifests now compute, rather than trust constants: the implementation commit, a SHA-256 over the source module tree, scientific-source cleanliness for `src/tests/configs/campaigns`, the combination-registry hash, and the screening-policy hash. The data source hash remains separately recorded. If Git identity cannot be read, the manifest reports `UNKNOWN`/`IDENTITY_UNAVAILABLE` instead of claiming a clean identity.

Verification: provenance identity assertions and Fast Discovery tests passed (15 focused). No historical R2B/R3 outcomes or final-holdout observations were accessed.
