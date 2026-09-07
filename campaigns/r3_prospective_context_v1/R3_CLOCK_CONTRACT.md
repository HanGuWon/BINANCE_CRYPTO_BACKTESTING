# R3 collection clock contract (frozen pre-outcome)

At startup and before each scheduled cycle, the collector samples
`GET /fapi/v1/time` with monotonic and UTC send/receive timestamps. For each
sample it records RTT and the midpoint offset
`server_ms - (local_send_ms + local_receive_ms)/2`. The selected calibration is
the minimum-RTT sample among the retained sample set; ties use earliest sample
identity. The uncertainty bound is half RTT plus one millisecond. The estimate
and uncertainty are immutable for a cycle and are never performance-tuned.

Raw envelopes retain the original local receipt timestamp, calibration ID,
server offset, RTT, uncertainty, and corrected receipt time. Corrected time is
only a causal representation; the original timestamp is never rewritten. If
uncertainty exceeds 2 seconds, the cycle emits `CLOCK_UNCERTAINTY_GAP` and its
scientific observations are ineligible.
