"""Append-only archive revision provenance."""

from __future__ import annotations

import csv
import io
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


REVISION_COLUMNS = [
    "archive_url", "old_sha256", "new_sha256", "old_last_modified",
    "new_last_modified", "detected_at", "revision_status",
    "campaigns_using_old_revision", "campaigns_using_new_revision",
]


def append_archive_revision(path: Path, revision: dict[str, object]) -> pd.DataFrame:
    """Append one immutable revision row without rewriting prior history."""
    missing = set(REVISION_COLUMNS) - set(revision)
    if missing:
        raise ValueError(f"missing archive revision fields: {', '.join(sorted(missing))}")
    record = {key: revision[key] for key in REVISION_COLUMNS}
    record["detected_at"] = str(record["detected_at"] or datetime.now(UTC).isoformat())
    record["revision_status"] = str(record["revision_status"] or "DETECTED_VALID_REVISION")
    destination = Path(path)
    if destination.is_symlink():
        raise ValueError(f"archive revision destination must not be a symlink: {destination}")
    rows: list[dict[str, str]] = []
    if destination.exists():
        with destination.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or list(reader.fieldnames) != REVISION_COLUMNS:
                raise ValueError(f"archive revision schema mismatch: {destination}")
            rows = [{key: str(row.get(key, "")) for key in REVISION_COLUMNS} for row in reader]
    normalized_record = {key: str(record[key]) for key in REVISION_COLUMNS}
    matching = [row for row in rows if row["archive_url"] == normalized_record["archive_url"] and row["new_sha256"] == normalized_record["new_sha256"]]
    if matching:
        if matching[0] == normalized_record:
            return pd.DataFrame(rows, columns=REVISION_COLUMNS)
        raise ValueError("immutable archive revision collision")

    destination.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=REVISION_COLUMNS, lineterminator="\n")
    if not destination.exists():
        writer.writeheader()
    writer.writerow(normalized_record)
    payload = buffer.getvalue().encode("utf-8")
    if destination.exists():
        with destination.open("ab") as handle:
            existing_bytes = destination.read_bytes()
            if existing_bytes and not existing_bytes.endswith((b"\n", b"\r")):
                handle.write(b"\n")
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    else:
        with destination.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return pd.DataFrame(rows + [normalized_record], columns=REVISION_COLUMNS)
