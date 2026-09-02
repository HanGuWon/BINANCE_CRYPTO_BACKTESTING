from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd

import scripts.prepare_r3_post_boundary_launch as executor
import scripts.qualify_r3_discovery_path as preflight
from binance_research.r3_universe import build_causal_monthly_roster, write_roster_artifact
from binance_research.data import ArchiveRequest
from scripts.qualify_r3_forward_ranking import build_forward_ranking_from_verified_source


def _zip(path: Path, month: str, days: list[int]) -> str:
    rows = []
    for day in days:
        stamp = int(pd.Timestamp(f"{month}-{day:02d}", tz="UTC").timestamp() * 1000)
        rows.append([stamp, 1, 2, 0.5, 1.5, 10, stamp + 86_400_000 - 1, 15, 1, 5, 7, 0])
    payload = "".join(",".join(map(str, row)) + "\n" for row in rows)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"FIXUSDT-1d-{month}.csv", payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_archive_request_percent_encodes_non_ascii_symbol() -> None:
    request = ArchiveRequest("um", "klines", "龙虾USDT", 2026, 7, interval="1d")
    assert "%E9%BE%99%E8%99%BEUSDT" in request.url()
    assert "龙虾" not in request.url()


def test_month_inventory_uses_actual_source_month_and_no_guessed_objects() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def list_objects_v2(self, prefix: str):
            self.calls.append(prefix)
            return [], [], 1

    client = Client()
    taxonomy = pd.DataFrame([
        {"market": "um", "symbol": "FIXUSDT", "primary_crypto_eligible": True},
        {"market": "um", "symbol": "STALEUSDT", "primary_crypto_eligible": True},
    ])
    listed = pd.DataFrame([{"market": "um", "symbol": "FIXUSDT", "archive_month": "2026-07", "key": "monthly/FIXUSDT-1d-2026-07.zip"}])
    inventory = executor._build_month_source_inventory(taxonomy, listed, client, "2026-07")
    assert inventory["month"] == "2026-07"
    assert inventory["discovered_symbols"] == ["FIXUSDT"]
    assert inventory["no_historical_source_symbols"] == ["STALEUSDT"]
    assert client.calls == ["data/futures/um/daily/klines/STALEUSDT/1d/"]


def test_month_acquisition_names_and_provenance_are_source_month_scoped(monkeypatch, tmp_path: Path) -> None:
    import scripts.build_r16_1d_universe as builder

    listed = pd.DataFrame([{"market": "um", "symbol": "FIXUSDT", "archive_month": "2026-07"}])
    taxonomy = pd.DataFrame([{"market": "um", "symbol": "FIXUSDT", "primary_crypto_eligible": True}])
    monkeypatch.setattr(builder, "census_1d", lambda *_args, **_kwargs: (taxonomy, listed))
    monkeypatch.setattr(builder, "acquire_1d", lambda frame, **_kwargs: pd.DataFrame([{"market": "um", "symbol": "FIXUSDT", "archive_month": "2026-07", "raw_path": str(tmp_path / "fix.zip"), "published_sha256": "a" * 64, "computed_sha256": "a" * 64, "integrity_status": "PASS"}]))
    result = executor._acquire_month_source({"control_root": str(tmp_path), "raw_root": str(tmp_path / "raw"), "source_month": "2026-07"}, "2026-07")
    assert result["source_month"] == "2026-07"
    assert result["manifest_path"].endswith("2026-07_acquisition.csv")
    assert result["inventory_path"].endswith("2026-07_source_inventory.json")


def test_month_verifier_rejects_missing_calendar_day(tmp_path: Path) -> None:
    raw = tmp_path / "partial.zip"
    sha = _zip(raw, "2026-07", list(range(1, 31)))
    manifest = tmp_path / "2026-07_acquisition.csv"
    pd.DataFrame([{"market": "um", "symbol": "FIXUSDT", "archive_month": "2026-07", "integrity_status": "PASS", "published_sha256": sha, "computed_sha256": sha, "raw_path": str(raw), "source_mode": "MONTHLY_ARCHIVE"}]).to_csv(manifest, index=False)
    inventory = tmp_path / "2026-07_source_inventory.json"
    inventory.write_text(json.dumps({"status": "PASS", "market": "um", "dataset": "klines", "interval": "1d", "month": "2026-07", "historical_taxonomy_symbols": ["FIXUSDT"], "discovered_symbols": ["FIXUSDT"], "discovered_objects": [{"market": "um", "symbol": "FIXUSDT", "archive_month": "2026-07", "source_mode": "MONTHLY_ARCHIVE"}]}), encoding="utf-8")
    result = executor._verify_month_source({"control_root": str(tmp_path), "AUGUST_SOURCE_ACQUISITION": {"manifest_path": str(manifest), "inventory_path": str(inventory)}}, "2026-07")
    payload = json.loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
    assert payload["month"] == "2026-07"
    assert payload["complete_source_eligible_symbol_count"] == 0
    assert payload["partial_source_symbol_count"] == 1


def test_verified_source_ranker_rejects_non_exact_calendar(tmp_path: Path) -> None:
    raw = tmp_path / "partial.zip"
    sha = _zip(raw, "2026-07", list(range(1, 31)))
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"status": "PASS", "market": "um", "interval": "1d", "verified_inputs": [{"symbol": "FIXUSDT", "path": str(raw), "sha256": sha}], "expected_symbols": ["FIXUSDT"]}), encoding="utf-8")
    census = tmp_path / "census"
    census.mkdir()
    pd.DataFrame([{"market": "um", "symbol": "FIXUSDT", "first_archive_month": "2026-07"}]).to_csv(census / "um_archive_symbol_census.csv", index=False)
    try:
        build_forward_ranking_from_verified_source(receipt, census, tmp_path / "out", effective_month="2026-08")
    except RuntimeError as exc:
        assert "INCOMPLETE" in str(exc)
    else:
        raise AssertionError("non-exact calendar unexpectedly ranked")


def test_preflight_receipt_declares_authoritative_discovery_and_no_outcomes(monkeypatch, tmp_path: Path) -> None:
    ranking = tmp_path / "ranking.csv"
    rows = [{"market": "um", "symbol": f"FIX{n:03d}USDT", "volume_month": "2026-07", "universe_month": "2026-08", "coverage_ratio": 1.0, "eligibility_reason": "ELIGIBLE_COMPLETE_PRIOR_MONTH", "rank": n, "selected_top50": True} for n in range(1, 51)]
    pd.DataFrame(rows).to_csv(ranking, index=False)
    committed = tmp_path / "committed.json"
    roster = build_causal_monthly_roster(ranking, effective_month="2026-08")
    write_roster_artifact(roster, committed, source_path=ranking)
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"historical_taxonomy_symbol_count": 50, "discovered_symbols": [row["symbol"] for row in rows], "discovered_objects": [{"symbol": row["symbol"], "source_mode": "MONTHLY_ARCHIVE"} for row in rows], "no_historical_source_symbol_count": 0}), encoding="utf-8")
    acquisition = {"inventory_path": str(inventory), "manifest_path": str(tmp_path / "manifest.csv")}
    Path(acquisition["manifest_path"]).write_text("market,symbol,archive_month\n", encoding="utf-8")
    verification = tmp_path / "verification.json"
    verification.write_text(json.dumps({"complete_source_eligible_symbol_count": 50, "partial_source_symbol_count": 0, "source_integrity_blocker_count": 0}), encoding="utf-8")
    monkeypatch.setattr(preflight, "_fresh_d_root", lambda _path: tmp_path)
    monkeypatch.setattr(preflight.executor, "_acquire_month_source", lambda *_args, **_kwargs: acquisition)
    monkeypatch.setattr(preflight.executor, "_verify_month_source", lambda *_args, **_kwargs: {"receipt_path": str(verification)})
    monkeypatch.setattr(preflight, "build_forward_ranking_from_verified_source", lambda *_args, **_kwargs: ranking)
    result = preflight.run_preflight(source_month="2026-07", effective_month="2026-08", work_root=tmp_path, raw_root=tmp_path, census_dir=tmp_path, committed_roster=committed, receipt_path=tmp_path / "parity.json")
    assert result["status"] == "PASS"
    assert result["ranking_input"] == "AUTHORITATIVE_MONTH_SCOPED_DISCOVERY"
    assert result["outcomes_accessed"] is False
    assert result["resulting_roster_logical_sha256"] == result["committed_roster_logical_sha256"]
