"""Compare two outcome-blind pytest qualification transcripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SUMMARY_RE = re.compile(r"^(?P<summary>.*\b(?:passed|failed|error|skipped).*)$")
DURATION_RE = re.compile(r"\s+in\s+[0-9.]+s\.?$")
PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s]+")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_tree_sha256() -> str:
    paths = subprocess.check_output(["git", "ls-files", "--", "src", "ops/r3", "tests", "scripts", "configs", "campaigns/r3_prospective_context_v1", "docs", "pyproject.toml"], cwd=REPO_ROOT, text=True).splitlines()
    digest = hashlib.sha256()
    for name in sorted(paths):
        path = REPO_ROOT / name
        digest.update(name.replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def normalize_transcript(text: str) -> str:
    kept: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = DURATION_RE.sub("", line)
        line = PATH_RE.sub("<PATH>", line)
        if SUMMARY_RE.match(line) or "short test summary" in line.lower() or line.startswith("SKIPPED"):
            kept.append(line)
    return "\n".join(kept)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run1", type=Path, required=True)
    parser.add_argument("--run2", type=Path, required=True)
    parser.add_argument("--meta1", type=Path)
    parser.add_argument("--meta2", type=Path)
    parser.add_argument("--verifiers1", type=Path)
    parser.add_argument("--verifiers2", type=Path)
    parser.add_argument("--report", type=Path, default=REPO_ROOT / "reports/SOL_AUDIT_WP3_PROVENANCE_RECONCILIATION.md")
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args(argv)
    first = normalize_transcript(args.run1.read_text(encoding="utf-8", errors="replace"))
    second = normalize_transcript(args.run2.read_text(encoding="utf-8", errors="replace"))
    meta1 = json.loads(args.meta1.read_text(encoding="utf-8")) if args.meta1 else {"exit_code": 0}
    meta2 = json.loads(args.meta2.read_text(encoding="utf-8")) if args.meta2 else {"exit_code": 0}
    verifier_hashes1 = sorted(_sha256(path) for path in args.verifiers1.glob("*.json")) if args.verifiers1 and args.verifiers1.exists() else []
    verifier_hashes2 = sorted(_sha256(path) for path in args.verifiers2.glob("*.json")) if args.verifiers2 and args.verifiers2.exists() else []
    result = {
        "run1_normalized": first,
        "run2_normalized": second,
        "normalized_equal": first == second,
        "exit_codes": [meta1.get("exit_code"), meta2.get("exit_code")],
        "verifier_output_sha256": [verifier_hashes1, verifier_hashes2],
        "verifier_outputs_equal": verifier_hashes1 == verifier_hashes2,
        "source_tree_sha256": source_tree_sha256(),
        "registry_sha256": _sha256(REPO_ROOT / "campaigns/r3_prospective_context_v1/trial_registry.csv"),
        "canonical_report_path": str(args.report.relative_to(REPO_ROOT)).replace("\\", "/") if args.report.is_relative_to(REPO_ROOT) else str(args.report),
        "canonical_report_sha256": _sha256(args.report),
        "status": "PASS" if first == second and meta1.get("exit_code") == 0 and meta2.get("exit_code") == 0 and verifier_hashes1 == verifier_hashes2 else "FAIL",
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "normalized_equal": result["normalized_equal"], "exit_codes": result["exit_codes"]}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
