"""Create hash-pinned attestations for completed Fast Discovery development screens."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity(root: Path) -> dict[str, object]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1", "--untracked-files=all", "--", "src", "scripts", "tests", "configs"], cwd=root, text=True)
    digest = hashlib.sha256()
    for path in sorted((root / "src" / "binance_research").rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return {"implementation_commit": commit, "source_tree_sha256": digest.hexdigest(), "scientific_source_clean": not bool(status.strip())}


def attest(root: Path, repo: Path) -> dict[str, object]:
    identity = source_identity(repo)
    receipt = root / "DEVELOPMENT_SCREEN_RECEIPT.json"
    results = root / "S0_DEVELOPMENT_RESULTS.csv"
    rejections = root / "S0_DEVELOPMENT_REJECTIONS.csv"
    if not all(path.is_file() for path in (receipt, results, rejections)):
        raise FileNotFoundError(f"incomplete screen root: {root}")
    data = json.loads(receipt.read_text(encoding="utf-8"))
    if data.get("final_holdout") != "UNTOUCHED" or data.get("trade_rows") != 0:
        raise ValueError(f"screen root violates holdout/trade firewall: {root}")
    result_rows = results.read_text(encoding="utf-8").splitlines()
    rejection_rows = rejections.read_text(encoding="utf-8").splitlines()
    return {
        "protocol": "FAST_DISCOVERY_V2",
        "screen_root": str(root),
        **identity,
        "receipt_sha256": sha256_file(receipt),
        "results_sha256": sha256_file(results),
        "rejections_sha256": sha256_file(rejections),
        "rows": int(data["rows"]),
        "excluded_non_top50_rows": int(data["excluded_non_top50_rows"]),
        "result_rows": max(0, len(result_rows) - 1),
        "rejection_rows": max(0, len(rejection_rows) - 1),
        "trade_rows": 0,
        "scope": "DEVELOPMENT_ONLY",
        "final_holdout": "UNTOUCHED",
        "r3_outcomes": "NOT_ACCESSED",
        "historical_r2b_outcomes": "NOT_RUN",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    for root in args.roots:
        payload = attest((repo / root).resolve() if not root.is_absolute() else root.resolve(), repo)
        path = Path(payload["screen_root"]) / "DEVELOPMENT_SCREEN_ATTESTATION.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

