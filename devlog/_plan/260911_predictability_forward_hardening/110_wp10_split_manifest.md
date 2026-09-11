# WP10 — Immutable split manifest
NEW development/final-holdout manifest and verifier; MODIFY CLI guards and tests.
Bind rows/times/cohorts to DEVELOPMENT or FINAL_HOLDOUT before result access; ordinary commands fail closed on intersection, independent of filename.
Activation: innocent filename containing a holdout row is rejected; override flags are unavailable.
