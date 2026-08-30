"""One-shot/long-run public R3 collector; never evaluates outcomes."""
from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path

from binance_research.collector import AppendOnlyEventStore, ForwardCollector
from binance_research.r3_timing import calibrated_now, next_quarter_hour
from binance_research.r3_operations import append_manifest, build_manifest, require_sha256, single_instance_lock, verify_launch_identity, verify_manifest_chain, write_health_receipt, write_pilot_receipt

PILOT_SYMBOLS = ("BTCUSDT", "ETHUSDT")
PILOT_ROOT_NAME = "r3_prospective_context_v1"


def validate_pilot_inputs(root: Path, symbols: list[str]) -> None:
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:" or resolved.name != PILOT_ROOT_NAME:
        raise ValueError("pilot root must be D-backed .../r3_prospective_context_v1")
    if tuple(sorted(symbols)) != PILOT_SYMBOLS:
        raise ValueError("pilot symbols are fixed to BTCUSDT and ETHUSDT")


def validate_scientific_inputs(manifest_path: Path, *, roster_sha256: str, implementation_commit: str | None = None) -> dict[str, object]:
    """Require an unblocked launch manifest before any scientific collection."""
    return verify_launch_identity(manifest_path, roster_sha256=roster_sha256, implementation_commit=implementation_commit)


def _run_cycle(root: Path, symbols: list[str], roster_sha256: str) -> dict[str, object]:
    roster_sha256 = require_sha256(roster_sha256, "roster_sha256")
    collector = ForwardCollector(AppendOnlyEventStore(root / "raw_v1"))
    for symbol in symbols:
        collector.collect_r3_um_snapshot(symbol)
    previous = None
    chain = root / "raw_v1" / "manifest_chain.jsonl"
    if chain.exists() and chain.read_text(encoding="utf-8").strip():
        import json
        if not verify_manifest_chain(chain):
            raise RuntimeError(f"manifest chain failed verification: {chain}")
        previous = json.loads(chain.read_text(encoding="utf-8").splitlines()[-1])["manifest_sha256"]
    manifest = build_manifest(root / "raw_v1", previous_manifest_sha256=previous)
    append_manifest(root / "raw_v1", manifest)
    write_health_receipt(root, raw_root=root / "raw_v1", campaign_id="r3_prospective_context_v1", manifest_sha256=manifest["manifest_sha256"], roster_sha256=roster_sha256, stream_state={"symbols": symbols, "status": "CYCLE_COMPLETE"})
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
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--roster-sha256", required=True)
    parser.add_argument("--launch-manifest", type=Path, default=None)
    parser.add_argument("--interval-seconds", type=int, default=None)
    args = parser.parse_args()
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
