"""Immutable prospective UM roster and month-rollover state machine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


class UniverseContractError(ValueError):
    pass


def _json_safe(value: Any) -> Any:
    """Normalize pandas NaN/NA values so roster identity is strict JSON."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is pd.NA:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


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
    rows = [_json_safe(dict(row)) for row in ranking]
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


def build_causal_monthly_roster(source: Path, *, effective_month: str) -> Roster:
    """Build a UM Top50 roster from a completed prior-month ranking artifact.

    The ranking artifact is treated as an immutable, content-addressed input.  A
    roster is rejected unless every selected row is UM, has a complete prior
    month, and its ``volume_month`` is exactly the month immediately preceding
    the roster's effective month.  This keeps month rollover causal and makes a
    replay from the same bytes deterministic.
    """
    source = Path(source)
    if not source.is_file():
        raise UniverseContractError(f"ranking source does not exist: {source}")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    frame = pd.read_csv(source)
    required = {"market", "symbol", "volume_month", "universe_month", "coverage_ratio", "eligibility_reason", "selected_top50"}
    missing = required - set(frame.columns)
    if missing:
        raise UniverseContractError(f"ranking source missing columns: {sorted(missing)}")
    prior_month = str(pd.Period(effective_month, freq="M") - 1)
    selected = frame[
        (frame["market"].astype(str).str.lower() == "um")
        & (frame["universe_month"].astype(str) == str(effective_month))
        & frame["selected_top50"].astype(str).str.lower().isin({"true", "1"})
    ].copy()
    if selected.empty:
        raise UniverseContractError(f"no selected UM Top50 rows for {effective_month}")
    if not selected["volume_month"].astype(str).eq(prior_month).all():
        raise UniverseContractError("roster includes a row whose ranking month is not the completed prior month")
    if not selected["eligibility_reason"].astype(str).eq("ELIGIBLE_COMPLETE_PRIOR_MONTH").all():
        raise UniverseContractError("roster includes a non-complete prior-month row")
    if not pd.to_numeric(selected["coverage_ratio"], errors="coerce").eq(1.0).all():
        raise UniverseContractError("roster includes a row with incomplete prior-month coverage")
    return freeze_um_top50(selected.to_dict(orient="records"), effective_month=effective_month, source_sha256=source_sha256)


def write_roster_artifact(roster: Roster, destination: Path, *, source_path: Path) -> Path:
    """Write a canonical JSON roster and return its path."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "r3_roster_v1",
        "source_path": str(Path(source_path).as_posix()),
        "effective_month": roster.effective_month,
        "market": roster.market,
        "symbols": list(roster.symbols),
        "prior_ranking": _json_safe(list(roster.prior_ranking)),
        "source_sha256": roster.source_sha256,
        "effective_start": roster.effective_start,
        "effective_end": roster.effective_end,
        "roster_sha256": roster.roster_sha256,
    }
    destination.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return destination


def replay_roster_artifact(source: Path, *, effective_month: str) -> Roster:
    """Replay a canonical roster artifact, rejecting tampered identity fields."""
    payload = json.loads(Path(source).read_text(encoding="utf-8"))
    required = {"schema", "effective_month", "market", "symbols", "prior_ranking", "source_sha256", "effective_start", "effective_end", "roster_sha256"}
    if payload.get("schema") != "r3_roster_v1" or not required.issubset(payload):
        raise UniverseContractError("invalid R3 roster artifact schema")
    if payload["effective_month"] != effective_month or payload["market"] != "um":
        raise UniverseContractError("roster artifact does not match requested UM month")
    roster = freeze_um_top50(payload["prior_ranking"], effective_month=effective_month, source_sha256=payload["source_sha256"])
    if tuple(payload["symbols"]) != roster.symbols or payload["roster_sha256"] != roster.roster_sha256:
        raise UniverseContractError("roster artifact identity does not replay")
    return roster


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
