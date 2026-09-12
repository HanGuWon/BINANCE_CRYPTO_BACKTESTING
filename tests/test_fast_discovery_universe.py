from __future__ import annotations

import pandas as pd
import pytest

from binance_research.fast_discovery_universe import attach_point_in_time_top50, build_point_in_time_top50


def _volume() -> pd.DataFrame:
    rows = []
    for market in ("spot", "um"):
        rows.extend(
            [
                {"market": market, "universe_month": "2024-02-01", "volume_month": "2024-01-01", "symbol": "AAAUSDT", "prior_month_quote_volume": 200.0, "first_observed": "2023-12-01T00:00Z", "coverage_ratio": 1.0},
                {"market": market, "universe_month": "2024-02-01", "volume_month": "2024-01-01", "symbol": "BBBUSDT", "prior_month_quote_volume": 100.0, "first_observed": "2023-12-01T00:00Z", "coverage_ratio": 1.0},
                {"market": market, "universe_month": "2024-03-01", "volume_month": "2024-02-01", "symbol": "AAAUSDT", "prior_month_quote_volume": 10.0, "first_observed": "2023-12-01T00:00Z", "coverage_ratio": 1.0},
                {"market": market, "universe_month": "2024-03-01", "volume_month": "2024-02-01", "symbol": "BBBUSDT", "prior_month_quote_volume": 5.0, "first_observed": "2023-12-01T00:00Z", "coverage_ratio": 1.0},
            ]
        )
    return pd.DataFrame(rows)


def test_top50_is_ranked_per_market_and_month_from_prior_month_only() -> None:
    result = build_point_in_time_top50(_volume())
    feb = result[result["universe_month"] == "2024-02"]
    assert set(feb.loc[feb["selected_top50"], "symbol"]) == {"AAAUSDT", "BBBUSDT"}
    assert set(feb["market"]) == {"spot", "um"}
    assert result.attrs["holdout_status"] == "UNTOUCHED"
    assert len(result.attrs["membership_sha256"]) == 64


def test_future_month_volume_rewrite_does_not_change_prior_membership() -> None:
    base = build_point_in_time_top50(_volume())
    changed_input = _volume()
    changed_input.loc[(changed_input["universe_month"] == "2024-03-01") & (changed_input["symbol"] == "BBBUSDT"), "prior_month_quote_volume"] = 999999.0
    changed = build_point_in_time_top50(changed_input)
    for market in ("spot", "um"):
        a = base[(base.market == market) & (base.universe_month == "2024-02")].sort_values("symbol")
        b = changed[(changed.market == market) & (changed.universe_month == "2024-02")].sort_values("symbol")
        assert list(a["selected_top50"]) == list(b["selected_top50"])
        assert list(a["rank"]) == list(b["rank"])


def test_non_adjacent_volume_month_fails_closed() -> None:
    bad = _volume()
    bad.loc[0, "volume_month"] = "2023-11-01"
    with pytest.raises(ValueError, match="immediately preceding calendar month"):
        build_point_in_time_top50(bad)


def test_attachment_is_market_keyed_and_rejects_non_cohort_symbol() -> None:
    membership = build_point_in_time_top50(_volume())
    bars = pd.DataFrame({"open_time": pd.to_datetime(["2024-02-15T00:00Z"]), "symbol": ["AAAUSDT"], "close": [1.0]})
    attached = attach_point_in_time_top50(bars, membership, market="um")
    assert attached.loc[0, "market"] == "um"
    assert bool(attached.loc[0, "selected_top50"]) is True
    with pytest.raises(ValueError, match="no point-in-time membership|outside the frozen Top50"):
        attach_point_in_time_top50(bars.assign(symbol="NOTINCOHORT"), membership, market="um")

