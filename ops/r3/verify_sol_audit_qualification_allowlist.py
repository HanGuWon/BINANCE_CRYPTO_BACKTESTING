"""Outcome-blind collection and static/import guard for the SOL audit suite."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOTS = (REPO_ROOT / "tests", REPO_ROOT / "ops/r3/tests")
NODEID_RE = re.compile(r"^(?:tests|ops/r3/tests)[/\\].+::")
FORBIDDEN_PATH_TOKENS = ("scientific_raw_v8", "r2a2/checkpoints", "r2a2\\checkpoints")
FORBIDDEN_IMPORTS = {"scripts.verify_r2a2_checkpoints", "scripts.run_r2a2_outcomes"}
FORBIDDEN_CALLS = {"read_feather", "read_pickle"}
PERSISTED_READ_CALLS = {"open", "read_csv", "read_parquet", "read_feather", "read_pickle", "read_bytes", "read_text"}


def _module_path(nodeid: str) -> Path:
    return REPO_ROOT / nodeid.split("::", 1)[0].replace("/", "\\")


def _ancestor_map(tree: ast.AST) -> dict[ast.AST, tuple[ast.AST, ...]]:
    parents: dict[ast.AST, tuple[ast.AST, ...]] = {}

    def visit(node: ast.AST, stack: tuple[ast.AST, ...]) -> None:
        parents[node] = stack
        for child in ast.iter_child_nodes(node):
            visit(child, stack + (node,))

    visit(tree, ())
    return parents


def _is_guard_assertion(node: ast.AST, parents: dict[ast.AST, tuple[ast.AST, ...]]) -> bool:
    for parent in parents.get(node, ()):
        if isinstance(parent, ast.Assert):
            return True
        if isinstance(parent, ast.Call):
            function = parent.func
            if isinstance(function, ast.Attribute) and function.attr == "raises":
                return True
    return False


def audit_module(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    parents = _ancestor_map(tree)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            module = node.module if isinstance(node, ast.ImportFrom) and node.module else ""
            if module in FORBIDDEN_IMPORTS or any(name in FORBIDDEN_IMPORTS for name in names):
                findings.append(f"line {node.lineno}: forbidden outcome import")
        if isinstance(node, ast.Call):
            function = node.func
            name = function.attr if isinstance(function, ast.Attribute) else function.id if isinstance(function, ast.Name) else ""
            if name in FORBIDDEN_CALLS:
                findings.append(f"line {node.lineno}: forbidden persisted reader {name}")
            if name in PERSISTED_READ_CALLS:
                literals = [child.value.lower().replace("\\", "/") for child in ast.walk(node) if isinstance(child, ast.Constant) and isinstance(child.value, str)]
                if any(any(token in value for token in FORBIDDEN_PATH_TOKENS) for value in literals):
                    findings.append(f"line {node.lineno}: persisted live/checkpoint path passed to {name}")
    return findings


def collect_nodeids() -> tuple[int, list[str], str]:
    command = [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests", "ops/r3/tests", "-p", "no:cacheprovider"]
    result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    nodeids = [line.strip() for line in result.stdout.splitlines() if NODEID_RE.match(line.strip())]
    return result.returncode, nodeids, result.stdout + result.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args(argv)
    exit_code, nodeids, collection_output = collect_nodeids()
    module_findings: dict[str, list[str]] = {}
    for module in sorted({_module_path(nodeid) for nodeid in nodeids}):
        findings = audit_module(module)
        if findings:
            module_findings[str(module.relative_to(REPO_ROOT)).replace("\\", "/")] = findings
    skipped = sorted(nodeid for nodeid in nodeids if str(_module_path(nodeid).relative_to(REPO_ROOT)).replace("\\", "/") in module_findings)
    report = {
        "command": "python -m pytest --collect-only -q tests ops/r3/tests -p no:cacheprovider",
        "collect_exit_code": exit_code,
        "collected_nodeids": nodeids,
        "allowlisted_nodeids": nodeids if not skipped else sorted(set(nodeids) - set(skipped)),
        "module_findings": module_findings,
        "skipped_nodeids": skipped,
        "skipped_count": len(skipped),
        "status": "PASS" if exit_code == 0 and not skipped else "BLOCKED",
        "metadata_only": True,
        "live_root_accessed": False,
        "collection_output_tail": collection_output[-2000:],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "collect_exit_code", "skipped_count", "metadata_only", "live_root_accessed")}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
