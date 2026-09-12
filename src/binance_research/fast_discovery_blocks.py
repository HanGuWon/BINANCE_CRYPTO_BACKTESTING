"""Calendar-block semantics for outcome-blind Fast Discovery screens."""
from __future__ import annotations

import pandas as pd


def calendar_block_ids(timestamps: pd.Series, *, block_days: int = 1) -> pd.Series:
    """Return synchronized UTC calendar-block labels; gaps do not get bridged."""
    if block_days < 1:
        raise ValueError("block_days must be positive")
    values = pd.to_datetime(timestamps, utc=True, errors="raise")
    if values.isna().any():
        raise ValueError("timestamps cannot contain NaT")
    return values.dt.floor(f"{int(block_days)}D")


def independent_calendar_block_count(timestamps: pd.Series, *, block_days: int = 1) -> int:
    """Count observed calendar blocks, not rows or synthetic fold identifiers."""
    return int(calendar_block_ids(timestamps, block_days=block_days).nunique())


def require_independent_calendar_blocks(timestamps: pd.Series, *, minimum_blocks: int = 2, block_days: int = 1) -> None:
    """Fail closed when a screen lacks the preregistered number of blocks."""
    if minimum_blocks < 1:
        raise ValueError("minimum_blocks must be positive")
    observed = independent_calendar_block_count(timestamps, block_days=block_days)
    if observed < minimum_blocks:
        raise ValueError(f"need at least {minimum_blocks} independent calendar blocks; observed {observed}")
