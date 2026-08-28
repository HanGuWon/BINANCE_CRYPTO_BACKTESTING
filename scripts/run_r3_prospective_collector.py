"""One-shot/long-run public R3 collector; never evaluates outcomes."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from binance_research.collector import AppendOnlyEventStore, ForwardCollector
from binance_research.r3_operations import append_manifest, build_manifest, require_sha256, single_instance_lock, verify_manifest_chain, write_health_receipt


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
    """Run deterministic polling cycles until a graceful keyboard stop."""
    if interval_seconds < 60:
        raise ValueError("R3 polling interval must be at least one minute")
    root = Path(root)
    with single_instance_lock(root / "control" / "collector.lock"):
        while True:
            _run_cycle(root, symbols, roster_sha256)
            time.sleep(interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--roster-sha256", required=True)
    parser.add_argument("--interval-seconds", type=int, default=None)
    args = parser.parse_args()
    symbols = [str(symbol).upper() for symbol in args.symbols]
    if args.interval_seconds is None:
        run_once(args.root, symbols, args.roster_sha256)
    else:
        run_forever(args.root, symbols, args.roster_sha256, interval_seconds=args.interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
