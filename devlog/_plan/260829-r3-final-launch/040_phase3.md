# R3 p3 — verified orchestration and segmented evidence

The operations layer now supports fail-closed launch identity checks (blocked
or engineering-only manifests cannot authorize scientific collection), stale
PID lock recovery without deleting live/malformed locks, and fsync'd isolated
segment manifests. The existing append-only chain remains intact. The runner
accepts a launch manifest gate when scientific mode is requested; the blocked
canonical manifest therefore prevents accidental activation.

No live or historical collection is run in this phase. Full Top50 shadow is
not authorized while the September roster provenance blocker remains open.
