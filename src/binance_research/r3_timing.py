"""Server-clock calibration and absolute quarter-hour scheduling primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class ClockCalibration:
    """A midpoint-calibrated Binance server clock sample."""

    local_before_ms: int
    local_after_ms: int
    server_ms: int
    offset_ms: float
    round_trip_ms: int


def calibrate_server_clock(*, local_before_ms: int, server_ms: int, local_after_ms: int) -> ClockCalibration:
    if local_after_ms < local_before_ms:
        raise ValueError("local clock samples must be monotonic")
    midpoint = (local_before_ms + local_after_ms) / 2.0
    return ClockCalibration(
        local_before_ms=local_before_ms,
        local_after_ms=local_after_ms,
        server_ms=server_ms,
        offset_ms=server_ms - midpoint,
        round_trip_ms=local_after_ms - local_before_ms,
    )


def next_quarter_hour(now: datetime, *, interval_seconds: int = 900) -> datetime:
    """Return the next UTC boundary from an absolute epoch grid.

    The result does not depend on work duration or the previous request's end
    time, preventing drift across repeated REST cycles.
    """
    if interval_seconds <= 0 or 3600 % interval_seconds:
        raise ValueError("interval_seconds must be a positive divisor of one hour")
    current = now.astimezone(UTC)
    epoch = current.timestamp()
    boundary = (int(epoch) // interval_seconds + 1) * interval_seconds
    return datetime.fromtimestamp(boundary, UTC)


def calibrated_now(local_now: datetime, calibration: ClockCalibration) -> datetime:
    """Apply the measured server offset to a local UTC timestamp."""
    return local_now.astimezone(UTC) + timedelta(milliseconds=calibration.offset_ms)
