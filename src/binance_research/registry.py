from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    feature_id: str
    code_hash: str
    dataset_hash: str
    market: str
    symbol_universe: tuple[str, ...]
    timeframe: str
    date_range: tuple[str, str]
    parameters: dict[str, Any]
    target_horizon: str
    execution_assumptions: dict[str, Any]
    fee_model: dict[str, Any]
    slippage_model: dict[str, Any]
    funding_model: dict[str, Any]
    split_boundaries: dict[str, Any]
    timestamp: str
    result_artifact_paths: tuple[str, ...]
    final_holdout_accessed: bool

    @classmethod
    def create(cls, **values: Any) -> "ExperimentRecord":
        return cls(
            experiment_id=values.pop("experiment_id", str(uuid.uuid4())),
            timestamp=values.pop("timestamp", datetime.now(UTC).isoformat()),
            **values,
        )


def code_hash(root: Path) -> str:
    root = Path(root)
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain=v1"], cwd=root, capture_output=True, text=True, check=True,
        ).stdout
        if not dirty:
            return commit
    except (OSError, subprocess.CalledProcessError):
        pass
    digest = hashlib.sha256()
    candidates = [root / "pyproject.toml", root / "README.md", root / ".gitignore"]
    for directory in ("src", "tests", "configs", "docs"):
        directory_path = root / directory
        if directory_path.exists():
            candidates.extend(path for path in directory_path.rglob("*") if path.is_file())
    for path in sorted({path for path in candidates if path.exists()}):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return "working-tree:" + digest.hexdigest()


class ExperimentRegistry:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, record: ExperimentRecord) -> None:
        values = asdict(record)
        payload = _canonical_json(values) + "\n"
        payload_bytes = payload.encode("utf-8")
        identity = canonical_experiment_identity(values)
        if self.path.exists():
            for line in self.path.read_bytes().splitlines(keepends=True):
                if not line.strip():
                    continue
                try:
                    existing = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError(f"invalid experiment registry record: {self.path}") from exc
                existing_identity = canonical_experiment_identity(existing)
                if existing.get("experiment_id") == record.experiment_id or existing_identity == identity:
                    if line == payload_bytes:
                        return
                    raise ValueError(f"immutable experiment identity collision: {record.experiment_id}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o644)
        try:
            os.write(descriptor, payload_bytes)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def read(self) -> list[ExperimentRecord]:
        if not self.path.exists():
            return []
        return [ExperimentRecord(**json.loads(line)) for line in self.path.read_text(encoding="utf-8").splitlines() if line]


def _canonical_json(values: Mapping[str, Any]) -> str:
    return json.dumps(dict(values), sort_keys=True, separators=(",", ":"), default=str)


def canonical_experiment_identity(record_or_mapping: ExperimentRecord | Mapping[str, Any]) -> str:
    """Return the stable identity hash for a record, ignoring only its timestamp."""
    values = asdict(record_or_mapping) if isinstance(record_or_mapping, ExperimentRecord) else dict(record_or_mapping)
    values.pop("timestamp", None)
    return hashlib.sha256(_canonical_json(values).encode("utf-8")).hexdigest()
