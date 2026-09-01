"""Fail-closed, calibrated-time-gated R3 post-boundary launch executor."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import argparse
import os
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT_SCRIPTS = REPO_ROOT / "scripts"
for _repo_path in (REPO_ROOT_SCRIPTS, REPO_ROOT / "src", REPO_ROOT):
    _repo_path_text = str(_repo_path)
    if _repo_path_text in sys.path:
        sys.path.remove(_repo_path_text)
    sys.path.insert(0, _repo_path_text)

BOUNDARY_UTC = datetime(2026, 9, 1, tzinfo=UTC)
SCIENTIFIC_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v1")
LEGACY_CONTROL_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09")
FAILED_V1_CONTROL_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v1")
FAILED_V2_CONTROL_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v2")
CONTROL_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v3")
SHADOW_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\engineering_shadow_september_launch_v3")
MAX_CLOCK_UNCERTAINTY_MS = 2_000
EXPECTED_REGISTRY_SHA256 = "c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a"


class PostBoundaryBlocked(RuntimeError):
    def __init__(self, code: str, reason: str) -> None:
        self.code, self.reason = code, reason
        super().__init__(f"{code}: {reason}")

    def __str__(self) -> str:
        return f"{self.code}: {self.reason}"


@dataclass(frozen=True)
class CalibratedClock:
    """A Binance server-time sample with an explicit uncertainty bound."""

    server_time: datetime
    uncertainty_ms: float
    sample_count: int = 5

    def __post_init__(self) -> None:
        object.__setattr__(self, "server_time", self.server_time.astimezone(UTC))


StageCallback = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def require_calibrated_boundary(clock: CalibratedClock) -> None:
    if clock.uncertainty_ms > MAX_CLOCK_UNCERTAINTY_MS:
        raise PostBoundaryBlocked("R3_BLOCKED_CLOCK_CAUSALITY", f"Binance clock calibration samples={clock.sample_count}; uncertainty {clock.uncertainty_ms:.3f}ms exceeds {MAX_CLOCK_UNCERTAINTY_MS}ms")
    if clock.server_time < BOUNDARY_UTC:
        raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_ROSTER", f"calibrated Binance time {clock.server_time.isoformat()} from samples={clock.sample_count} is before {BOUNDARY_UTC.isoformat()}")


def require_boundary(now: datetime) -> None:
    require_calibrated_boundary(CalibratedClock(now, 0.0))


def require_fresh_scientific_root(root: Path = SCIENTIFIC_ROOT) -> Path:
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:":
        raise PostBoundaryBlocked("R3_BLOCKED_STORAGE", "scientific root must be D-backed")
    if resolved.exists() and any(resolved.iterdir()):
        raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", "scientific root is not fresh; existing evidence cannot be reused")
    return resolved


def require_control_root(root: Path = CONTROL_ROOT) -> Path:
    resolved = Path(root).resolve()
    if resolved.drive.upper() != "D:":
        raise PostBoundaryBlocked("R3_BLOCKED_STORAGE", "control root must be D-backed")
    forbidden = {
        LEGACY_CONTROL_ROOT.resolve(),
        FAILED_V1_CONTROL_ROOT.resolve(),
        FAILED_V2_CONTROL_ROOT.resolve(),
    }
    if resolved in forbidden:
        raise PostBoundaryBlocked(
            "R3_BLOCKED_LAUNCH_IDENTITY",
            f"control root is reserved historical/failed evidence and cannot authorize launch-v3: {resolved}",
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_artifact_references(proof: Mapping[str, Any]) -> None:
    """Ensure every referenced artifact still matches its pinned SHA256."""
    for key, value in proof.items():
        if not key.endswith("_path") or not isinstance(value, str):
            continue
        path = Path(value)
        if not path.is_file():
            raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", f"referenced artifact missing: {path}")
        hash_key = key[:-5] + "_sha256"
        expected = proof.get(hash_key)
        if expected is not None and hashlib.sha256(path.read_bytes()).hexdigest() != str(expected):
            raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", f"referenced artifact hash changed: {path}")


def _write_stage_receipt(receipt_root: Path, stage: str, proof: Mapping[str, Any]) -> dict[str, Any]:
    receipt_root.mkdir(parents=True, exist_ok=True)
    path = receipt_root / f"{stage.lower()}.json"
    payload = {"stage": stage, "status": "PASS", "proof": dict(proof)}
    payload["proof_sha256"] = _digest(payload["proof"])
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PostBoundaryBlocked("R3_BLOCKED_IMPLEMENTATION", f"invalid {stage} receipt: {exc}") from exc
        if existing != payload:
            raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", f"conflicting {stage} receipt on replay")
        return existing
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _default_blocked(code: str, reason: str) -> StageCallback:
    def callback(_: Mapping[str, Any]) -> Mapping[str, Any]:
        raise PostBoundaryBlocked(code, reason)

    return callback


def _run_stage(stage: str, callback: StageCallback, context: Mapping[str, Any], receipt_root: Path) -> dict[str, Any]:
    path = receipt_root / f"{stage.lower()}.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PostBoundaryBlocked("R3_BLOCKED_IMPLEMENTATION", f"invalid {stage} receipt: {exc}") from exc
        if existing.get("stage") != stage or existing.get("status") != "PASS" or not isinstance(existing.get("proof"), Mapping) or existing.get("proof_sha256") != _digest(existing["proof"]):
            raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", f"conflicting {stage} receipt on replay")
        _validate_artifact_references(existing["proof"])
        return existing
    try:
        proof = callback(context)
    except PostBoundaryBlocked:
        raise
    except Exception as exc:
        raise PostBoundaryBlocked("R3_BLOCKED_IMPLEMENTATION", f"{stage} callback failed: {exc}") from exc
    if not isinstance(proof, Mapping) or not proof:
        raise PostBoundaryBlocked("R3_BLOCKED_IMPLEMENTATION", f"{stage} returned no proof")
    _validate_artifact_references(proof)
    if stage == "SEPTEMBER_ENGINEERING_SHADOW" and proof.get("evidence_mode") == "SCIENTIFIC":
        raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_SHADOW", "engineering shadow proof is contaminated with SCIENTIFIC evidence")
    return _write_stage_receipt(receipt_root, stage, proof)


PRODUCTION_STAGE_NAMES = (
    "AUGUST_SOURCE_ACQUISITION", "AUGUST_SOURCE_VERIFICATION", "SEPTEMBER_RANKING",
    "SEPTEMBER_ROSTER_FREEZE", "SEPTEMBER_ROSTER_REPLAY", "SEPTEMBER_ENGINEERING_SHADOW",
    "LAUNCH_IDENTITY_FREEZE", "LAUNCH_MANIFEST_BUILD", "LAUNCH_SEAL",
    "SCIENTIFIC_ROOT_GATE", "SCIENTIFIC_ACTIVATION",
)


def build_production_callbacks(*, adapters: Mapping[str, StageCallback]) -> dict[str, StageCallback]:
    """Build stage callbacks from named production adapters.

    Production callers must provide every external adapter explicitly; a
    missing adapter is an implementation error rather than an implicit proof.
    The adapter functions are expected to call the repository's acquisition,
    ranking, roster, operations, and collector implementations and return
    machine-readable evidence. Tests may provide local-fixture adapters.
    """
    missing = [name for name in PRODUCTION_STAGE_NAMES if name not in adapters]
    if missing:
        raise ValueError(f"production callback factory missing adapters: {missing}")
    if any(not callable(adapters[name]) for name in PRODUCTION_STAGE_NAMES):
        raise TypeError("production adapters must be callable")
    return {name: adapters[name] for name in PRODUCTION_STAGE_NAMES}


def build_project_production_callbacks() -> dict[str, StageCallback]:
    """Wire the canonical repository implementations for a real invocation."""
    return build_production_callbacks(adapters={
        "AUGUST_SOURCE_ACQUISITION": _acquire_august_source,
        "AUGUST_SOURCE_VERIFICATION": _verify_august_source,
        "SEPTEMBER_RANKING": _build_september_ranking,
        "SEPTEMBER_ROSTER_FREEZE": _freeze_september_roster,
        "SEPTEMBER_ROSTER_REPLAY": _replay_september_roster,
        "SEPTEMBER_ENGINEERING_SHADOW": _run_september_shadow,
        "LAUNCH_IDENTITY_FREEZE": _freeze_launch_identity,
        "LAUNCH_MANIFEST_BUILD": _build_launch_manifest,
        "LAUNCH_SEAL": _build_launch_seal,
        "SCIENTIFIC_ROOT_GATE": lambda ctx: {"root": str(require_fresh_scientific_root(Path(ctx["scientific_root"]))), "fresh": True},
        "SCIENTIFIC_ACTIVATION": _activate_scientific,
    })


def _august_daily_inventory(client: Any, symbol: str) -> list[dict[str, Any]]:
    """List actual August daily Vision objects; never infer missing days by URL."""
    prefix = f"data/futures/um/daily/klines/{symbol}/1d/"
    try:
        _, objects, pages = client.list_objects_v2(prefix)
    except Exception as exc:
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", f"August source inventory failed for {symbol}: {exc}") from exc
    stem = f"{symbol}-1d-2026-08-"
    rows: list[dict[str, Any]] = []
    for obj in objects:
        name = Path(obj.key).name
        if not (name.startswith(stem) and name.endswith(".zip")):
            continue
        day_text = name[len(stem):-4]
        if not day_text.isdigit() or not 1 <= int(day_text) <= 31:
            continue
        rows.append({"market": "um", "symbol": symbol, "archive_month": "2026-08", "interval": "1d", "cadence": "daily", "source_day": int(day_text), "object_key": obj.key, "object_size": obj.size, "object_etag": obj.etag, "listing_pages": pages, "source_mode": "DAILY_ARCHIVE_FALLBACK", "discovery_status": "DISCOVERED"})
    return sorted(rows, key=lambda row: int(row["source_day"]))


def _build_august_source_inventory(taxonomy: Any, listed: Any, client: Any) -> dict[str, Any]:
    """Separate historical taxonomy from actual August-discovered objects."""
    import pandas as pd
    um_taxonomy = taxonomy[taxonomy["market"].astype(str).str.lower().eq("um")].copy() if "market" in taxonomy.columns else pd.DataFrame()
    if um_taxonomy.empty or "symbol" not in um_taxonomy:
        historical = set()
    elif "primary_crypto_eligible" in um_taxonomy:
        primary = um_taxonomy["primary_crypto_eligible"].astype(str).str.lower().isin({"true", "1", "yes"})
        historical = set(um_taxonomy.loc[primary, "symbol"].astype(str).str.upper())
    else:
        historical = set(um_taxonomy["symbol"].astype(str).str.upper())
    monthly = listed[(listed["market"].astype(str).str.lower() == "um") & listed["archive_month"].astype(str).eq("2026-08")].copy() if {"market", "archive_month", "symbol"}.issubset(listed.columns) else pd.DataFrame()
    monthly = monthly.drop_duplicates(subset=["symbol", "archive_month"])
    monthly_symbols = set(monthly["symbol"].astype(str).str.upper())
    objects: list[dict[str, Any]] = []
    objects.extend({**row, "source_mode": "MONTHLY_ARCHIVE", "discovery_status": "DISCOVERED", "cadence": "monthly", "object_key": row.get("key", ""), "object_size": row.get("size", ""), "object_etag": row.get("etag", "")} for row in monthly.to_dict(orient="records"))
    for symbol in sorted(historical - monthly_symbols):
        objects.extend(_august_daily_inventory(client, symbol))
    discovered = {str(row["symbol"]).upper() for row in objects}
    return {"status": "PASS", "market": "um", "dataset": "klines", "interval": "1d", "month": "2026-08", "historical_taxonomy_symbols": sorted(historical), "historical_taxonomy_symbol_count": len(historical), "discovered_symbols": sorted(discovered), "august_discovered_symbol_count": len(discovered), "no_august_historical_symbols": sorted(historical - discovered), "no_august_historical_symbol_count": len(historical - discovered), "discovered_objects": objects}


def _download_discovered_daily(ctx: Mapping[str, Any], *, raw_root: Path, inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from binance_research.data import ArchiveRequest, BinanceArchiveClient
    client = BinanceArchiveClient(raw_root, timeout=90, max_retries=3)
    rows: list[dict[str, Any]] = []
    for item in inventory:
        request = ArchiveRequest("um", "klines", str(item["symbol"]), 2026, 8, interval="1d", cadence="daily", day=int(item["source_day"]))
        try:
            path, manifest = client.download(request)
        except Exception as exc:
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", f"discovered daily object retrieval failed for {item['symbol']} day {item['source_day']}: {exc}") from exc
        rows.append({**item, "raw_path": str(path), "published_sha256": manifest.published_sha256, "computed_sha256": manifest.computed_sha256, "integrity_status": "PASS" if not manifest.issues else "ISSUES", "retrieved_at_utc": manifest.downloaded_at})
    return rows


def _acquire_august_source(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    """Discover and acquire only actual August UM 1d objects."""
    import pandas as pd
    from scripts.build_r16_1d_universe import acquire_1d, census_1d
    from binance_research.data import BinanceArchiveClient
    census_dir = Path(ctx.get("census_dir", REPO_ROOT / "data/census/r1_full_history_v1"))
    raw_root = Path(ctx.get("raw_root", REPO_ROOT / "data/raw"))
    out = Path(ctx["control_root"]) / "august_source"
    out.mkdir(parents=True, exist_ok=True)
    taxonomy, listed = census_1d(census_dir, out / "census", workers=2)
    inventory = _build_august_source_inventory(taxonomy, listed, BinanceArchiveClient(raw_root, timeout=90, max_retries=3))
    inventory_path = out / "august_2026_source_inventory.json"
    inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monthly = pd.DataFrame([row for row in inventory["discovered_objects"] if row["source_mode"] == "MONTHLY_ARCHIVE"])
    daily = [row for row in inventory["discovered_objects"] if row["source_mode"] == "DAILY_ARCHIVE_FALLBACK"]
    frames: list[pd.DataFrame] = []
    if not monthly.empty:
        acquired = acquire_1d(monthly[["market", "symbol", "archive_month"]], workers=2, raw_root=raw_root)
        acquired["source_mode"] = "MONTHLY_ARCHIVE"
        frames.append(acquired)
        if acquired.loc[acquired["integrity_status"].astype(str).eq("ERROR")].shape[0]:
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "authoritative monthly object retrieval failed")
    if daily:
        frames.append(pd.DataFrame(_download_discovered_daily(ctx, raw_root=raw_root, inventory=daily)))
    columns = ["market", "symbol", "archive_month", "raw_path", "published_sha256", "computed_sha256", "integrity_status", "source_mode", "source_day", "retrieved_at_utc"]
    acquired = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)
    for column in columns:
        if column not in acquired:
            acquired[column] = None
    acquired.to_csv(out / "august_2026_acquisition.csv", index=False)
    return {"manifest_path": str((out / "august_2026_acquisition.csv").resolve()), "manifest_sha256": hashlib.sha256((out / "august_2026_acquisition.csv").read_bytes()).hexdigest(), "inventory_path": str(inventory_path.resolve()), "inventory_sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(), "historical_taxonomy_symbol_count": inventory["historical_taxonomy_symbol_count"], "august_discovered_symbol_count": inventory["august_discovered_symbol_count"], "no_august_historical_symbol_count": inventory["no_august_historical_symbol_count"], "source_integrity_blocker_count": 0, "source_mode": "MONTHLY_ARCHIVE" if not daily else "MONTHLY_ARCHIVE_AND_DAILY_ARCHIVE_FALLBACK"}


def _verify_august_source(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    import pandas as pd
    from binance_research.data import load_kline_archive, validate_klines
    acquisition = ctx["AUGUST_SOURCE_ACQUISITION"]
    manifest_path = Path(acquisition["manifest_path"])
    frame = pd.read_csv(manifest_path)
    required = {"market", "symbol", "archive_month", "integrity_status", "published_sha256", "computed_sha256", "raw_path"}
    if not required.issubset(frame.columns):
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "acquisition manifest lacks integrity columns")
    inventory_path = Path(str(acquisition.get("inventory_path", manifest_path.with_name("august_2026_source_inventory.json"))))
    if not inventory_path.is_file():
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source inventory is missing")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("status") != "PASS" or inventory.get("market") != "um" or inventory.get("month") != "2026-08":
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source inventory is not authoritative")
    for item in inventory.get("discovered_objects", []):
        if str(item.get("market", "")).lower() != "um" or str(item.get("archive_month", "")) != "2026-08":
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source inventory contains an unexpected market or month")
        if str(item.get("source_mode", "")) not in {"MONTHLY_ARCHIVE", "DAILY_ARCHIVE_FALLBACK"}:
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source inventory contains an unknown source mode")
    discovered_symbols = {str(symbol).upper() for symbol in inventory.get("discovered_symbols", [])}
    discovered_object_symbols = {str(item.get("symbol", "")).upper() for item in inventory.get("discovered_objects", [])}
    historical_symbols = {str(symbol).upper() for symbol in inventory.get("historical_taxonomy_symbols", [])}
    if discovered_object_symbols != discovered_symbols:
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source inventory symbol set does not match discovered objects")
    if frame.empty:
        if discovered_symbols:
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "discovered August objects have no acquisition manifest rows")
        return _write_august_verification_receipt(ctx, frame, inventory, [], set(), historical_symbols, inventory_path)
    manifest_symbols = {str(symbol).upper() for symbol in frame["symbol"].dropna()}
    missing_discovered = discovered_symbols - manifest_symbols
    if missing_discovered:
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", f"discovered August symbols missing from acquisition manifest: {sorted(missing_discovered)}")
    valid = frame["market"].astype(str).str.lower().eq("um") & frame["archive_month"].astype(str).eq("2026-08") & frame["integrity_status"].astype(str).eq("PASS") & frame["published_sha256"].astype(str).eq(frame["computed_sha256"].astype(str))
    if not bool(valid.all()):
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source failed UM/1d/checksum metadata verification")
    if frame["archive_month"].astype(str).str.contains("2026-09").any():
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "September observation entered August source")
    expected_days = set(pd.date_range("2026-08-01", "2026-08-31", freq="D", tz="UTC"))
    verified_inputs: list[dict[str, Any]] = []
    grouped_days: dict[str, set[pd.Timestamp]] = {}
    for record in frame.to_dict(orient="records"):
        path = Path(str(record["raw_path"]))
        if not path.is_file():
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", f"missing source archive: {path}")
        actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha != str(record["computed_sha256"]) or actual_sha != str(record["published_sha256"]):
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", f"source checksum mismatch: {path}")
        try:
            candles = load_kline_archive(path)
            issues = [issue for issue in validate_klines(candles, "1d") if issue.severity == "ERROR"]
        except Exception as exc:
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", f"malformed source archive: {path}") from exc
        if candles.empty:
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", f"empty source archive: {path}")
        if issues:
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", f"invalid OHLCV/grid in {path}")
        days = set(pd.to_datetime(candles["open_time"], utc=True).dt.floor("D"))
        if any(day not in expected_days for day in days) or len(days) != len(candles):
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", f"duplicate or non-August candle in {path}")
        symbol = str(record["symbol"]).upper()
        if symbol not in discovered_symbols:
            raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", f"acquired symbol was not in discovered August inventory: {symbol}")
        grouped_days.setdefault(symbol, set()).update(days)
        verified_inputs.append({"symbol": symbol, "path": str(path), "sha256": actual_sha, "rows": int(len(candles)), "first_day": min(days).isoformat(), "last_day": max(days).isoformat(), "source_mode": str(record.get("source_mode", "MONTHLY_ARCHIVE"))})
    complete_symbols = {symbol for symbol, days in grouped_days.items() if days == expected_days}
    partial_symbols = set(grouped_days) - complete_symbols
    complete_inputs = [item for item in verified_inputs if item["symbol"] in complete_symbols]
    return _write_august_verification_receipt(ctx, frame, inventory, complete_inputs, partial_symbols, historical_symbols, inventory_path, discovered_symbols=discovered_symbols, grouped_days=grouped_days)


def _write_august_verification_receipt(ctx: Mapping[str, Any], frame: Any, inventory: Mapping[str, Any], verified_inputs: list[dict[str, Any]], partial_symbols: set[str], historical_symbols: set[str], inventory_path: Path, *, discovered_symbols: set[str] | None = None, grouped_days: Mapping[str, set[Any]] | None = None) -> Mapping[str, Any]:
    discovered_symbols = discovered_symbols if discovered_symbols is not None else {str(symbol).upper() for symbol in inventory.get("discovered_symbols", [])}
    grouped_days = grouped_days or {}
    complete_symbols = {str(item["symbol"]).upper() for item in verified_inputs}
    partial_symbols = {str(symbol).upper() for symbol in partial_symbols}
    semantic_sha = _digest({"month": "2026-08", "inputs": verified_inputs, "discovered_symbols": sorted(discovered_symbols), "partial_symbols": sorted(partial_symbols)})
    receipt = Path(ctx["control_root"]) / "R3_AUGUST_2026_SOURCE_VERIFICATION_RECEIPT.json"
    source_mode_by_symbol = {symbol: sorted({str(item.get("source_mode", "MONTHLY_ARCHIVE")) for item in verified_inputs if item["symbol"] == symbol}) for symbol in sorted(complete_symbols | partial_symbols)}
    source_coverage_by_symbol = {}
    no_august_symbols = historical_symbols - discovered_symbols
    for symbol in sorted(discovered_symbols):
        observed_day_count = len(grouped_days.get(symbol, set()))
        source_coverage_by_symbol[symbol] = {
            "source_mode": source_mode_by_symbol.get(symbol, []),
            "observed_day_count": observed_day_count,
            "expected_day_count": 31,
            "coverage_ratio": observed_day_count / 31,
            "integrity_state": "PASS" if symbol in complete_symbols or symbol in partial_symbols else "NOT_ACQUIRED",
            "eligibility_state": "ELIGIBLE_COMPLETE_PRIOR_MONTH" if symbol in complete_symbols else "INELIGIBLE_INCOMPLETE_PRIOR_MONTH",
            "ranking_state": "ELIGIBLE" if symbol in complete_symbols else "EXCLUDED",
        }
    for symbol in sorted(no_august_symbols):
        source_coverage_by_symbol[symbol] = {
            "source_mode": [],
            "observed_day_count": 0,
            "expected_day_count": 31,
            "coverage_ratio": 0.0,
            "integrity_state": "NOT_DISCOVERED",
            "eligibility_state": "NO_AUGUST_HISTORICAL_SOURCE",
            "ranking_state": "EXCLUDED",
        }
    payload = {"status": "PASS", "market": "um", "dataset": "klines", "interval": "1d", "month": "2026-08", "rows": int(frame.shape[0]), "manifest_path": str(Path(ctx["AUGUST_SOURCE_ACQUISITION"]["manifest_path"]).resolve()), "manifest_sha256": hashlib.sha256(Path(ctx["AUGUST_SOURCE_ACQUISITION"]["manifest_path"]).read_bytes()).hexdigest(), "inventory_path": str(inventory_path.resolve()), "inventory_sha256": hashlib.sha256(inventory_path.read_bytes()).hexdigest(), "verified_source_semantic_sha256": semantic_sha, "historical_taxonomy_symbol_count": int(inventory.get("historical_taxonomy_symbol_count", len(historical_symbols))), "august_discovered_symbol_count": int(len(discovered_symbols)), "complete_august_eligible_symbol_count": int(len(complete_symbols)), "partial_august_symbol_count": int(len(partial_symbols)), "no_august_historical_symbol_count": int(len(historical_symbols - discovered_symbols)), "source_integrity_blocker_count": 0, "expected_symbols": sorted(complete_symbols), "verified_symbols": sorted(complete_symbols), "discovered_symbols": sorted(discovered_symbols), "partial_symbols": sorted(partial_symbols), "missing_symbols": [], "extra_symbols": [], "source_mode_by_symbol": source_mode_by_symbol, "source_coverage_by_symbol": source_coverage_by_symbol, "verified_inputs": verified_inputs}
    if receipt.exists():
        prior = json.loads(receipt.read_text(encoding="utf-8"))
        if prior != payload:
            raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", "August verification receipt changed on replay")
        return {"receipt_path": str(receipt.resolve()), "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(), "verified_source_semantic_sha256": semantic_sha, "rows": int(frame.shape[0]), "manifest_path": str(Path(ctx["AUGUST_SOURCE_ACQUISITION"]["manifest_path"]).resolve())}
    receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"receipt_path": str(receipt.resolve()), "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(), "verified_source_semantic_sha256": semantic_sha, "rows": int(frame.shape[0]), "manifest_path": str(Path(ctx["AUGUST_SOURCE_ACQUISITION"]["manifest_path"]).resolve())}


def _build_september_ranking(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    from scripts.qualify_r3_forward_ranking import build_forward_ranking_from_verified_source, ranking_semantic_sha256
    output = Path(ctx["control_root"]) / "ranking"
    receipt_path = Path(ctx.get("AUGUST_SOURCE_VERIFICATION", {}).get("receipt_path", ""))
    if not receipt_path.is_file():
        raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_RANKING", "ranking requires verified August source receipt")
    ranked = build_forward_ranking_from_verified_source(receipt_path, Path(ctx.get("census_dir", REPO_ROOT / "data/census/r1_full_history_v1")), output, effective_month="2026-09")
    frame = __import__("pandas").read_csv(ranked)
    if not frame["volume_month"].astype(str).eq("2026-08").all() or not frame["universe_month"].astype(str).eq("2026-09").all():
        raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_RANKING", "ranking month contract mismatch")
    return {"artifact_path": str(ranked.resolve()), "artifact_sha256": hashlib.sha256(ranked.read_bytes()).hexdigest(), "semantic_sha256": ranking_semantic_sha256(frame, effective_month="2026-09", selected_only=False), "candidate_count": int(len(frame)), "eligible_count": int(frame["rank"].notna().sum())}


def _source_tree_sha256() -> str:
    root = Path(__file__).resolve().parents[1]
    files: list[Path] = []
    for directory in ("scripts", "src", "tests", "configs"):
        base = root / directory
        if base.exists():
            files.extend(path for path in base.rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode()); digest.update(b"\0"); digest.update(path.read_bytes())
    return digest.hexdigest()


def _registry_identity() -> str:
    path = REPO_ROOT / "campaigns/r3_prospective_context_v1/trial_registry.csv"
    if not path.is_file():
        raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", "frozen trial registry is missing")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_REGISTRY_SHA256:
        raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", "trial registry SHA does not match frozen identity")
    return digest


def _freeze_september_roster(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    from binance_research.r3_universe import build_causal_monthly_roster, write_roster_artifact
    ranking = Path(ctx["SEPTEMBER_RANKING"]["artifact_path"])
    destination = Path(ctx.get("roster_path", REPO_ROOT / "campaigns/r3_prospective_context_v1/rosters/2026-09.json"))
    roster = build_causal_monthly_roster(ranking, effective_month="2026-09")
    if destination.exists():
        try:
            from binance_research.r3_universe import replay_roster_artifact
            existing_roster = replay_roster_artifact(destination, effective_month="2026-09")
        except Exception as exc:
            raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_ROSTER", f"invalid existing roster: {exc}") from exc
        if existing_roster.roster_sha256 != roster.roster_sha256:
            raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_ROSTER", "existing roster conflicts with ranking")
        return {"roster_path": str(destination.resolve()), "roster_file_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "roster_sha256": existing_roster.roster_sha256, "symbols": list(existing_roster.symbols), "symbol_count": len(existing_roster.symbols), "effective_month": existing_roster.effective_month, "reused": True}
    write_roster_artifact(roster, destination, source_path=ranking)
    return {"roster_path": str(destination.resolve()), "roster_file_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "roster_sha256": roster.roster_sha256, "symbols": list(roster.symbols), "symbol_count": len(roster.symbols), "effective_month": roster.effective_month}


def _replay_september_roster(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    from binance_research.r3_universe import replay_roster_artifact
    roster = replay_roster_artifact(Path(ctx["SEPTEMBER_ROSTER_FREEZE"]["roster_path"]), effective_month="2026-09")
    return {"roster_sha256": roster.roster_sha256, "symbols": len(roster.symbols), "replayed": True}


def _run_september_shadow(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    from binance_research.r3_operations import verify_engineering_shadow_root
    from scripts.run_r3_prospective_collector import run_engineering_shadow_forever
    root = Path(ctx.get("shadow_root", SHADOW_ROOT))
    roster_path = Path(ctx["SEPTEMBER_ROSTER_FREEZE"]["roster_path"])
    result = run_engineering_shadow_forever(root, roster_path, max_cycles=1, wait_for_boundary=True)
    verified = verify_engineering_shadow_root(root, expected_symbols=list(ctx["SEPTEMBER_ROSTER_FREEZE"].get("symbols", [])), roster_sha256=ctx["SEPTEMBER_ROSTER_FREEZE"]["roster_sha256"])
    return {"root": str(root), "cycles": int(result["cycles"]), "verified": verified}


def _freeze_launch_identity(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "scripts", "src", "tests", "configs"], capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", "scientific source scope is dirty")
    implementation = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    registry = _registry_identity()
    contract_dir = REPO_ROOT / "campaigns/r3_prospective_context_v1"
    contracts = {name: hashlib.sha256((contract_dir / filename).read_bytes()).hexdigest() for name, filename in {"data_contract_sha256": "data_contract.md", "source_dependency_matrix_sha256": "R3_SOURCE_DEPENDENCY_MATRIX.json", "collection_contract_sha256": "collection_contract.md", "feature_semantics_sha256": "feature_semantics.md", "clock_contract_sha256": "R3_CLOCK_CONTRACT.md", "universe_contract_sha256": "universe_contract.md", "metrics_contract_sha256": "metrics_contract.md", "multiple_testing_plan_sha256": "multiple_testing_plan.md", "promotion_policy_sha256": "promotion_policy.md"}.items()}
    verification = ctx["AUGUST_SOURCE_VERIFICATION"]
    ranking = ctx["SEPTEMBER_RANKING"]
    roster = ctx["SEPTEMBER_ROSTER_FREEZE"]
    shadow = ctx["SEPTEMBER_ENGINEERING_SHADOW"]
    return {"implementation_commit": implementation, "source_tree_sha256": _source_tree_sha256(), "registry_sha256": registry, "roster_sha256": ctx["SEPTEMBER_ROSTER_REPLAY"]["roster_sha256"], "roster_file_sha256": roster.get("roster_file_sha256", ""), "august_verification_receipt_sha256": verification.get("receipt_sha256", ""), "august_verified_source_semantic_sha256": verification.get("verified_source_semantic_sha256", ""), "september_ranking_artifact_sha256": ranking.get("artifact_sha256", ""), "september_ranking_semantic_sha256": ranking.get("semantic_sha256", ""), "september_shadow_root": shadow.get("root", ""), "scientific_root": str(ctx["scientific_root"]), **contracts}


def _build_launch_manifest(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    path = Path(ctx["control_root"]) / "R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json"
    identity = ctx["LAUNCH_IDENTITY_FREEZE"]
    body = {"campaign_id": "r3_prospective_context_v1", "status": "R3_READY_FOR_PROSPECTIVE_LAUNCH", "implementation_commit": identity["implementation_commit"], "source_tree_sha256": identity["source_tree_sha256"], "registry_sha256": identity["registry_sha256"], "roster_sha256": identity["roster_sha256"], "scientific_root": str(ctx["scientific_root"]), "final_holdout": "UNTOUCHED", "r2b2": "NOT_STARTED", "outcomes": "NOT_STARTED", "activation_not_before": ctx["clock"], **{key: value for key, value in identity.items() if key.endswith("_sha256") and key not in {"source_tree_sha256", "registry_sha256", "roster_sha256"}}}
    body["august_source_verification_receipt_sha256"] = ctx["AUGUST_SOURCE_VERIFICATION"].get("receipt_sha256", "")
    body["september_ranking_artifact_sha256"] = ctx["SEPTEMBER_RANKING"].get("artifact_sha256", "")
    body["september_ranking_semantic_sha256"] = ctx["SEPTEMBER_RANKING"].get("semantic_sha256", "")
    body["september_roster_file_sha256"] = ctx["SEPTEMBER_ROSTER_FREEZE"].get("roster_file_sha256", "")
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"manifest_path": str(path.resolve()), "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **body}


def _build_launch_seal(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    path = Path(ctx["control_root"]) / "R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json"
    manifest_path = Path(ctx["LAUNCH_MANIFEST_BUILD"]["manifest_path"])
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    body = {"status": "SEALED", "manifest_path": str(manifest_path.resolve()), "manifest_sha256": manifest_sha, "implementation_commit": ctx["LAUNCH_IDENTITY_FREEZE"]["implementation_commit"], "roster_sha256": ctx["SEPTEMBER_ROSTER_REPLAY"]["roster_sha256"], "sealed_at_utc": datetime.now(UTC).isoformat(), "scientific_activation_not_before": ctx["clock"]}
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(body, indent=2, sort_keys=True) + "\n"); handle.flush(); os.fsync(handle.fileno())
    return {"seal_path": str(path.resolve()), "seal_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "manifest_path": str(manifest_path.resolve()), "manifest_sha256": manifest_sha, "status": "SEALED"}


def _activate_scientific(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    launcher = ctx.get("collector_launcher")
    if not callable(launcher):
        raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", "collector launcher/supervisor adapter is not configured")
    result = launcher(ctx)
    if not isinstance(result, Mapping) or int(result.get("cycles_completed", 0)) < 1 or result.get("manifest_chain_pass") is not True or result.get("health_pass") is not True:
        raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", "activation requires one verified scientific cycle")
    evidence = dict(result)
    control_root = ctx.get("control_root")
    if control_root:
        receipt_path = Path(str(control_root)) / "R3_PROSPECTIVE_COLLECTION_ACTIVATION_RECEIPT.json"
        payload = {"status": "ACTIVE", "activated_at_utc": datetime.now(UTC).isoformat(), **evidence}
        with receipt_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n"); handle.flush(); os.fsync(handle.fileno())
        evidence["activation_receipt"] = str(receipt_path.resolve())
    return evidence


def _probe_scientific_evidence(process: Any, root: Path, *, manifest_path: Path | None = None, seal_path: Path | None = None, roster_sha256: str | None = None) -> Mapping[str, Any]:
    """Verify actual scientific cycle, health, chain, and launch authorization."""
    if getattr(process, "poll", lambda: None)() is not None:
        return {"cycles_completed": 0, "manifest_chain_pass": False, "health_pass": False}
    chain = root / "raw_v1" / "manifest_chain.jsonl"
    health_path = root / "health" / "health_receipts.jsonl"
    if not chain.is_file() or not verify_manifest_chain(chain) or not health_path.is_file():
        return {"cycles_completed": 0, "manifest_chain_pass": False, "health_pass": False}
    lines = [line for line in health_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    try:
        health = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        return {"cycles_completed": 0, "manifest_chain_pass": True, "health_pass": False}
    if health.get("evidence_mode") != "SCIENTIFIC" or (roster_sha256 and health.get("roster_sha256") != roster_sha256):
        return {"cycles_completed": 0, "manifest_chain_pass": True, "health_pass": False, "evidence_mode": health.get("evidence_mode")}
    latest = json.loads([line for line in chain.read_text(encoding="utf-8").splitlines() if line.strip()][-1])
    if latest.get("manifest_sha256") != health.get("manifest_sha256"):
        return {"cycles_completed": 0, "manifest_chain_pass": True, "health_pass": False}
    cycle_count = 0
    for path in (root / "raw_v1").rglob("*.jsonl"):
        if path.name == "manifest_chain.jsonl":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                continue
            if envelope.get("evidence_mode") != "SCIENTIFIC":
                return {"cycles_completed": 0, "manifest_chain_pass": True, "health_pass": False, "evidence_mode": envelope.get("evidence_mode")}
            cycle_count += int(envelope.get("stream") == "cycle_metadata")
    if cycle_count < 1:
        return {"cycles_completed": 0, "manifest_chain_pass": True, "health_pass": False, "evidence_mode": "SCIENTIFIC"}
    if manifest_path is not None and seal_path is not None and roster_sha256:
        try:
            verify_launch_seal(seal_path, manifest_path, roster_sha256=roster_sha256, scientific_root=root)
        except Exception:
            return {"cycles_completed": cycle_count, "manifest_chain_pass": True, "health_pass": False, "evidence_mode": "SCIENTIFIC"}
    return {"cycles_completed": cycle_count, "manifest_chain_pass": True, "health_pass": True, "evidence_mode": "SCIENTIFIC", "manifest_sha256": latest.get("manifest_sha256"), "roster_sha256": health.get("roster_sha256")}


def supervise_scientific_process(command: list[str], *, scientific_root: Path, control_root: Path, timeout_seconds: float = 60.0, popen: Callable[..., Any] = subprocess.Popen, probe: Callable[[Any, Path], Mapping[str, Any]] | None = None, manifest_path: Path | None = None, seal_path: Path | None = None, roster_sha256: str | None = None) -> Mapping[str, Any]:
    """Launch a collector child and require evidence of its first cycle."""
    process = popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid_path = Path(control_root) / "scientific_collector.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(getattr(process, "pid", "unknown")), encoding="utf-8")
    check = probe or (lambda proc, root: _probe_scientific_evidence(proc, root, manifest_path=manifest_path, seal_path=seal_path, roster_sha256=roster_sha256))
    deadline = datetime.now(UTC).timestamp() + timeout_seconds
    try:
        while datetime.now(UTC).timestamp() < deadline:
            evidence = check(process, Path(scientific_root))
            if isinstance(evidence, Mapping) and int(evidence.get("cycles_completed", 0)) >= 1 and evidence.get("manifest_chain_pass") is True and evidence.get("health_pass") is True:
                return {**dict(evidence), "pid": getattr(process, "pid", None), "supervisor_status": "RUNNING"}
            if getattr(process, "poll", lambda: None)() is not None:
                break
            import time
            time.sleep(0.2)
    finally:
        pid_path.unlink(missing_ok=True)
    if getattr(process, "poll", lambda: None)() is None and hasattr(process, "terminate"):
        process.terminate()
    raise PostBoundaryBlocked("R3_BLOCKED_LAUNCH_IDENTITY", "collector did not produce a verified scientific cycle before supervisor timeout")


def execute_post_boundary(*, clock: CalibratedClock, scientific_root: Path = SCIENTIFIC_ROOT, control_root: Path = CONTROL_ROOT, receipt_root: Path | None = None, callbacks: Mapping[str, StageCallback] | None = None, initial_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Run all launch stages after the calibrated boundary.

    The temporal gate is first, so pre-boundary calls create no files and invoke
    no callback. All external work is represented by proof-producing callbacks.
    """
    require_calibrated_boundary(clock)
    root = Path(scientific_root)
    control = Path(receipt_root) if receipt_root is not None else require_control_root(control_root)
    if receipt_root is not None:
        control = require_control_root(control)
    defaults: dict[str, StageCallback] = {
        "AUGUST_SOURCE_ACQUISITION": _default_blocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source acquisition proof required"),
        "AUGUST_SOURCE_VERIFICATION": _default_blocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source verification proof required"),
        "SEPTEMBER_RANKING": _default_blocked("R3_BLOCKED_SEPTEMBER_RANKING", "September ranking proof required"),
        "SEPTEMBER_ROSTER_FREEZE": _default_blocked("R3_BLOCKED_SEPTEMBER_ROSTER", "September roster freeze proof required"),
        "SEPTEMBER_ROSTER_REPLAY": _default_blocked("R3_BLOCKED_SEPTEMBER_ROSTER", "September roster replay proof required"),
        "SEPTEMBER_ENGINEERING_SHADOW": _default_blocked("R3_BLOCKED_SEPTEMBER_SHADOW", "September shadow proof required"),
        "LAUNCH_IDENTITY_FREEZE": _default_blocked("R3_BLOCKED_LAUNCH_IDENTITY", "launch identity proof required"),
        "LAUNCH_MANIFEST_BUILD": _default_blocked("R3_BLOCKED_LAUNCH_IDENTITY", "fresh launch manifest proof required"),
        "LAUNCH_SEAL": _default_blocked("R3_BLOCKED_LAUNCH_IDENTITY", "launch seal proof required"),
        "SCIENTIFIC_ROOT_GATE": lambda _: {"root": str(require_fresh_scientific_root(root)), "fresh": True},
        "SCIENTIFIC_ACTIVATION": _default_blocked("R3_BLOCKED_LAUNCH_IDENTITY", "scientific activation proof required"),
    }
    defaults.update(build_project_production_callbacks() if callbacks is None else dict(callbacks))
    context: dict[str, Any] = {"clock": clock.server_time.isoformat(), "scientific_root": str(root), "control_root": str(control)}
    context.update(dict(initial_context or {}))
    out = [_write_stage_receipt(control, "TEMPORAL_GATE", {"server_time": clock.server_time.isoformat(), "uncertainty_ms": clock.uncertainty_ms})]
    for stage, callback in defaults.items():
        result = _run_stage(stage, callback, context, control)
        out.append(result)
        context[stage] = result["proof"]
    return {"status": "R3_READY_FOR_PROSPECTIVE_LAUNCH", "scientific_root": str(root), "receipts": out, "execute": True}


def rollover_state(*, now: datetime, september_end: datetime = datetime(2026, 10, 1, tzinfo=UTC), has_next_roster: bool) -> str:
    if now.astimezone(UTC) >= september_end.astimezone(UTC) and not has_next_roster:
        return "UNIVERSE_ROLLOVER_GAP"
    return "ACTIVE"


def prepare_post_boundary_plan(*, now: datetime, scientific_root: Path = SCIENTIFIC_ROOT) -> dict[str, object]:
    require_boundary(now)
    root = require_fresh_scientific_root(scientific_root)
    return {"status": "POST_BOUNDARY_EXECUTOR_READY", "boundary_utc": BOUNDARY_UTC.isoformat().replace("+00:00", "Z"), "scientific_root": str(root), "steps": ["TEMPORAL_GATE", "AUGUST_SOURCE_ACQUISITION", "AUGUST_SOURCE_VERIFICATION", "SEPTEMBER_RANKING", "build_september_liquidity_ranking", "SEPTEMBER_ROSTER_FREEZE", "SEPTEMBER_ROSTER_REPLAY", "SEPTEMBER_ENGINEERING_SHADOW", "LAUNCH_IDENTITY_FREEZE", "LAUNCH_MANIFEST_BUILD", "LAUNCH_SEAL", "SCIENTIFIC_ROOT_GATE", "SCIENTIFIC_ACTIVATION"], "execute": False, "outcomes": "NOT_STARTED", "final_holdout": "UNTOUCHED", "r2b2": "NOT_STARTED"}


def _production_clock() -> CalibratedClock:
    """Calibrate against Binance public server time before any launch-stage I/O."""
    from binance_research.data import BinanceRestClient
    from binance_research.r3_timing import calibrated_now
    calibration = BinanceRestClient().calibrate_server_clock("um", sample_count=5)
    current = calibrated_now(datetime.now(UTC), calibration)
    return CalibratedClock(current, calibration.round_trip_ms / 2.0 + 1.0, sample_count=5)


def _import_closure_self_check() -> str:
    """Resolve lazy production imports without network or launch-stage writes."""
    import importlib

    modules = (
        "scripts.build_r16_1d_universe",
        "scripts.qualify_r3_forward_ranking",
        "scripts.run_r3_prospective_collector",
        "binance_research.r3_universe",
        "binance_research.r3_operations",
    )
    for module in modules:
        importlib.import_module(module)
    build_project_production_callbacks()
    return str(REPO_ROOT)


def _production_collector_launcher(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    """Start the qualified persistent collector and supervise its first cycle."""
    command = [sys.executable, str(REPO_ROOT_SCRIPTS / "run_r3_prospective_collector.py"), "--mode", "SCIENTIFIC", "--persistent", "--root", str(ctx["scientific_root"]), "--roster-artifact", str(ctx["SEPTEMBER_ROSTER_FREEZE"]["roster_path"]), "--launch-manifest", str(ctx["LAUNCH_MANIFEST_BUILD"]["manifest_path"])]
    return supervise_scientific_process(command, scientific_root=Path(ctx["scientific_root"]), control_root=Path(ctx["control_root"]), timeout_seconds=float(ctx.get("supervisor_timeout_seconds", 900)), manifest_path=Path(ctx["LAUNCH_MANIFEST_BUILD"]["manifest_path"]), seal_path=Path(ctx.get("LAUNCH_SEAL", {}).get("seal_path", Path(ctx["control_root"]) / "R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json")), roster_sha256=str(ctx["SEPTEMBER_ROSTER_REPLAY"]["roster_sha256"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrated, fail-closed R3 post-boundary executor")
    parser.add_argument("--execute-production", action="store_true")
    parser.add_argument("--self-check-imports", action="store_true")
    parser.add_argument("--control-root", type=Path, default=CONTROL_ROOT)
    parser.add_argument("--scientific-root", type=Path, default=SCIENTIFIC_ROOT)
    parser.add_argument("--raw-root", type=Path, default=REPO_ROOT / "data/raw")
    parser.add_argument("--census-dir", type=Path, default=REPO_ROOT / "data/census/r1_full_history_v1")
    parser.add_argument("--roster-path", type=Path, default=REPO_ROOT / "campaigns/r3_prospective_context_v1/rosters/2026-09.json")
    parser.add_argument("--shadow-root", type=Path, default=SHADOW_ROOT)
    parser.add_argument("--registry-sha256", default="")
    parser.add_argument("--supervisor-timeout-seconds", type=float, default=900.0)
    args = parser.parse_args(argv)
    if args.self_check_imports:
        repo_root = _import_closure_self_check()
        print(json.dumps({"repo_root": repo_root, "imports": "PASS"}, sort_keys=True))
        return 0
    if not args.execute_production:
        raise SystemExit("R3_BLOCKED_SEPTEMBER_ROSTER: use --execute-production after calibrated boundary")
    try:
        clock = _production_clock()
        result = execute_post_boundary(clock=clock, control_root=args.control_root, scientific_root=args.scientific_root, callbacks=None, initial_context={"raw_root": str(args.raw_root), "census_dir": str(args.census_dir), "roster_path": str(args.roster_path), "shadow_root": str(args.shadow_root), "registry_sha256": args.registry_sha256, "supervisor_timeout_seconds": args.supervisor_timeout_seconds, "collector_launcher": _production_collector_launcher})
    except PostBoundaryBlocked as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"R3_BLOCKED_CLOCK_CAUSALITY: Binance clock calibration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
