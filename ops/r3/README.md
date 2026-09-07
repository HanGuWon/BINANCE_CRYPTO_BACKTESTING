# R3 v8 operations layer

The files in this directory supervise the already sealed
`scientific_raw_v8` collector. They are deliberately outside `scripts/`,
`src/`, `tests/`, and `configs/`, so installing the operational service cannot
change the frozen scientific source-tree identity.

`run_r3_v8_guardian.ps1` is the sole service/supervisor entrypoint. It polls
the exact sealed-v8 identity and writer metadata, records immutable
outcome-blind attempts, and invokes `launch_r3_v8_resume.ps1` only after the
canonical standing recovery policy has authorized a fresh preflight and a
single-use child authorization. The child binds the verified policy hash,
v8 identity, and immutable preflight receipt; parent mismatch, replay, expiry,
or a forged issuer fail closed. The underlying launcher runs the fail-closed
`preflight` command before invoking the existing scientific collector and uses
the collector's PID lock as the sole writer lock. A healthy live writer is
always a no-action state. Persistent polling re-enters after a child exits and
throttles unchanged state receipts, while preserving every distinct state
transition as an immutable attempt. The standing policy is valid only for the
existing sealed v8 root and never authorizes ForceOrder migration, outcomes, or
holdout access.
`watch_r3_v8.ps1` and `r3_ops.py watch` are read-only: they inspect only
operational metadata and classify liveness as GREEN, YELLOW, or RED.
`write_r3_daily_receipt.ps1` appends a one-record-per-UTC-day receipt under the
campaign operations directory with a separate lock. Duplicate dates are
rejected and each record contains `outcomes_accessed: false`.

The Task Scheduler XML is a sanitized template. It intentionally contains no
user SID, password, credential, or security descriptor. Registration belongs
to the phase-3 script and must use `MultipleInstancesPolicy=IgnoreNew`.

If the local token cannot register a scheduled task, the phase-3 installer can
use the native per-user Startup shortcut as a credential-free logon fallback;
it invokes the one guardian wrapper, which in turn uses the same fail-closed
launcher and existing collector lock. The guardian's strict lock is separate
from the collector lock and stale/malformed guardian locks are never removed
automatically.
