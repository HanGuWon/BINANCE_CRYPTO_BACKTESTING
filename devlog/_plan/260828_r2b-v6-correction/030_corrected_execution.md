# Corrected pre-holdout execution unit

Freeze the implementation identity after the runner/verifier/qualification
commits. Confirm registry SHA `3c61d923fe2cf88714c8cd2592264800ef2880db894dd2a21170fdf4fcc85302`
and all frozen protocol hashes are unchanged. Select an unused D-backed root
(never v6), execute every 72-trial × 8-fold unit once under the identity-pinned
runner, finalize the manifest, and run the enhanced verifier before any
aggregation. Acceptance requires 576 terminal units, no failures, and zero for
all execution, sign, availability, overlap, net-return, January, and holdout
violation counters.
