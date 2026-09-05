"""Regression tests for the corrected R2A preregistration (pre-outcome)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_r2a_registry import KNOWN_VARIANTS, SIGNAL_SEMANTICS, LEGAL_SIDES, verify_registry  # noqa: E402

REGISTRY = ROOT / "campaigns" / "r2a_standalone_evidence_v1" / "trial_registry.csv"
AVAILABILITY = ROOT / "campaigns" / "r1_final_panel_v1" / "feature_availability_final.csv"


def test_registry_exactly_matches_r2a_primary_eligibility() -> None:
    registry = pd.read_csv(REGISTRY)
    availability = pd.read_csv(AVAILABILITY)
    primary = set(map(tuple, availability.loc[availability.classification == "R2A_PRIMARY", ["feature", "market", "timeframe"]].values))
    for row in registry.itertuples(index=False):
        assert (row.feature_id, row.market, row.timeframe) in primary


def test_no_1h_breadth_trials() -> None:
    registry = pd.read_csv(REGISTRY)
    assert len(registry) == 252
    breadth_1h = registry[(registry.feature_id == "context.market_breadth") & (registry.timeframe == "1h")]
    assert breadth_1h.empty


def test_spot_never_short() -> None:
    registry = pd.read_csv(REGISTRY)
    assert not ((registry.market == "spot") & (registry.side == "SHORT")).any()
    assert set(registry.loc[registry.market == "spot", "side"]) == {"LONG"}
    assert set(registry.loc[registry.market == "um", "side"]) <= LEGAL_SIDES["um"]


def test_all_trials_mechanically_verified() -> None:
    summary = verify_registry(REGISTRY, AVAILABILITY)
    assert summary["trials"] == 252
    families = summary["families"]
    assert families == {
        "spot|15m": 27,
        "spot|1h": 26,
        "spot|4h": 27,
        "um|15m": 58,
        "um|1h": 56,
        "um|4h": 58,
    }


def test_deterministic_signal_semantics_exist_for_every_registered_pair() -> None:
    registry = pd.read_csv(REGISTRY)
    pairs = set(zip(registry.feature_id, registry.variant))
    missing = pairs - set(SIGNAL_SEMANTICS)
    assert not missing
    unknown = set(SIGNAL_SEMANTICS) - {(fid, v) for fid, variants in KNOWN_VARIANTS.items() for v in variants}
    assert not unknown


def test_trial_ids_are_deterministic_sequence() -> None:
    registry = pd.read_csv(REGISTRY)
    assert list(registry.trial_id) == [f"T{i:04d}" for i in range(1, 253)]


def test_amendment_document_exists_and_states_preoutcome() -> None:
    text = (ROOT / "campaigns" / "r2a_standalone_evidence_v1" / "R2A_PROTOCOL_AMENDMENT_001.md").read_text(encoding="utf-8")
    assert "NO R2A outcome was inspected" in text
    assert "255 to exactly 252" in text
