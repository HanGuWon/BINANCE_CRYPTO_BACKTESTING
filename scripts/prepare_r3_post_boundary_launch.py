"""Fail-closed, calibrated-time-gated R3 post-boundary launch executor."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

BOUNDARY_UTC = datetime(2026, 9, 1, tzinfo=UTC)
SCIENTIFIC_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v1")
MAX_CLOCK_UNCERTAINTY_MS = 2_000


class PostBoundaryBlocked(RuntimeError):
    def __init__(self, code: str, reason: str) -> None:
        self.code, self.reason = code, reason
        super().__init__(f"{code}: {reason}")

    def __str__(self) -> str:
        return f"{self.code}: {self.reason}"


@dataclass(frozen=True)
class CalibratedClock:
    """A Binance server-time sample with an explicit uncertainty bound."""

    server_time: datetime
    uncertainty_ms: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "server_time", self.server_time.astimezone(UTC))


StageCallback = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def require_calibrated_boundary(clock: CalibratedClock) -> None:
    if clock.uncertainty_ms > MAX_CLOCK_UNCERTAINTY_MS:
        raise PostBoundaryBlocked("R3_BLOCKED_CLOCK_CAUSALITY", f"Binance clock uncertainty {clock.uncertainty_ms:.3f}ms exceeds {MAX_CLOCK_UNCERTAINTY_MS}ms")
    if clock.server_time < BOUNDARY_UTC:
        raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_ROSTER", f"calibrated Binance time {clock.server_time.isoformat()} is before {BOUNDARY_UTC.isoformat()}")


def require_boundary(now: datetime) -> None:
    require_calibrated_boundary(CalibratedClock(now, 0.0))


def require_fresh_scientific_root(root: Path = SCIENTIFIC_ROOT) -> Path:
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:":
        raise PostBoundaryBlocked("R3_BLOCKED_STORAGE", "scientific root must be D-backed")
    if resolved.exists() and any(resolved.iterdir()):
        raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", "scientific root is not fresh; existing evidence cannot be reused")
    return resolved


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_stage_receipt(receipt_root: Path, stage: str, proof: Mapping[str, Any]) -> dict[str, Any]:
    receipt_root.mkdir(parents=True, exist_ok=True)
    path = receipt_root / f"{stage.lower()}.json"
    payload = {"stage": stage, "status": "PASS", "proof": dict(proof)}
    payload["proof_sha256"] = _digest(payload["proof"])
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PostBoundaryBlocked("R3_BLOCKED_IMPLEMENTATION", f"invalid {stage} receipt: {exc}") from exc
        if existing != payload:
            raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", f"conflicting {stage} receipt on replay")
        return existing
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _default_blocked(code: str, reason: str) -> StageCallback:
    def callback(_: Mapping[str, Any]) -> Mapping[str, Any]:
        raise PostBoundaryBlocked(code, reason)

    return callback


def _run_stage(stage: str, callback: StageCallback, context: Mapping[str, Any], receipt_root: Path) -> dict[str, Any]:
    try:
        proof = callback(context)
    except PostBoundaryBlocked:
        raise
    except Exception as exc:
        raise PostBoundaryBlocked("R3_BLOCKED_IMPLEMENTATION", f"{stage} callback failed: {exc}") from exc
    if not isinstance(proof, Mapping) or not proof:
        raise PostBoundaryBlocked("R3_BLOCKED_IMPLEMENTATION", f"{stage} returned no proof")
    return _write_stage_receipt(receipt_root, stage, proof)


def execute_post_boundary(*, clock: CalibratedClock, scientific_root: Path = SCIENTIFIC_ROOT, receipt_root: Path | None = None, callbacks: Mapping[str, StageCallback] | None = None) -> dict[str, Any]:
    """Run all launch stages after the calibrated boundary.

    The temporal gate is first, so pre-boundary calls create no files and invoke
    no callback. All external work is represented by proof-producing callbacks.
    """
    require_calibrated_boundary(clock)
    root = require_fresh_scientific_root(scientific_root)
    receipts = Path(receipt_root) if receipt_root is not None else root / "launch_receipts"
    defaults: dict[str, StageCallback] = {
        "AUGUST_SOURCE_ACQUISITION": _default_blocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source acquisition proof required"),
        "AUGUST_SOURCE_VERIFICATION": _default_blocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source verification proof required"),
        "SEPTEMBER_RANKING": _default_blocked("R3_BLOCKED_SEPTEMBER_RANKING", "September ranking proof required"),
        "SEPTEMBER_ROSTER_FREEZE": _default_blocked("R3_BLOCKED_SEPTEMBER_ROSTER", "September roster freeze proof required"),
        "SEPTEMBER_ROSTER_REPLAY": _default_blocked("R3_BLOCKED_SEPTEMBER_ROSTER", "September roster replay proof required"),
        "SEPTEMBER_ENGINEERING_SHADOW": _default_blocked("R3_BLOCKED_SEPTEMBER_SHADOW", "September shadow proof required"),
        "LAUNCH_IDENTITY_FREEZE": _default_blocked("R3_BLOCKED_LAUNCH_IDENTITY", "launch identity proof required"),
        "SCIENTIFIC_ROOT_GATE": lambda _: {"root": str(root), "fresh": True},
        "SCIENTIFIC_ACTIVATION": _default_blocked("R3_BLOCKED_LAUNCH_IDENTITY", "scientific activation proof required"),
    }
    defaults.update(dict(callbacks or {}))
    context: dict[str, Any] = {"clock": clock.server_time.isoformat(), "scientific_root": str(root)}
    out = [_write_stage_receipt(receipts, "TEMPORAL_GATE", {"server_time": clock.server_time.isoformat(), "uncertainty_ms": clock.uncertainty_ms})]
    for stage, callback in defaults.items():
        result = _run_stage(stage, callback, context, receipts)
        out.append(result)
        context[stage] = result["proof"]
    return {"status": "R3_READY_FOR_PROSPECTIVE_LAUNCH", "scientific_root": str(root), "receipts": out, "execute": True}


def rollover_state(*, now: datetime, september_end: datetime = datetime(2026, 10, 1, tzinfo=UTC), has_next_roster: bool) -> str:
    if now.astimezone(UTC) >= september_end.astimezone(UTC) and not has_next_roster:
        return "UNIVERSE_ROLLOVER_GAP"
    return "ACTIVE"


def prepare_post_boundary_plan(*, now: datetime, scientific_root: Path = SCIENTIFIC_ROOT) -> dict[str, object]:
    require_boundary(now)
    root = require_fresh_scientific_root(scientific_root)
    return {"status": "POST_BOUNDARY_EXECUTOR_READY", "boundary_utc": BOUNDARY_UTC.isoformat().replace("+00:00", "Z"), "scientific_root": str(root), "steps": ["TEMPORAL_GATE", "AUGUST_SOURCE_ACQUISITION", "AUGUST_SOURCE_VERIFICATION", "SEPTEMBER_RANKING", "build_september_liquidity_ranking", "SEPTEMBER_ROSTER_FREEZE", "SEPTEMBER_ROSTER_REPLAY", "SEPTEMBER_ENGINEERING_SHADOW", "LAUNCH_IDENTITY_FREEZE", "SCIENTIFIC_ROOT_GATE", "SCIENTIFIC_ACTIVATION"], "execute": False, "outcomes": "NOT_STARTED", "final_holdout": "UNTOUCHED", "r2b2": "NOT_STARTED"}


if __name__ == "__main__":
    raise SystemExit("R3_BLOCKED_SEPTEMBER_ROSTER: calibrated post-boundary invocation required")
