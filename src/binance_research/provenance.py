"""Append-only archive revision provenance."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


REVISION_COLUMNS = [
    "archive_url", "old_sha256", "new_sha256", "old_last_modified",
    "new_last_modified", "detected_at", "revision_status",
    "campaigns_using_old_revision", "campaigns_using_new_revision",
]


def append_archive_revision(path: Path, revision: dict[str, object]) -> pd.DataFrame:
    """Append a detected valid revision without overwriting prior history."""
    missing = set(REVISION_COLUMNS) - set(revision)
    if missing:
        raise ValueError(f"missing archive revision fields: {', '.join(sorted(missing))}")
    record = {key: revision[key] for key in REVISION_COLUMNS}
    record["detected_at"] = str(record["detected_at"] or datetime.now(UTC).isoformat())
    record["revision_status"] = str(record["revision_status"] or "DETECTED_VALID_REVISION")
    destination = Path(path)
    if destination.exists():
        existing = pd.read_csv(destination)
        existing = existing.reindex(columns=REVISION_COLUMNS)
    else:
        existing = pd.DataFrame(columns=REVISION_COLUMNS)
    duplicate = (existing["archive_url"].astype(str) == str(record["archive_url"])) & (existing["new_sha256"].astype(str) == str(record["new_sha256"]))
    if not duplicate.any():
        existing = pd.concat([existing, pd.DataFrame([record])], ignore_index=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing.to_csv(destination, index=False)
    return existing
