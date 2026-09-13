from __future__ import annotations

import pandas as pd
import pytest

from binance_research.fast_discovery_replay import replay_finalists


def _finalist() -> pd.DataFrame:
    return pd.DataFrame([{"candidate_id": "S2_01", "feature_id": "signal", "variant": "raw", "side": "LONG", "horizon_bars": 2}])


def _executor(group, signal, **kwargs):
    rows = []
    for i, value in enumerate(signal):
        if value == 1.0:
            rows.append({"decision_time": group.open_time.iloc[i], "symbol": group.symbol.iloc[i], "side": kwargs["side"], "signal_value": float(value), "entry_time": group.open_time.iloc[i + 1], "exit_time": group.open_time.iloc[min(i + 2, len(group) - 1)], "gross_return": 0.01, "funding_cashflow": 0.0, "net_return": 0.009})
    return pd.DataFrame(rows)


def _builder(group, feature_id, variant, market):
    return group[feature_id]


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"open_time": pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC"), "symbol": ["AAA"] * 4, "segment_id": ["seg1"] * 4, "signal": [0.0, 1.0, 0.0, 0.0]})


def test_replay_hands_off_only_explicit_finalist() -> None:
    result = replay_finalists(_frame(), _finalist(), signal_builder=_builder, executor=_executor, market="um", timeframe="1h", validation_start=pd.Timestamp("2024-01-01", tz="UTC"), validation_end=pd.Timestamp("2024-01-02", tz="UTC"), universe_top50={("um", "", "AAA")}, funding_events=None)
    assert list(result.candidate_id.unique()) == ["S2_01"]
    assert set(("decision_time", "symbol", "side", "signal_value", "entry_time", "exit_time", "gross_return", "funding_cashflow", "net_return")).issubset(result.columns)


def test_empty_finalists_are_noop() -> None:
    result = replay_finalists(_frame(), pd.DataFrame(), signal_builder=_builder, executor=_executor, market="spot", timeframe="15m", validation_start=pd.Timestamp("2024-01-01", tz="UTC"), validation_end=pd.Timestamp("2024-01-02", tz="UTC"), universe_top50=set(), funding_events=None)
    assert result.empty


def test_replay_refuses_holdout_rows() -> None:
    frame = _frame().assign(final_holdout=[False, True, False, False])
    with pytest.raises(ValueError, match="final-holdout"):
        replay_finalists(frame, _finalist(), signal_builder=_builder, executor=_executor, market="um", timeframe="1h", validation_start=pd.Timestamp("2024-01-01", tz="UTC"), validation_end=pd.Timestamp("2024-01-02", tz="UTC"), universe_top50=set(), funding_events=None)


def test_replay_requires_complete_finalist_contract() -> None:
    with pytest.raises(ValueError, match="finalist contract"):
        replay_finalists(_frame(), pd.DataFrame([{"candidate_id": "x"}]), signal_builder=_builder, executor=_executor, market="um", timeframe="1h", validation_start=pd.Timestamp("2024-01-01", tz="UTC"), validation_end=pd.Timestamp("2024-01-02", tz="UTC"), universe_top50=set(), funding_events=None)
