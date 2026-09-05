from __future__ import annotations

import pytest
from pathlib import Path

from binance_research.r3_universe import (
    RolloverStateMachine,
    UniverseContractError,
    build_causal_monthly_roster,
    freeze_um_top50,
    replay_roster_artifact,
    write_roster_artifact,
)


def _ranking(count: int = 50, month: str = "2026-08") -> list[dict[str, object]]:
    return [{"market": "um", "symbol": f"S{i:03d}USDT", "rank": i + 1, "selected_top50": True, "universe_month": month, "prior_rank": i + 1} for i in range(count)]


def test_freeze_um_roster_requires_exactly_50_and_is_hashed() -> None:
    roster = freeze_um_top50(_ranking(), effective_month="2026-08", source_sha256="a" * 64)
    assert len(roster.symbols) == 50
    assert roster.effective_start.startswith("2026-08-01")
    assert len(roster.roster_sha256) == 64


def test_roster_rejects_wrong_market_or_count() -> None:
    with pytest.raises(UniverseContractError):
        freeze_um_top50([{**row, "market": "spot"} for row in _ranking()], effective_month="2026-08", source_sha256="a" * 64)
    with pytest.raises(UniverseContractError):
        freeze_um_top50(_ranking(49), effective_month="2026-08", source_sha256="a" * 64)
    with pytest.raises(UniverseContractError):
        freeze_um_top50(_ranking(), effective_month="2026-08", source_sha256="z" * 64)


def test_rollover_suspends_when_september_unavailable_then_reenters() -> None:
    august = freeze_um_top50(_ranking(), effective_month="2026-08", source_sha256="a" * 64)
    machine = RolloverStateMachine(august)
    assert machine.rollover(effective_month="2026-09", next_roster=None) == "UNIVERSE_ROLLOVER_GAP"
    september = freeze_um_top50(_ranking(), effective_month="2026-09", source_sha256="b" * 64)
    assert machine.rollover(effective_month="2026-09", next_roster=september) == "ACTIVE"
    assert [item["state"] for item in machine.receipts] == ["UNIVERSE_ROLLOVER_GAP", "LEAVE", "REENTER"]


def test_causal_monthly_roster_build_and_replay_from_completed_prior_month(tmp_path: Path) -> None:
    source = tmp_path / "universe_monthly.csv"
    rows = [
        {
            "market": "um",
            "symbol": f"S{i:03d}USDT",
            "volume_month": "2026-08",
            "universe_month": "2026-09",
            "coverage_ratio": 1.0,
            "eligibility_reason": "ELIGIBLE_COMPLETE_PRIOR_MONTH",
            "selected_top50": "True",
        }
        for i in range(50)
    ]
    import pandas as pd

    pd.DataFrame(rows).to_csv(source, index=False)
    roster = build_causal_monthly_roster(source, effective_month="2026-09")
    artifact = write_roster_artifact(roster, tmp_path / "2026-09.json", source_path=source)
    replay = replay_roster_artifact(artifact, effective_month="2026-09")
    assert replay == roster


def test_causal_monthly_roster_rejects_incomplete_prior_month(tmp_path: Path) -> None:
    source = tmp_path / "universe_monthly.csv"
    rows = [
        {
            "market": "um",
            "symbol": f"S{i:03d}USDT",
            "volume_month": "2026-08",
            "universe_month": "2026-09",
            "coverage_ratio": 0.5 if i == 0 else 1.0,
            "eligibility_reason": "PARTIAL_PRIOR_MONTH_EXCLUDED" if i == 0 else "ELIGIBLE_COMPLETE_PRIOR_MONTH",
            "selected_top50": "True",
        }
        for i in range(50)
    ]
    import pandas as pd

    pd.DataFrame(rows).to_csv(source, index=False)
    with pytest.raises(UniverseContractError, match="non-complete|incomplete"):
        build_causal_monthly_roster(source, effective_month="2026-09")
