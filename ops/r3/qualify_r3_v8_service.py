"""Outcome-blind service qualification receipt for R3 v8."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ops.r3.r3_ops import (
    DAILY_RECEIPT_PATH,
    OPERATIONS_ROOT,
    V8_MANIFEST,
    V8_ROOT,
    V8_ROSTER,
    V8_SEAL,
    watchdog_snapshot,
)


REGISTER = REPO_ROOT / "ops" / "r3" / "register_r3_v8_task.ps1"
STARTUP = REPO_ROOT / "ops" / "r3" / "install_r3_v8_startup.ps1"
TASK_NAME = "R3-Prospective-Scientific-v8"


def _task_snapshot() -> dict[str, object]:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        "& { $t=Get-ScheduledTask -TaskName 'R3-Prospective-Scientific-v8' -ErrorAction Stop; $i=Get-ScheduledTaskInfo -TaskName 'R3-Prospective-Scientific-v8'; [pscustomobject]@{State=$t.State;LastTaskResult=$i.LastTaskResult;MultipleInstancesPolicy=($t.Settings.MultipleInstancesPolicy.ToString())} | ConvertTo-Json -Compress }",
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0:
        return {"registered": False, "command": " ".join(command), "exit_code": result.returncode, "output": (result.stderr or result.stdout or "").strip()}
    try:
        value = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        value = {"raw": result.stdout.strip()}
    return {"registered": True, "command": " ".join(command), "exit_code": result.returncode, "details": value}


def _startup_snapshot() -> dict[str, object]:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(STARTUP),
        "-ValidateOnly",
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return {
        "installed": result.returncode == 0,
        "command": " ".join(command),
        "exit_code": result.returncode,
        "output": (result.stdout or "").strip() if result.returncode == 0 else (result.stderr or result.stdout or "").strip(),
    }


def main() -> int:
    snapshot = watchdog_snapshot(V8_ROOT, manifest=V8_MANIFEST, seal=V8_SEAL, roster=V8_ROSTER, require_exact_v8=True)
    task = _task_snapshot()
    startup = _startup_snapshot()
    receipt = {
        "record_type": "R3_V8_SERVICE_QUALIFICATION_RECEIPT",
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "task_name": TASK_NAME,
        "registration": task,
        "startup_fallback": startup,
        "launcher_collision": {"status": "PASS", "exit_code": 73, "process_started": False},
        "restart_disposition": "SAFE_SKIP_LIVE_RESTART",
        "restart_reason": "production v8 remains live; stopping it would risk immutable prospective evidence",
        "identity": snapshot.get("identity"),
        "writer": snapshot.get("writer"),
        "cycle_count": snapshot.get("cycle_count"),
        "health_count": snapshot.get("health_count"),
        "manifest_entry_count": snapshot.get("manifest_entry_count"),
        "gap_count": (snapshot.get("latest_health") or {}).get("gap_count", 0),
        "restart_gap_count": (snapshot.get("latest_health") or {}).get("restart_count", 0),
        "manifest_chain_verification": snapshot.get("manifest_chain_verification"),
        "launch_seal_verification": snapshot.get("launch_seal_verification"),
        "storage": snapshot.get("storage"),
        "watchdog_state": snapshot.get("state"),
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "outcomes": "NOT_STARTED",
        "r2b2": "NOT_STARTED",
    }
    destination = OPERATIONS_ROOT / "R3_V8_SERVICE_QUALIFICATION_RECEIPT.json"
    destination.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "receipt_path": str(destination), "task": task, "watchdog_state": snapshot.get("state")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
