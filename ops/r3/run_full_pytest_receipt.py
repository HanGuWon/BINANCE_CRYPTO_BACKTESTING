"""Run the repository test suite and record a compact, source-pinned receipt."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ops.r3.r3_ops import _source_tree_sha256  # noqa: E402


RECEIPT_PATH = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations" / "R3_V8_FULL_PYTEST_RECEIPT_20260902.json"


def main() -> int:
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    combined = (result.stdout or "") + (result.stderr or "")
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    summary = lines[-1] if lines else ""
    match = re.search(r"(?P<passed>\d+) passed", summary)
    receipt = {
        "record_type": "R3_V8_FULL_PYTEST_RECEIPT",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "command": f"{sys.executable} -m pytest -q",
        "exit_code": result.returncode,
        "summary": summary,
        "passed_count": int(match.group("passed")) if match else None,
        "implementation_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        "source_tree_sha256": _source_tree_sha256(),
        "scientific_scope_status": subprocess.run(["git", "status", "--short", "--", "scripts", "src", "tests", "configs"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip() or "clean",
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "outcomes": "NOT_STARTED",
        "r2b2": "NOT_STARTED",
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt_path": str(RECEIPT_PATH), "exit_code": result.returncode, "summary": summary, "passed_count": receipt["passed_count"]}, sort_keys=True))
    return result.returncode


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
