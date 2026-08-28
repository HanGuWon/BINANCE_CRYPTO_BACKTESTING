"""Immutable prospective UM roster and month-rollover state machine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

import pandas as pd


class UniverseContractError(ValueError):
    pass


@dataclass(frozen=True)
class Roster:
    effective_month: str
    market: str
    symbols: tuple[str, ...]
    prior_ranking: tuple[dict[str, Any], ...]
    source_sha256: str
    effective_start: str
    effective_end: str
    roster_sha256: str


def _month_bounds(month: str) -> tuple[str, str]:
    period = pd.Period(month, freq="M")
    return period.start_time.tz_localize(UTC).isoformat(), (period + 1).start_time.tz_localize(UTC).isoformat()


def freeze_um_top50(ranking: Iterable[dict[str, Any]], *, effective_month: str, source_sha256: str) -> Roster:
    rows = [dict(row) for row in ranking]
    if not source_sha256 or len(source_sha256) != 64 or any(char not in "0123456789abcdefABCDEF" for char in source_sha256):
        raise UniverseContractError("source SHA256 is required")
    frame = pd.DataFrame(rows)
    required = {"market", "symbol"}
    if not required.issubset(frame.columns):
        raise UniverseContractError(f"roster ranking missing columns: {sorted(required - set(frame.columns))}")
    frame["market"] = frame["market"].astype(str).str.lower()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    if not frame["market"].eq("um").all():
        raise UniverseContractError("R3 roster is USD-M only")
    selected = frame[frame.get("selected_top50", frame.get("rank", 10**9) <= 50).astype(bool)].copy()
    symbols = tuple(sorted(set(selected["symbol"])))
    if len(symbols) != 50:
        raise UniverseContractError(f"expected exactly 50 unique UM symbols, got {len(symbols)}")
    start, end = _month_bounds(effective_month)
    evidence = tuple(sorted((row for row in rows if str(row.get("symbol", "")).upper() in symbols), key=lambda row: str(row.get("symbol"))))
    body = {"effective_month": effective_month, "market": "um", "symbols": symbols, "prior_ranking": evidence, "source_sha256": source_sha256, "effective_start": start, "effective_end": end}
    roster_sha = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return Roster(**body, roster_sha256=roster_sha)


class RolloverStateMachine:
    def __init__(self, roster: Roster) -> None:
        self.roster = roster
        self.state = "ACTIVE"
        self.receipts: list[dict[str, Any]] = []

    def rollover(self, *, effective_month: str, next_roster: Roster | None, observed_at: datetime | None = None) -> str:
        now = (observed_at or datetime.now(UTC)).isoformat()
        if next_roster is None:
            self.state = "UNIVERSE_ROLLOVER_GAP"
            self.receipts.append({"state": self.state, "from_month": self.roster.effective_month, "to_month": effective_month, "observed_at": now})
            return self.state
        if next_roster.market != "um" or next_roster.effective_month != effective_month:
            raise UniverseContractError("next roster does not match requested UM month")
        self.receipts.append({"state": "LEAVE", "month": self.roster.effective_month, "observed_at": now})
        self.roster = next_roster
        self.state = "ACTIVE"
        self.receipts.append({"state": "REENTER", "month": effective_month, "observed_at": now, "roster_sha256": next_roster.roster_sha256})
        return self.state
