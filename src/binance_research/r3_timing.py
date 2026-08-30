"""Server-clock calibration and absolute quarter-hour scheduling primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

COLLECTION_DELAY_SECONDS = 5


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


def cycle_boundaries(boundary: datetime, *, actual_start: datetime | None = None, required_available: datetime | None = None, collection_delay_seconds: int = COLLECTION_DELAY_SECONDS) -> dict[str, str]:
    """Return causal 15-minute candle and next-open timing for one boundary."""
    close = boundary.astimezone(UTC).replace(second=0, microsecond=0)
    if close.minute % 15:
        raise ValueError("boundary must be on an absolute 15-minute grid")
    open_time = close - timedelta(minutes=15)
    scheduled = close + timedelta(seconds=collection_delay_seconds)
    start = (actual_start or scheduled).astimezone(UTC)
    available = (required_available or start).astimezone(UTC)
    next_open = next_quarter_hour(available - timedelta(microseconds=1))
    return {"target_bar_open": open_time.isoformat(), "target_bar_close": close.isoformat(), "scheduled_collection_time": scheduled.isoformat(), "actual_collection_start": start.isoformat(), "eligible_next_execution_time": next_open.isoformat()}
