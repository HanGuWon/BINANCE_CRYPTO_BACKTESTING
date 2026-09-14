from __future__ import annotations

import pandas as pd

from scripts.run_fast_discovery_v2_broad_replication import (
    archive_list_sha256,
    cohort_membership,
    discover_archives,
    _month_from_name,
)


def test_month_parser_is_strict() -> None:
    assert _month_from_name("AAAUSDT-15m-2024-02.zip") == "2024-02"
    assert _month_from_name("AAAUSDT-15m-not-a-month.zip") is None


def test_cohort_membership_reads_only_um_and_preserves_selection(tmp_path) -> None:
    path = tmp_path / "universe.csv"
    pd.DataFrame(
        [
            {"market": "spot", "symbol": "AAAUSDT", "universe_month": "2024-02", "selected_top50": True},
            {"market": "um", "symbol": "AAAUSDT", "universe_month": "2024-02", "selected_top50": True},
            {"market": "um", "symbol": "BBBUSDT", "universe_month": "2024-02", "selected_top50": False},
        ]
    ).to_csv(path, index=False)
    assert cohort_membership(path) == {("AAAUSDT", "2024-02"): True, ("BBBUSDT", "2024-02"): False}


def test_archive_discovery_is_deterministic_and_reports_missing(tmp_path) -> None:
    raw = tmp_path / "raw" / "um" / "klines"
    (raw / "AAAUSDT" / "15m").mkdir(parents=True)
    (raw / "AAAUSDT" / "15m" / "AAAUSDT-15m-2024-02.zip").write_bytes(b"x")
    membership = {("AAAUSDT", "2024-02"): True, ("BBBUSDT", "2024-02"): True}
    rows, missing = discover_archives(raw, membership, "15m")
    assert len(rows) == 1
    assert rows[0]["relative_path"] == "AAAUSDT/15m/AAAUSDT-15m-2024-02.zip"
    assert missing == ["BBBUSDT|15m|2024-02"]
    assert archive_list_sha256(rows) == archive_list_sha256(list(reversed(rows)))
