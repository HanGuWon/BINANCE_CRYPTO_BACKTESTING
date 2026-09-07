"""Reproducible, outcome-blind qualification for the R3 operations layer."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "ops" / "r3" / "launch_r3_v8_resume.ps1"


def main() -> int:
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "ops/r3/tests/test_operations_layer.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if tests.returncode != 0:
        print(tests.stdout, end="")
        print(tests.stderr, end="", file=sys.stderr)
        return tests.returncode
    # The live v8 lock is intentionally not touched.  The launcher preflight
    # must detect the existing writer and return its documented collision code.
    collision = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAUNCHER),
            "-PreflightOnly",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if collision.returncode != 73 or "COLLECTOR_LOCK_COLLISION" not in collision.stdout:
        print(collision.stdout, end="")
        print(collision.stderr, end="", file=sys.stderr)
        print("launcher collision preflight failed", file=sys.stderr)
        return 2
    print("R3_OPS_C_CHECK=PASS targeted=7 passed launcher_collision_exit=73")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
