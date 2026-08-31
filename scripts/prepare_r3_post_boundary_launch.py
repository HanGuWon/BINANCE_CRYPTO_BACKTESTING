"""Time-gated preparation for the post-August R3 launch workflow.

This module only prepares a fail-closed plan before the September boundary. It
does not acquire August data, build a September ranking/roster, or activate a
scientific collector.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

BOUNDARY_UTC = datetime(2026, 9, 1, tzinfo=UTC)
SCIENTIFIC_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v1")


class PostBoundaryBlocked(RuntimeError):
    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")

    def __str__(self) -> str:
        return f"{self.code}: {self.reason}"


def require_boundary(now: datetime) -> None:
    """Reject all post-boundary actions until Binance-calibrated time is valid."""
    current = now.astimezone(UTC)
    if current < BOUNDARY_UTC:
        raise PostBoundaryBlocked(
            "R3_BLOCKED_SEPTEMBER_ROSTER",
            f"August source is not complete before {BOUNDARY_UTC.isoformat()}",
        )


def require_fresh_scientific_root(root: Path = SCIENTIFIC_ROOT) -> Path:
    """Require a D-backed empty root with no inherited engineering lineage."""
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:":
        raise PostBoundaryBlocked("R3_BLOCKED_STORAGE", "scientific root must be D-backed")
    if resolved.exists() and any(resolved.iterdir()):
        raise PostBoundaryBlocked(
            "R3_BLOCKED_LAUNCH_IDENTITY",
            "scientific root is not fresh; engineering evidence cannot be reused",
        )
    return resolved


def prepare_post_boundary_plan(*, now: datetime, scientific_root: Path = SCIENTIFIC_ROOT) -> dict[str, object]:
    """Return the immutable post-boundary sequence without executing it."""
    require_boundary(now)
    root = require_fresh_scientific_root(scientific_root)
    return {
        "status": "POST_BOUNDARY_PLAN_ONLY",
        "boundary_utc": BOUNDARY_UTC.isoformat().replace("+00:00", "Z"),
        "scientific_root": str(root),
        "steps": [
            "verify_binance_calibrated_time",
            "verify_completed_august_um_1d_source_and_checksums",
            "build_september_liquidity_ranking",
            "freeze_and_replay_roster_2026-09",
            "run_september_engineering_shadow_qualification",
            "verify_clock_ws_manifest_storage_gates",
            "create_new_launch_manifest_and_seal",
            "activate_fresh_scientific_root",
            "start_scientific_collector",
        ],
        "execute": False,
        "outcomes": "NOT_STARTED",
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_STARTED",
    }


if __name__ == "__main__":
    # The command is intentionally plan-only; callers must provide a calibrated
    # time and invoke each post-boundary gate explicitly after September opens.
    raise SystemExit("R3_BLOCKED_SEPTEMBER_ROSTER: plan-only module; no pre-boundary execution")
