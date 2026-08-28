"""One-shot/long-run public R3 collector; never evaluates outcomes."""
from __future__ import annotations

import argparse
from pathlib import Path

from binance_research.collector import AppendOnlyEventStore, ForwardCollector
from binance_research.r3_operations import append_manifest, build_manifest, single_instance_lock, write_health_receipt


def run_once(root: Path, symbols: list[str]) -> dict[str, object]:
    root = Path(root)
    with single_instance_lock(root / "control" / "collector.lock"):
        collector = ForwardCollector(AppendOnlyEventStore(root / "raw_v1"))
        for symbol in symbols:
            collector.collect_r3_um_snapshot(symbol)
        previous = None
        chain = root / "raw_v1" / "manifest_chain.jsonl"
        if chain.exists() and chain.read_text(encoding="utf-8").strip():
            import json
            previous = json.loads(chain.read_text(encoding="utf-8").splitlines()[-1])["manifest_sha256"]
        manifest = build_manifest(root / "raw_v1", previous_manifest_sha256=previous)
        append_manifest(root / "raw_v1", manifest)
        write_health_receipt(root / "raw_v1", campaign_id="r3_prospective_context_v1", manifest_sha256=manifest["manifest_sha256"], roster_sha256=None, stream_state={"symbols": symbols, "status": "ONE_SHOT_COMPLETE"})
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--symbols", nargs="+", required=True)
    args = parser.parse_args()
    run_once(args.root, [str(symbol).upper() for symbol in args.symbols])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
