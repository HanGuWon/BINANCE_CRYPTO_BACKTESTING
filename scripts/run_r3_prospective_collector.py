"""One-shot/long-run public R3 collector; never evaluates outcomes."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _repo_path in (REPO_ROOT / "src", REPO_ROOT):
    _repo_path_text = str(_repo_path)
    if _repo_path_text in sys.path:
        sys.path.remove(_repo_path_text)
    sys.path.insert(0, _repo_path_text)

from binance_research.collector import AppendOnlyEventStore, ForwardCollector
from binance_research.r3_universe import replay_roster_artifact
from binance_research.r3_timing import calibrated_now, cycle_boundaries, next_quarter_hour
from binance_research.r3_operations import append_manifest, build_manifest, cycle_metadata, require_sha256, single_instance_lock, verify_launch_identity, verify_launch_seal, verify_manifest_chain, write_health_receipt, write_pilot_receipt

PILOT_SYMBOLS = ("BTCUSDT", "ETHUSDT")
PILOT_ROOT_NAME = "r3_prospective_context_v1"
SHADOW_WS_SECONDS = 5


def first_scheduled_boundary(local_now: datetime, calibration, *, interval_seconds: int = 900) -> tuple[datetime, datetime]:
    """Return the next absolute boundary and its frozen collection time."""
    boundary = next_quarter_hour(calibrated_now(local_now, calibration), interval_seconds=interval_seconds)
    return boundary, boundary + timedelta(seconds=5)


def clock_uncertainty_eligible(uncertainty_ms: float, *, threshold_ms: float = 2000.0) -> bool:
    return float(uncertainty_ms) <= float(threshold_ms)


def validate_pilot_inputs(root: Path, symbols: list[str]) -> None:
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:" or resolved.name != PILOT_ROOT_NAME:
        raise ValueError("pilot root must be D-backed .../r3_prospective_context_v1")
    if tuple(sorted(symbols)) != PILOT_SYMBOLS:
        raise ValueError("pilot symbols are fixed to BTCUSDT and ETHUSDT")


def _load_roster(roster_artifact: Path):
    payload = json.loads(Path(roster_artifact).read_text(encoding="utf-8"))
    month = payload.get("effective_month")
    if not isinstance(month, str) or len(month) != 7:
        raise ValueError("roster artifact must declare effective_month")
    return replay_roster_artifact(Path(roster_artifact), effective_month=month)


def validate_scientific_inputs(manifest_path: Path, *, roster_sha256: str, implementation_commit: str | None = None, launch_seal: Path | None = None, scientific_root: Path | None = None) -> dict[str, object]:
    """Require an unblocked launch manifest before any scientific collection."""
    manifest = verify_launch_identity(manifest_path, roster_sha256=roster_sha256, implementation_commit=implementation_commit)
    seal = Path(launch_seal) if launch_seal is not None else Path(manifest_path).with_name("R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json")
    verify_launch_seal(seal, Path(manifest_path), roster_sha256=roster_sha256, scientific_root=scientific_root)
    return manifest


def validate_engineering_shadow_inputs(root: Path, roster_artifact: Path, *, at_utc: datetime | None = None, require_fresh: bool = False) -> tuple[list[str], str]:
    """Load the August roster; manual symbol lists are not accepted."""
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:" or resolved.name in {"raw_v1", "scientific_raw_v1"}:
        raise ValueError("ENGINEERING_SHADOW requires a fresh D-backed non-scientific root")
    if require_fresh and resolved.exists() and any(resolved.iterdir()):
        raise ValueError("ENGINEERING_SHADOW root must be fresh and empty")
    roster = _load_roster(roster_artifact)
    now = (at_utc or datetime.now(UTC)).astimezone(UTC)
    if not (datetime.fromisoformat(roster.effective_start) <= now < datetime.fromisoformat(roster.effective_end)):
        raise ValueError("August roster is outside its engineering-shadow validity window")
    return list(roster.symbols), roster.roster_sha256


def run_engineering_shadow(root: Path, roster_artifact: Path, *, at_utc: datetime | None = None) -> dict[str, object]:
    symbols, roster_sha256 = validate_engineering_shadow_inputs(root, roster_artifact, at_utc=at_utc, require_fresh=True)
    context_only = set()
    if "BTCUSDT" not in symbols:
        symbols = [*symbols, "BTCUSDT"]
        context_only.add("BTCUSDT")
    return _run_cycle(Path(root), symbols, roster_sha256, evidence_mode="ENGINEERING_SHADOW", ws_seconds=SHADOW_WS_SECONDS, context_only_symbols=context_only)


def run_scientific(root: Path, roster_artifact: Path, launch_manifest: Path) -> dict[str, object]:
    """Run the same primary collector path, authorized only by a frozen launch manifest."""
    roster = _load_roster(roster_artifact)
    manifest = validate_scientific_inputs(launch_manifest, roster_sha256=roster.roster_sha256, scientific_root=root)
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:" or resolved.name in {"raw_v1", "scientific_raw_v1"}:
        raise ValueError("SCIENTIFIC requires a fresh D-backed scientific root")
    if resolved.exists() and any(resolved.iterdir()):
        _validate_authorized_resume(resolved, launch_manifest, roster.roster_sha256)
    if manifest.get("campaign_id") != "r3_prospective_context_v1":
        raise ValueError("launch manifest campaign mismatch")
    symbols = list(roster.symbols)
    context_only = set()
    if "BTCUSDT" not in symbols:
        symbols.append("BTCUSDT")
        context_only.add("BTCUSDT")
    with single_instance_lock(resolved / "control" / "collector.lock"):
        return _run_cycle(resolved, symbols, roster.roster_sha256, evidence_mode="SCIENTIFIC", ws_seconds=SHADOW_WS_SECONDS, context_only_symbols=context_only)


def _validate_authorized_resume(root: Path, launch_manifest: Path, roster_sha256: str) -> None:
    """Allow only a root produced by this exact sealed launch identity."""
    chain = root / "raw_v1" / "manifest_chain.jsonl"
    health = root / "health" / "health_receipts.jsonl"
    if not chain.is_file() or not verify_manifest_chain(chain) or not health.is_file():
        raise ValueError("SCIENTIFIC resume root is missing a valid manifest chain or health receipt")
    lines = [line for line in health.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest = json.loads(lines[-1])
    if latest.get("evidence_mode") != "SCIENTIFIC" or latest.get("roster_sha256") != roster_sha256:
        raise ValueError("SCIENTIFIC resume root has foreign evidence or roster identity")
    seal = Path(launch_manifest).with_name("R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json")
    verify_launch_seal(seal, Path(launch_manifest), roster_sha256=roster_sha256, scientific_root=root)
    AppendOnlyEventStore(root / "raw_v1").append("collector_status", "um", "ALL", {"status": "AUTHORIZED_RESUME", "manifest_sha256": latest.get("manifest_sha256")}, source_kind="collector_control", endpoint="/fapi/v1/time", continuity_state="RESTART_GAP", evidence_mode="SCIENTIFIC")


async def _shadow_rest_and_ws(collector: ForwardCollector, symbols: list[str], *, evidence_mode: str, ws_seconds: int = 5) -> dict[str, object]:
    """Run the roster REST snapshot while a forceOrder WS listener is alive."""
    def collect_rest() -> None:
        for symbol in symbols:
            collector.collect_engineering_shadow_snapshot(symbol, evidence_mode=evidence_mode)

    async def collect_ws() -> dict[str, object]:
        try:
            async for _ in collector.stream_liquidations("ALL", evidence_mode=evidence_mode):
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


def _run_cycle(root: Path, symbols: list[str], roster_sha256: str, *, evidence_mode: str | None = None, ws_seconds: int = SHADOW_WS_SECONDS, context_only_symbols: set[str] | None = None, include_ws: bool = True, boundary: datetime | None = None, collector: ForwardCollector | None = None, clock=None) -> dict[str, object]:
    cycle_started = datetime.now(UTC)
    roster_sha256 = require_sha256(roster_sha256, "roster_sha256")
    collector = collector or ForwardCollector(AppendOnlyEventStore(root / "raw_v1"))
    clock = clock or collector.client.calibrate_server_clock("um")
    collector.clock_calibration = clock
    clock_uncertainty_ms = clock.round_trip_ms / 2.0 + 1.0
    calibration_id = clock.calibration_id
    scientifically_eligible = clock_uncertainty_eligible(clock_uncertainty_ms)
    if clock_uncertainty_ms > 2000:
        collector.store.append(
            "clock_status", "um", "ALL",
            {"status": "CLOCK_UNCERTAINTY_GAP", "calibration_id": calibration_id, "offset_ms": clock.offset_ms, "round_trip_ms": clock.round_trip_ms, "uncertainty_ms": clock_uncertainty_ms},
            source_kind="collector_control", endpoint="/fapi/v1/time", continuity_state="CLOCK_UNCERTAINTY_GAP", evidence_mode=evidence_mode,
        )
    ws_result: dict[str, object] | None = None
    target_boundary = (boundary or next_quarter_hour(calibrated_now(cycle_started, clock))).astimezone(UTC)
    if scientifically_eligible and evidence_mode in {"ENGINEERING_SHADOW", "SCIENTIFIC"} and include_ws:
        ws_result = asyncio.run(_shadow_rest_and_ws(collector, symbols, evidence_mode=evidence_mode or "ENGINEERING_SHADOW", ws_seconds=ws_seconds))
        collector.store.append(
            "force_order_status", "um", "ALL", ws_result,
            source_kind="collector_control", endpoint="wss://fstream.binance.com/market/ws/!forceOrder@arr",
            continuity_state="SOURCE_TIME_UNAVAILABLE", evidence_mode=evidence_mode,
        )
    elif scientifically_eligible:
        for symbol in symbols:
            collector.collect_r3_um_snapshot(symbol, evidence_mode=evidence_mode)
    collector.store.append(
        "clock_calibration", "um", "ALL",
        {"calibration_id": calibration_id, "offset_ms": clock.offset_ms, "round_trip_ms": clock.round_trip_ms, "uncertainty_ms": clock.round_trip_ms / 2.0 + 1.0},
        source_kind="collector_control", endpoint="/fapi/v1/time", continuity_state="COMPLETE", evidence_mode=evidence_mode,
    )
    cycle_finished = datetime.now(UTC)
    collector.store.append(
        "cycle_metadata", "um", "ALL",
        cycle_metadata(
            cycle_id=f"cycle-{cycle_started.strftime('%Y%m%dT%H%M%S%fZ')}",
            target_bar_open=cycle_boundaries(target_boundary, actual_start=cycle_started, required_available=cycle_finished)["target_bar_open"], target_bar_close=cycle_boundaries(target_boundary, actual_start=cycle_started, required_available=cycle_finished)["target_bar_close"],
            scheduled_collection_time=cycle_boundaries(target_boundary, actual_start=cycle_started, required_available=cycle_finished)["scheduled_collection_time"], actual_collection_start=cycle_started.isoformat(),
            cycle_completed_at=cycle_finished.isoformat(), clock_calibration_id=calibration_id,
            eligible_next_execution_time=cycle_boundaries(target_boundary, actual_start=cycle_started, required_available=cycle_finished)["eligible_next_execution_time"],
        ), source_kind="collector_control", endpoint="/fapi/v1/time", continuity_state="COMPLETE", evidence_mode=evidence_mode,
    )
    previous = None
    chain = root / "raw_v1" / "manifest_chain.jsonl"
    if chain.exists() and chain.read_text(encoding="utf-8").strip():
        if not verify_manifest_chain(chain):
            raise RuntimeError(f"manifest chain failed verification: {chain}")
        previous = json.loads(chain.read_text(encoding="utf-8").splitlines()[-1])["manifest_sha256"]
    manifest = build_manifest(root / "raw_v1", previous_manifest_sha256=previous)
    append_manifest(root / "raw_v1", manifest)
    stream_state = {"symbols": symbols, "status": "CYCLE_COMPLETE" if scientifically_eligible else "CLOCK_UNCERTAINTY_GAP", "scientifically_eligible": scientifically_eligible, "calibration_id": calibration_id}
    if context_only_symbols:
        stream_state["context_only_symbols"] = sorted(context_only_symbols)
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


def run_scientific_forever(root: Path, roster_artifact: Path, launch_manifest: Path, *, max_cycles: int | None = None, interval_seconds: int = 900, stop_event: asyncio.Event | None = None) -> None:
    """Persistent scientific architecture with one WS worker and grid REST cycles.

    The function is intentionally not invoked by the CLI before launch gates
    authorize it.  ``max_cycles`` exists only for outcome-blind qualification.
    """
    roster = _load_roster(roster_artifact)
    manifest = validate_scientific_inputs(launch_manifest, roster_sha256=roster.roster_sha256, scientific_root=root)
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:":
        raise ValueError("SCIENTIFIC requires a D-backed root")
    if resolved.exists() and any(resolved.iterdir()):
        _validate_authorized_resume(resolved, launch_manifest, roster.roster_sha256)
    symbols = list(roster.symbols)
    context_only = set()
    if "BTCUSDT" not in symbols:
        symbols.append("BTCUSDT")
        context_only.add("BTCUSDT")

    async def _run() -> None:
        collector = ForwardCollector(AppendOnlyEventStore(resolved / "raw_v1"))
        calibration = collector.client.calibrate_server_clock("um")
        collector.clock_calibration = calibration
        ws_stop = asyncio.Event()
        async def ws_worker() -> None:
            try:
                async for _ in collector.stream_liquidations("ALL", evidence_mode="SCIENTIFIC"):
                    if ws_stop.is_set():
                        return
            except asyncio.CancelledError:
                return
        ws_task = asyncio.create_task(ws_worker())
        cycles = 0
        try:
            boundary, scheduled = first_scheduled_boundary(datetime.now(UTC), calibration, interval_seconds=interval_seconds)
            await asyncio.sleep(max(0.0, (scheduled - calibrated_now(datetime.now(UTC), calibration)).total_seconds()))
            while max_cycles is None or cycles < max_cycles:
                if stop_event is not None and stop_event.is_set():
                    break
                now = calibrated_now(datetime.now(UTC), calibration)
                if now >= datetime.fromisoformat(roster.effective_end).astimezone(UTC):
                    collector.store.append("collector_status", "um", "ALL", {"status": "UNIVERSE_ROLLOVER_GAP", "from_month": roster.effective_month, "observed_at": now.isoformat()}, source_kind="collector_control", endpoint="/fapi/v1/time", continuity_state="UNIVERSE_ROLLOVER_GAP", evidence_mode="SCIENTIFIC")
                    chain = resolved / "raw_v1" / "manifest_chain.jsonl"
                    previous = json.loads(chain.read_text(encoding="utf-8").splitlines()[-1])["manifest_sha256"] if chain.exists() and chain.read_text(encoding="utf-8").strip() else None
                    gap_manifest = build_manifest(resolved / "raw_v1", previous_manifest_sha256=previous)
                    append_manifest(resolved / "raw_v1", gap_manifest)
                    write_health_receipt(resolved, raw_root=resolved / "raw_v1", campaign_id="r3_prospective_context_v1", manifest_sha256=gap_manifest["manifest_sha256"], roster_sha256=roster.roster_sha256, stream_state={"status": "UNIVERSE_ROLLOVER_GAP"}, evidence_mode="SCIENTIFIC", gap_count=1)
                    break
                await asyncio.to_thread(_run_cycle, resolved, symbols, roster.roster_sha256, evidence_mode="SCIENTIFIC", context_only_symbols=context_only, include_ws=False, boundary=boundary)
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                boundary = next_quarter_hour(boundary, interval_seconds=interval_seconds)
                now = calibrated_now(datetime.now(UTC), calibration)
                await asyncio.sleep(max(0.0, (boundary.timestamp() + 5.0) - now.timestamp()))
        finally:
            ws_stop.set()
            ws_task.cancel()
            await asyncio.gather(ws_task, return_exceptions=True)
            (resolved / "health" / "shutdown_receipt.json").parent.mkdir(parents=True, exist_ok=True)
            (resolved / "health" / "shutdown_receipt.json").write_text(json.dumps({"evidence_mode": "SCIENTIFIC", "cycles": cycles, "status": "SHUTDOWN_FINALIZED", "launch_manifest": str(launch_manifest), "implementation_commit": manifest.get("implementation_commit")}, sort_keys=True) + "\n", encoding="utf-8")
    with single_instance_lock(resolved / "control" / "collector.lock"):
        asyncio.run(_run())


def run_engineering_shadow_forever(root: Path, roster_artifact: Path, *, max_cycles: int = 4, interval_seconds: int = 900, stop_event: asyncio.Event | None = None, wait_for_boundary: bool = True, initial_boundary: datetime | None = None) -> dict[str, object]:
    """Run the persistent August engineering architecture without outcomes."""
    symbols, roster_sha256 = validate_engineering_shadow_inputs(Path(root), roster_artifact, require_fresh=True)
    context_only = set()
    if "BTCUSDT" not in symbols:
        symbols = [*symbols, "BTCUSDT"]
        context_only.add("BTCUSDT")
    resolved = Path(root).resolve()

    async def _run() -> dict[str, object]:
        collector = ForwardCollector(AppendOnlyEventStore(resolved / "raw_v1"))
        calibration = collector.client.calibrate_server_clock("um")
        collector.clock_calibration = calibration
        boundary, scheduled = first_scheduled_boundary(datetime.now(UTC), calibration, interval_seconds=interval_seconds)
        if initial_boundary is not None:
            boundary = initial_boundary.astimezone(UTC)
            if boundary.minute % 15 or boundary.second or boundary.microsecond:
                raise ValueError("initial_boundary must be an absolute 15-minute boundary")
            scheduled = boundary + timedelta(seconds=5)
        ws_stop = asyncio.Event()
        async def ws_worker() -> None:
            try:
                async for _ in collector.stream_liquidations("ALL", evidence_mode="ENGINEERING_SHADOW"):
                    if ws_stop.is_set():
                        return
            except asyncio.CancelledError:
                return
        ws_task = asyncio.create_task(ws_worker())
        manifests: list[dict[str, object]] = []
        try:
            for _ in range(max_cycles):
                if wait_for_boundary:
                    now = calibrated_now(datetime.now(UTC), calibration)
                    await asyncio.sleep(max(0.0, (scheduled - now).total_seconds()))
                manifests.append(await asyncio.to_thread(_run_cycle, resolved, symbols, roster_sha256, evidence_mode="ENGINEERING_SHADOW", context_only_symbols=context_only, include_ws=False, boundary=boundary, collector=collector, clock=calibration))
                boundary = next_quarter_hour(boundary, interval_seconds=interval_seconds)
                scheduled = boundary + timedelta(seconds=5)
                if stop_event is not None and stop_event.is_set():
                    break
        finally:
            ws_stop.set(); ws_task.cancel(); await asyncio.gather(ws_task, return_exceptions=True)
            (resolved / "health" / "shutdown_receipt.json").parent.mkdir(parents=True, exist_ok=True)
            (resolved / "health" / "shutdown_receipt.json").write_text(json.dumps({"evidence_mode": "ENGINEERING_SHADOW", "cycles": len(manifests), "status": "SHUTDOWN_FINALIZED", "roster_sha256": roster_sha256}, sort_keys=True) + "\n", encoding="utf-8")
        return {"cycles": len(manifests), "manifests": manifests, "roster_sha256": roster_sha256, "evidence_mode": "ENGINEERING_SHADOW"}
    with single_instance_lock(resolved / "control" / "collector.lock"):
        return asyncio.run(_run())


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
    parser.add_argument("--persistent", action="store_true", help="run the authorized scientific path continuously")
    parser.add_argument("--interval-seconds", type=int, default=None)
    args = parser.parse_args()
    if args.mode == "SCIENTIFIC":
        if args.roster_artifact is None or args.launch_manifest is None or args.symbols or args.roster_sha256:
            parser.error("SCIENTIFIC requires --roster-artifact and --launch-manifest and rejects --symbols/--roster-sha256")
        if args.persistent:
            run_scientific_forever(args.root, args.roster_artifact, args.launch_manifest, interval_seconds=args.interval_seconds or 900)
        else:
            run_scientific(args.root, args.roster_artifact, args.launch_manifest)
        return 0
    if args.mode == "ENGINEERING_SHADOW" or args.roster_artifact is not None:
        if args.roster_artifact is None:
            parser.error("ENGINEERING_SHADOW requires --roster-artifact")
        if args.symbols:
            parser.error("--symbols cannot be combined with --roster-artifact")
        if args.launch_manifest is not None:
            validate_scientific_inputs(args.launch_manifest, roster_sha256=_load_roster(args.roster_artifact).roster_sha256)
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
