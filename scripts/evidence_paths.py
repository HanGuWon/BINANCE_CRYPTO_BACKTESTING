"""Deterministic cross-platform paths for preserved evidence roots."""
from __future__ import annotations

import os
from pathlib import Path


V6_ROOT = r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r2b_restricted_derivatives_v1_checkpoints_v6"
V6_REGISTRY_SHA256 = "3c61d923fe2cf88714c8cd2592264800ef2880db894dd2a21170fdf4fcc85302"


def _wsl_candidate(windows_path: str) -> Path:
    drive, remainder = windows_path.split(":", 1)
    return Path("/mnt") / drive.lower() / remainder.lstrip("\\/").replace("\\", "/")


def resolve_evidence_root(
    *,
    env_var: str = "R2B_V6_EVIDENCE_ROOT",
    windows_path: str = V6_ROOT,
    expected_campaign: str = "r2b_restricted_derivatives_v1",
    expected_registry_sha256: str = V6_REGISTRY_SHA256,
) -> Path | None:
    """Resolve an evidence root without silently weakening a regression test.

    An explicit environment override wins. Otherwise both native Windows and
    the deterministic WSL `/mnt/<drive>` mapping are considered. ``None`` is
    returned only when the evidence is genuinely unavailable.
    """
    override = os.environ.get(env_var)
    candidates = [Path(override)] if override else [Path(windows_path), _wsl_candidate(windows_path)]
    for candidate in candidates:
        manifest_path = candidate / "run_manifest.json"
        if not (candidate.is_dir() and manifest_path.is_file()):
            continue
        try:
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (manifest.get("campaign_id") == expected_campaign
                and manifest.get("unit_count") == 576
                and manifest.get("final_holdout_status") == "UNTOUCHED"
                and manifest.get("registry_sha256") == expected_registry_sha256):
            return candidate
    return None


def resolve_preserved_v6_root() -> Path | None:
    """Resolve only the immutable v6 regression evidence (not R3 data)."""
    return resolve_evidence_root()
