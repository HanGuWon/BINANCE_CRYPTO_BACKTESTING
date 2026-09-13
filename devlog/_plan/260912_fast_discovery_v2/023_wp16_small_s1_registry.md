# WP16 — Small fixed S1 registry

The S1 family is frozen at four theory-driven combinations, each with exactly three logical components and the role grammar `TRIGGER AND REGIME_FILTER AND PARTICIPATION`. The implementation enforces `S1_MAX_COMBINATIONS=4` and `S1_MAX_COMPONENTS=3` at registry construction; no Cartesian expansion or post-screening candidate addition is possible. The policy receipt records both caps. This phase is development-only and does not open historical R2B outcomes.

Verification is covered by `tests/test_fast_discovery_s1_roles.py` and the complete targeted Fast Discovery family. Existing structural screen artifacts remain immutable and are not reinterpreted.
