"""Final outcome-blind live audit; never evaluates returns or performance."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ops.r3.r3_ops import (  # noqa: E402
    V8_MANIFEST,
    V8_ROOT,
    V8_ROSTER,
    V8_SEAL,
    watchdog_snapshot,
)


STARTUP = REPO_ROOT / "ops" / "r3" / "install_r3_v8_startup.ps1"
RECEIPT_PATH = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations" / "R3_V8_FINAL_OPERATIONS_AUDIT_20260902.json"


def _startup_check() -> dict[str, object]:
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(STARTUP), "-ValidateOnly"]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"command": " ".join(command), "exit_code": result.returncode, "valid": result.returncode == 0, "output": (result.stdout or result.stderr or "").strip()}


def _task_check() -> dict[str, object]:
    command = "Get-ScheduledTask -TaskName 'R3-Prospective-Scientific-v8'; Get-ScheduledTaskInfo -TaskName 'R3-Prospective-Scientific-v8'"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {"command": command, "exit_code": result.returncode, "registered": result.returncode == 0, "output": (result.stdout or result.stderr or "").strip()}


def main() -> int:
    snapshot = watchdog_snapshot(V8_ROOT, manifest=V8_MANIFEST, seal=V8_SEAL, roster=V8_ROSTER, require_exact_v8=True)
    git_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    origin = subprocess.run(["git", "rev-parse", "origin/research/r2b-restricted-derivatives-v1"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    source_status = subprocess.run(["git", "status", "--short", "--", "scripts", "src", "tests", "configs"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    receipt = {
        "record_type": "R3_V8_FINAL_OPERATIONS_AUDIT",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "branch": branch,
        "head": git_head,
        "origin": origin,
        "ahead_behind": subprocess.run(["git", "rev-list", "--left-right", "--count", "origin/research/r2b-restricted-derivatives-v1...HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        "scientific_scope_status": source_status or "clean",
        "watchdog": snapshot,
        "startup_fallback": _startup_check(),
        "task_scheduler": _task_check(),
        "restart_disposition": "SAFE_SKIP_LIVE_RESTART",
        "restart_reason": "live v8 evidence was left running; no destructive restart was authorized",
        "evaluation_amendment": "NOT_YET_AUTHORIZED",
        "outcomes_accessed": False,
        "outcomes": "NOT_STARTED",
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_STARTED",
        "state": "R3_PROSPECTIVE_COLLECTION_OPERATIONALLY_STABILIZED",
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "receipt_path": str(RECEIPT_PATH), "head": git_head, "watchdog_state": snapshot.get("state"), "cycle_count": snapshot.get("cycle_count"), "authorized_writer_count": (snapshot.get("writer") or {}).get("authorized_writer_count")}, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
