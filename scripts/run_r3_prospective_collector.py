"""One-shot/long-run public R3 collector; never evaluates outcomes."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from binance_research.collector import AppendOnlyEventStore, ForwardCollector
from binance_research.r3_universe import replay_roster_artifact
from binance_research.r3_timing import calibrated_now, next_quarter_hour
from binance_research.r3_operations import append_manifest, build_manifest, require_sha256, single_instance_lock, verify_launch_identity, verify_manifest_chain, write_health_receipt, write_pilot_receipt

PILOT_SYMBOLS = ("BTCUSDT", "ETHUSDT")
PILOT_ROOT_NAME = "r3_prospective_context_v1"
SHADOW_WS_SECONDS = 5


def validate_pilot_inputs(root: Path, symbols: list[str]) -> None:
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:" or resolved.name != PILOT_ROOT_NAME:
        raise ValueError("pilot root must be D-backed .../r3_prospective_context_v1")
    if tuple(sorted(symbols)) != PILOT_SYMBOLS:
        raise ValueError("pilot symbols are fixed to BTCUSDT and ETHUSDT")


def validate_scientific_inputs(manifest_path: Path, *, roster_sha256: str, implementation_commit: str | None = None) -> dict[str, object]:
    """Require an unblocked launch manifest before any scientific collection."""
    return verify_launch_identity(manifest_path, roster_sha256=roster_sha256, implementation_commit=implementation_commit)


def validate_engineering_shadow_inputs(root: Path, roster_artifact: Path, *, at_utc: datetime | None = None, require_fresh: bool = False) -> tuple[list[str], str]:
    """Load the August roster; manual symbol lists are not accepted."""
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:" or resolved.name in {"raw_v1", "scientific_raw_v1"}:
        raise ValueError("ENGINEERING_SHADOW requires a fresh D-backed non-scientific root")
    if require_fresh and resolved.exists() and any(resolved.iterdir()):
        raise ValueError("ENGINEERING_SHADOW root must be fresh and empty")
    roster = replay_roster_artifact(Path(roster_artifact), effective_month="2026-08")
    now = (at_utc or datetime.now(UTC)).astimezone(UTC)
    if not (datetime.fromisoformat(roster.effective_start) <= now < datetime.fromisoformat(roster.effective_end)):
        raise ValueError("August roster is outside its engineering-shadow validity window")
    return list(roster.symbols), roster.roster_sha256


def run_engineering_shadow(root: Path, roster_artifact: Path, *, at_utc: datetime | None = None) -> dict[str, object]:
    symbols, roster_sha256 = validate_engineering_shadow_inputs(root, roster_artifact, at_utc=at_utc, require_fresh=True)
    return _run_cycle(Path(root), symbols, roster_sha256, evidence_mode="ENGINEERING_SHADOW", ws_seconds=SHADOW_WS_SECONDS)


def run_scientific(root: Path, roster_artifact: Path, launch_manifest: Path) -> dict[str, object]:
    """Run the same primary collector path, authorized only by a frozen launch manifest."""
    roster = replay_roster_artifact(Path(roster_artifact), effective_month="2026-08")
    manifest = validate_scientific_inputs(launch_manifest, roster_sha256=roster.roster_sha256)
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:" or resolved.name in {"raw_v1", "scientific_raw_v1"}:
        raise ValueError("SCIENTIFIC requires a fresh D-backed scientific root")
    if manifest.get("campaign_id") != "r3_prospective_context_v1":
        raise ValueError("launch manifest campaign mismatch")
    with single_instance_lock(resolved / "control" / "collector.lock"):
        return _run_cycle(resolved, list(roster.symbols), roster.roster_sha256, evidence_mode="SCIENTIFIC", ws_seconds=SHADOW_WS_SECONDS)


async def _shadow_rest_and_ws(collector: ForwardCollector, symbols: list[str], *, ws_seconds: int = 5) -> dict[str, object]:
    """Run the roster REST snapshot while a forceOrder WS listener is alive."""
    def collect_rest() -> None:
        for symbol in symbols:
            collector.collect_engineering_shadow_snapshot(symbol)

    async def collect_ws() -> dict[str, object]:
        try:
            async for _ in collector.stream_liquidations("ALL", evidence_mode="ENGINEERING_SHADOW"):
                return {"connected": True, "received": True, "event_policy": "persist_raw_only"}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return {"connected": False, "received": False, "error": type(exc).__name__}
        return {"connected": False, "received": False, "error": "stream_ended"}

    ws_task = asyncio.create_task(collect_ws())
    rest_task = asyncio.create_task(asyncio.to_thread(collect_rest))
    await rest_task
    try:
        ws_result = await asyncio.wait_for(ws_task, timeout=max(1, ws_seconds))
    except asyncio.TimeoutError:
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass
        ws_result = {"connected": True, "received": False, "timeout_seconds": max(1, ws_seconds), "event_policy": "persist_raw_only"}
    except Exception as exc:
        ws_result = {"connected": False, "received": False, "error": type(exc).__name__}
    return ws_result


def _run_cycle(root: Path, symbols: list[str], roster_sha256: str, *, evidence_mode: str | None = None, ws_seconds: int = SHADOW_WS_SECONDS) -> dict[str, object]:
    roster_sha256 = require_sha256(roster_sha256, "roster_sha256")
    collector = ForwardCollector(AppendOnlyEventStore(root / "raw_v1"))
    clock = collector.client.calibrate_server_clock("um")
    collector.clock_calibration = clock
    ws_result: dict[str, object] | None = None
    if evidence_mode in {"ENGINEERING_SHADOW", "SCIENTIFIC"}:
        ws_result = asyncio.run(_shadow_rest_and_ws(collector, symbols, ws_seconds=ws_seconds))
        collector.store.append(
            "force_order_status", "um", "ALL", ws_result,
            source_kind="collector_control", endpoint="wss://fstream.binance.com/market/ws/!forceOrder@arr",
            continuity_state="SOURCE_TIME_UNAVAILABLE", evidence_mode=evidence_mode,
        )
    else:
        for symbol in symbols:
            collector.collect_r3_um_snapshot(symbol)
    collector.store.append(
        "clock_calibration", "um", "ALL",
        {"calibration_id": f"cal-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}", "offset_ms": clock.offset_ms, "round_trip_ms": clock.round_trip_ms, "uncertainty_ms": clock.round_trip_ms / 2.0 + 1.0},
        source_kind="collector_control", endpoint="/fapi/v1/time", continuity_state="COMPLETE", evidence_mode=evidence_mode,
    )
    previous = None
    chain = root / "raw_v1" / "manifest_chain.jsonl"
    if chain.exists() and chain.read_text(encoding="utf-8").strip():
        if not verify_manifest_chain(chain):
            raise RuntimeError(f"manifest chain failed verification: {chain}")
        previous = json.loads(chain.read_text(encoding="utf-8").splitlines()[-1])["manifest_sha256"]
    manifest = build_manifest(root / "raw_v1", previous_manifest_sha256=previous)
    append_manifest(root / "raw_v1", manifest)
    stream_state = {"symbols": symbols, "status": "CYCLE_COMPLETE"}
    if ws_result is not None:
        stream_state["force_order_ws"] = ws_result
    gap_states = {"POLL_GAP", "RATE_LIMIT_GAP", "SEQUENCE_GAP", "RESTART_GAP"}
    gap_count = 0
    restart_count = 0
    for path in (root / "raw_v1").rglob("*.jsonl"):
        if path.name == "manifest_chain.jsonl":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                state = json.loads(line).get("continuity_state")
            except json.JSONDecodeError:
                continue
            gap_count += int(state in gap_states)
            restart_count += int(state == "RESTART_GAP")
    write_health_receipt(root, raw_root=root / "raw_v1", campaign_id="r3_prospective_context_v1", manifest_sha256=manifest["manifest_sha256"], roster_sha256=roster_sha256, stream_state=stream_state, restart_count=restart_count, gap_count=gap_count, evidence_mode=evidence_mode)
    return manifest


def run_once(root: Path, symbols: list[str], roster_sha256: str) -> dict[str, object]:
    root = Path(root)
    with single_instance_lock(root / "control" / "collector.lock"):
        return _run_cycle(root, symbols, roster_sha256)


def run_forever(root: Path, symbols: list[str], roster_sha256: str, *, interval_seconds: int = 900) -> None:
    """Run polling cycles on an absolute, calibrated UTC epoch grid."""
    if interval_seconds < 60 or 3600 % interval_seconds:
        raise ValueError("R3 polling interval must be a positive divisor of one hour")
    root = Path(root)
    with single_instance_lock(root / "control" / "collector.lock"):
        # Align the first cycle to the next absolute UTC grid as well as all
        # subsequent cycles; this prevents a launch-time phase offset.
        clock = ForwardCollector(AppendOnlyEventStore(root / "raw_v1")).client.calibrate_server_clock("um")
        server_now = calibrated_now(datetime.now(UTC), clock)
        boundary = next_quarter_hour(server_now, interval_seconds=interval_seconds)
        time.sleep(max(0.0, (boundary - server_now).total_seconds()))
        while True:
            _run_cycle(root, symbols, roster_sha256)
            clock = ForwardCollector(AppendOnlyEventStore(root / "raw_v1")).client.calibrate_server_clock("um")
            server_now = calibrated_now(datetime.now(UTC), clock)
            boundary = next_quarter_hour(server_now, interval_seconds=interval_seconds)
            time.sleep(max(0.0, (boundary - server_now).total_seconds()))


def run_pilot(root: Path, roster_sha256: str) -> dict[str, object]:
    symbols = list(PILOT_SYMBOLS)
    validate_pilot_inputs(root, symbols)
    manifest = run_once(root, symbols, roster_sha256)
    stream_counts = {str(item["path"]).split("/")[-1].removesuffix(".jsonl"): int(item["rows"]) for item in manifest["files"]}
    import asyncio
    try:
        from scripts.r3_liquidation_probe import probe
        liquidation_state = asyncio.run(probe(5))
    except Exception as exc:
        liquidation_state = {"connected": False, "received": False, "error": type(exc).__name__}
    projections = {period: int(manifest["total_bytes"] * factor) for period, factor in (("24h", 96), ("7d", 672), ("30d", 2880), ("90d", 8640))}
    write_pilot_receipt(Path(root), symbols=symbols, manifest_sha256=str(manifest["manifest_sha256"]), roster_sha256=roster_sha256, stream_counts=stream_counts, bytes_written=int(manifest["total_bytes"]), latency_seconds={}, gap_counts={}, storage_projection_bytes=projections, liquidation_state=liquidation_state)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--mode", choices=("ENGINEERING_PILOT", "ENGINEERING_SHADOW", "SCIENTIFIC"), default="ENGINEERING_PILOT")
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--roster-artifact", type=Path, default=None, help="Use the frozen roster (required for shadow/scientific mode)")
    parser.add_argument("--roster-sha256")
    parser.add_argument("--launch-manifest", type=Path, default=None)
    parser.add_argument("--interval-seconds", type=int, default=None)
    args = parser.parse_args()
    if args.mode == "SCIENTIFIC":
        if args.roster_artifact is None or args.launch_manifest is None or args.symbols or args.roster_sha256:
            parser.error("SCIENTIFIC requires --roster-artifact and --launch-manifest and rejects --symbols/--roster-sha256")
        run_scientific(args.root, args.roster_artifact, args.launch_manifest)
        return 0
    if args.mode == "ENGINEERING_SHADOW" or args.roster_artifact is not None:
        if args.roster_artifact is None:
            parser.error("ENGINEERING_SHADOW requires --roster-artifact")
        if args.symbols:
            parser.error("--symbols cannot be combined with --roster-artifact")
        if args.launch_manifest is not None:
            validate_scientific_inputs(args.launch_manifest, roster_sha256=replay_roster_artifact(args.roster_artifact, effective_month="2026-08").roster_sha256)
        if args.interval_seconds is not None:
            parser.error("roster-driven ENGINEERING_SHADOW is one-shot; do not use --interval-seconds")
        run_engineering_shadow(args.root, args.roster_artifact)
        return 0
    if not args.symbols or not args.roster_sha256:
        parser.error("--symbols is required for legacy engineering pilot mode; scientific/shadow mode requires --roster-artifact")
    symbols = [str(symbol).upper() for symbol in args.symbols]
    if args.launch_manifest is not None:
        validate_scientific_inputs(args.launch_manifest, roster_sha256=args.roster_sha256)
    if args.interval_seconds is None:
        run_once(args.root, symbols, args.roster_sha256)
    else:
        run_forever(args.root, symbols, args.roster_sha256, interval_seconds=args.interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
