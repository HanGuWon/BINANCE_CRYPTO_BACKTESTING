from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from binance_research.forward import append_jsonl_atomic, append_predictions_write_once


def test_incremental_replay_preserves_old_timestamp_and_appends_only_new(tmp_path: Path):
    path = tmp_path / "forward_predictions.csv"
    first = pd.DataFrame(
        [
            {"prediction_id": "a", "decision_time": "2025-01-01T00:00:00Z", "prediction_recorded_at": "2025-01-01T00:01:00Z", "value": 1},
        ]
    )
    append_predictions_write_once(path, first)
    second = pd.DataFrame(
        [
            {"prediction_id": "a", "decision_time": "2025-01-01T00:00:00Z", "prediction_recorded_at": "2025-01-02T00:01:00Z", "value": 1},
            {"prediction_id": "b", "decision_time": "2025-01-01T00:15:00Z", "prediction_recorded_at": "2025-01-02T00:01:00Z", "value": 2},
        ]
    )
    append_predictions_write_once(path, second, allow_replay=True)
    rows = pd.read_csv(path)
    assert list(rows["prediction_id"]) == ["a", "b"]
    assert rows.loc[rows["prediction_id"] == "a", "prediction_recorded_at"].item() == "2025-01-01T00:01:00Z"
    append_predictions_write_once(path, second, allow_replay=True)
    assert len(pd.read_csv(path)) == 2


def test_incremental_receipt_is_append_only_and_crash_safe(tmp_path: Path):
    path = tmp_path / "run_receipts.jsonl"
    append_jsonl_atomic(path, {"cutoff": "T0", "rows": 1})
    append_jsonl_atomic(path, {"cutoff": "T1", "rows": 2})
    assert [json.loads(line)["cutoff"] for line in path.read_text(encoding="utf-8").splitlines()] == ["T0", "T1"]
    path.with_name(path.name + ".tmp").write_text("interrupted", encoding="utf-8")
    with pytest.raises(FileExistsError):
        append_jsonl_atomic(path, {"cutoff": "T2", "rows": 3})

