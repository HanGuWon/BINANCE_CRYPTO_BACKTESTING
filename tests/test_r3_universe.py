from __future__ import annotations

import pytest

from binance_research.r3_universe import RolloverStateMachine, UniverseContractError, freeze_um_top50


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


def test_rollover_suspends_when_september_unavailable_then_reenters() -> None:
    august = freeze_um_top50(_ranking(), effective_month="2026-08", source_sha256="a" * 64)
    machine = RolloverStateMachine(august)
    assert machine.rollover(effective_month="2026-09", next_roster=None) == "UNIVERSE_ROLLOVER_GAP"
    september = freeze_um_top50(_ranking(), effective_month="2026-09", source_sha256="b" * 64)
    assert machine.rollover(effective_month="2026-09", next_roster=september) == "ACTIVE"
    assert [item["state"] for item in machine.receipts] == ["UNIVERSE_ROLLOVER_GAP", "LEAVE", "REENTER"]
