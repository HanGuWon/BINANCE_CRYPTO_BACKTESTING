from pathlib import Path
import hashlib
import json

import pytest

import scripts.qualify_r3_forward_ranking as forward_ranking
from scripts.qualify_r3_forward_ranking import build_forward_ranking_from_raw, qualify


def test_raw_forward_ranking_requires_archive_sidecar(tmp_path: Path) -> None:
    archive_dir = tmp_path / "um" / "klines" / "AAAUSDT" / "1d"
    archive_dir.mkdir(parents=True)
    archive = archive_dir / "AAAUSDT-1d-2026-07.zip"
    archive.write_bytes(b"not-a-valid-archive")
    with pytest.raises(RuntimeError, match="MISSING_ARCHIVE_MANIFEST"):
        build_forward_ranking_from_raw(tmp_path, tmp_path, tmp_path / "out", effective_month="2026-08")


def test_raw_forward_ranking_success_path_uses_requested_prior_month(tmp_path: Path, monkeypatch) -> None:
    archive_dir = tmp_path / "um" / "klines" / "AAAUSDT" / "1d"
    archive_dir.mkdir(parents=True)
    archive = archive_dir / "AAAUSDT-1d-2026-07.zip"
    archive.write_bytes(b"verified-by-fixture")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (archive.with_suffix(archive.suffix + ".manifest.json")).write_text(json.dumps({
        "market_type": "um", "dataset": "klines", "interval": "1d",
        "computed_sha256": digest, "published_sha256": digest,
    }), encoding="utf-8")
    census = tmp_path / "census"
    census.mkdir()
    (census / "um_archive_symbol_census.csv").write_text("market,symbol,first_archive_month\num,AAAUSDT,2020-01\n", encoding="utf-8")
    monkeypatch.setattr(forward_ranking, "load_kline_archive", lambda _: object())
    monkeypatch.setattr(forward_ranking, "validate_klines", lambda *_: [])
    monkeypatch.setattr(forward_ranking, "_summarize_1d_archive", lambda _: {
        "observed_days": 31, "integrity_status": "PASS", "issue_codes": "", "row_count": 31,
    })
    def fake_build(manifest, taxonomy, output_dir, *, census_dir=None):
        result = manifest.assign(universe_month="2026-08", volume_month="2026-07", coverage_ratio=1.0,
                                 eligibility_reason="ELIGIBLE_COMPLETE_PRIOR_MONTH", selected_top50=True, rank=1)
        result.to_csv(output_dir / "universe_monthly.csv", index=False)
        return result
    monkeypatch.setattr(forward_ranking, "build_monthly_cohorts", fake_build)
    ranked = build_forward_ranking_from_raw(tmp_path, census, tmp_path / "out", effective_month="2026-08")
    assert ranked.is_file()
    assert "2026-07" in (tmp_path / "out" / "raw_1d_manifest.csv").read_text(encoding="utf-8")


def test_precomputed_control_is_explicitly_non_scientific() -> None:
    source = Path("campaigns/r1_final_panel_v1/universe_monthly.csv")
    roster = Path("campaigns/r3_prospective_context_v1/rosters/2026-08.json")
    result = qualify(source, roster)
    assert result["outcomes_accessed"] is False
    assert result["september_roster"] == "NOT_BUILT_BEFORE_BOUNDARY"


def test_spot_archive_cannot_enter_um_discovery(tmp_path: Path) -> None:
    spot = tmp_path / "spot" / "klines" / "UMAUSDT" / "1d"
    spot.mkdir(parents=True)
    (spot / "UMAUSDT-1d-2026-07.zip").write_bytes(b"spot-only")
    with pytest.raises(RuntimeError, match="NO_RAW_1D_ARCHIVES"):
        build_forward_ranking_from_raw(tmp_path, tmp_path, tmp_path / "out", effective_month="2026-08")
