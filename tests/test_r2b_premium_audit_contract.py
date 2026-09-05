from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_r2b_premium_coverage import validate_premium_manifest


def _manifest(path: Path, archive: Path, *, dataset: str = "premiumIndexKlines", root: str | None = None) -> None:
    digest = hashlib.sha256(archive.read_bytes()).hexdigest() if archive.exists() else "a" * 64
    row = {
        "symbol": "BTCUSDT",
        "archive_month": "2024-01",
        "dataset": dataset,
        "market": "um",
        "interval": "15m",
        "integrity_status": "PASS",
        "published_sha256": digest,
        "computed_sha256": digest,
        "local_path": str(archive),
        "object_size": archive.stat().st_size if archive.exists() else None,
    }
    # The production manifest has many rows; this fixture intentionally uses
    # three symbols to satisfy the anti-R1 anchor gate.
    rows = [dict(row, symbol=symbol) for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
    if root is not None:
        for item in rows:
            item["causal_root"] = root
    pd.DataFrame(rows).to_csv(path, index=False)


def test_authoritative_shape_and_archive_bytes_are_verified(tmp_path: Path) -> None:
    archive = tmp_path / "BTCUSDT-15m-2024-01.zip"
    archive.write_bytes(b"synthetic-premium-archive")
    manifest = tmp_path / "premium_archive_manifest.csv"
    _manifest(manifest, archive, root=str(tmp_path))
    frame = validate_premium_manifest(manifest, expected_root=tmp_path, verify_archives=True)
    assert len(frame) == 3


@pytest.mark.parametrize(
    ("dataset", "message"),
    [("klines", "dataset=premiumIndexKlines"), ("premiumIndexKlines", "unexpectedly small")],
)
def test_manifest_rejects_wrong_dataset_or_r1_sized_anchor(tmp_path: Path, dataset: str, message: str) -> None:
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"archive")
    manifest = tmp_path / "premium_archive_manifest.csv"
    if dataset == "premiumIndexKlines":
        # one symbol is intentionally an R1-style anchor
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        pd.DataFrame([{
            "symbol": "BTCUSDT", "dataset": dataset, "market": "um", "interval": "15m",
            "integrity_status": "PASS", "published_sha256": digest, "computed_sha256": digest,
            "local_path": str(archive),
        }]).to_csv(manifest, index=False)
    else:
        _manifest(manifest, archive, dataset=dataset)
    with pytest.raises(ValueError, match=message):
        validate_premium_manifest(manifest)


def test_manifest_rejects_historical_anchor_filename(tmp_path: Path) -> None:
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"archive")
    manifest = tmp_path / "derivative_archive_manifest.csv"
    _manifest(manifest, archive)
    with pytest.raises(ValueError, match="historical R1 anchor"):
        validate_premium_manifest(manifest)


def test_manifest_root_conflict_and_missing_archive_fail_closed(tmp_path: Path) -> None:
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"archive")
    manifest = tmp_path / "premium_archive_manifest.csv"
    _manifest(manifest, archive, root=str(tmp_path / "other"))
    with pytest.raises(ValueError, match="root declaration conflicts"):
        validate_premium_manifest(manifest, expected_root=tmp_path, verify_archives=True)

    missing = tmp_path / "missing.zip"
    _manifest(manifest, missing, root=str(tmp_path))
    with pytest.raises(ValueError, match="archive verification failed"):
        validate_premium_manifest(manifest, expected_root=tmp_path, verify_archives=True)
