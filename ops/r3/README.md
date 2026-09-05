# R3 v8 operations layer

The files in this directory supervise the already sealed
`scientific_raw_v8` collector. They are deliberately outside `scripts/`,
`src/`, `tests/`, and `configs/`, so installing the operational service cannot
change the frozen scientific source-tree identity.

`launch_r3_v8_resume.ps1` is the only service entrypoint. It runs the
fail-closed `preflight` command before invoking the existing scientific
collector and uses the collector's PID lock as the sole writer lock.
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
it still invokes the same fail-closed launcher and existing collector lock.
