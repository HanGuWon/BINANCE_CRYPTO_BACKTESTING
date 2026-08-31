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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

BOUNDARY_UTC = datetime(2026, 9, 1, tzinfo=UTC)
SCIENTIFIC_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v1")
CONTROL_ROOT = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09")
MAX_CLOCK_UNCERTAINTY_MS = 2_000


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "server_time", self.server_time.astimezone(UTC))


StageCallback = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def require_calibrated_boundary(clock: CalibratedClock) -> None:
    if clock.uncertainty_ms > MAX_CLOCK_UNCERTAINTY_MS:
        raise PostBoundaryBlocked("R3_BLOCKED_CLOCK_CAUSALITY", f"Binance clock uncertainty {clock.uncertainty_ms:.3f}ms exceeds {MAX_CLOCK_UNCERTAINTY_MS}ms")
    if clock.server_time < BOUNDARY_UTC:
        raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_ROSTER", f"calibrated Binance time {clock.server_time.isoformat()} is before {BOUNDARY_UTC.isoformat()}")


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
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
        return existing
    try:
        proof = callback(context)
    except PostBoundaryBlocked:
        raise
    except Exception as exc:
        raise PostBoundaryBlocked("R3_BLOCKED_IMPLEMENTATION", f"{stage} callback failed: {exc}") from exc
    if not isinstance(proof, Mapping) or not proof:
        raise PostBoundaryBlocked("R3_BLOCKED_IMPLEMENTATION", f"{stage} returned no proof")
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


def _acquire_august_source(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    """Acquire completed August UM 1d archives through existing R1.6 code."""
    from scripts.build_r16_1d_universe import acquire_1d, census_1d
    census_dir = Path(ctx.get("census_dir", "data/census/r1_full_history_v1"))
    raw_root = Path(ctx.get("raw_root", "data/raw"))
    out = Path(ctx["control_root"]) / "august_source"
    _, listed = census_1d(census_dir, out / "census", workers=2)
    august = listed[listed["archive_month"].astype(str).eq("2026-08")].copy()
    if august.empty:
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "no completed August UM 1d archive candidates")
    acquired = acquire_1d(august, workers=2, raw_root=raw_root)
    acquired.to_csv(out / "august_2026_acquisition.csv", index=False)
    return {"manifest_path": str((out / "august_2026_acquisition.csv").resolve()), "candidate_count": int(len(acquired)), "raw_root": str(raw_root)}


def _verify_august_source(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    import pandas as pd
    manifest_path = Path(ctx["AUGUST_SOURCE_ACQUISITION"]["manifest_path"])
    frame = pd.read_csv(manifest_path)
    required = {"market", "symbol", "archive_month", "integrity_status", "published_sha256", "computed_sha256", "raw_path"}
    if not required.issubset(frame.columns):
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "acquisition manifest lacks integrity columns")
    valid = frame["market"].astype(str).str.lower().eq("um") & frame["archive_month"].astype(str).eq("2026-08") & frame["integrity_status"].astype(str).eq("PASS") & frame["published_sha256"].astype(str).eq(frame["computed_sha256"].astype(str))
    paths_exist = frame["raw_path"].map(lambda value: Path(str(value)).is_file())
    if not bool((valid & paths_exist).all()) or frame.empty:
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "August source failed UM/1d/checksum/completeness verification")
    if frame["archive_month"].astype(str).str.contains("2026-09").any():
        raise PostBoundaryBlocked("R3_BLOCKED_AUGUST_SOURCE_INCOMPLETE", "September observation entered August source")
    receipt = Path(ctx["control_root"]) / "R3_AUGUST_2026_SOURCE_VERIFICATION_RECEIPT.json"
    payload = {"status": "PASS", "market": "um", "interval": "1d", "month": "2026-08", "rows": int(len(frame)), "manifest_path": str(manifest_path), "retrieved_at_utc": datetime.now(UTC).isoformat()}
    receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"receipt_path": str(receipt.resolve()), "rows": int(len(frame)), "manifest_path": str(manifest_path)}


def _build_september_ranking(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    from scripts.qualify_r3_forward_ranking import build_forward_ranking_from_raw, ranking_semantic_sha256
    output = Path(ctx["control_root"]) / "ranking"
    ranked = build_forward_ranking_from_raw(Path(ctx.get("raw_root", "data/raw")), Path(ctx.get("census_dir", "data/census/r1_full_history_v1")), output, effective_month="2026-09")
    frame = __import__("pandas").read_csv(ranked)
    if not frame["volume_month"].astype(str).eq("2026-08").all() or not frame["universe_month"].astype(str).eq("2026-09").all():
        raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_RANKING", "ranking month contract mismatch")
    return {"artifact_path": str(ranked.resolve()), "artifact_sha256": hashlib.sha256(ranked.read_bytes()).hexdigest(), "semantic_sha256": ranking_semantic_sha256(frame, effective_month="2026-09", selected_only=False), "candidate_count": int(len(frame)), "eligible_count": int(frame["rank"].notna().sum())}


def _freeze_september_roster(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    from binance_research.r3_universe import build_causal_monthly_roster, write_roster_artifact
    ranking = Path(ctx["SEPTEMBER_RANKING"]["artifact_path"])
    destination = Path(ctx.get("roster_path", "campaigns/r3_prospective_context_v1/rosters/2026-09.json"))
    roster = build_causal_monthly_roster(ranking, effective_month="2026-09")
    if destination.exists():
        try:
            from binance_research.r3_universe import replay_roster_artifact
            existing_roster = replay_roster_artifact(destination, effective_month="2026-09")
        except Exception as exc:
            raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_ROSTER", f"invalid existing roster: {exc}") from exc
        if existing_roster.roster_sha256 != roster.roster_sha256:
            raise PostBoundaryBlocked("R3_BLOCKED_SEPTEMBER_ROSTER", "existing roster conflicts with ranking")
        return {"roster_path": str(destination.resolve()), "roster_sha256": existing_roster.roster_sha256, "symbols": list(existing_roster.symbols), "symbol_count": len(existing_roster.symbols), "effective_month": existing_roster.effective_month, "reused": True}
    write_roster_artifact(roster, destination, source_path=ranking)
    return {"roster_path": str(destination.resolve()), "roster_sha256": roster.roster_sha256, "symbols": list(roster.symbols), "symbol_count": len(roster.symbols), "effective_month": roster.effective_month}


def _replay_september_roster(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    from binance_research.r3_universe import replay_roster_artifact
    roster = replay_roster_artifact(Path(ctx["SEPTEMBER_ROSTER_FREEZE"]["roster_path"]), effective_month="2026-09")
    return {"roster_sha256": roster.roster_sha256, "symbols": len(roster.symbols), "replayed": True}


def _run_september_shadow(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    from binance_research.r3_operations import verify_engineering_shadow_root
    from scripts.run_r3_prospective_collector import run_engineering_shadow_forever
    root = Path(ctx.get("shadow_root", Path(ctx["control_root"]) / "engineering_shadow_september_launch_v1"))
    roster_path = Path(ctx["SEPTEMBER_ROSTER_FREEZE"]["roster_path"])
    result = run_engineering_shadow_forever(root, roster_path, max_cycles=1, wait_for_boundary=True)
    verified = verify_engineering_shadow_root(root, expected_symbols=list(ctx["SEPTEMBER_ROSTER_FREEZE"].get("symbols", [])), roster_sha256=ctx["SEPTEMBER_ROSTER_FREEZE"]["roster_sha256"])
    return {"root": str(root), "cycles": int(result["cycles"]), "verified": verified}


def _freeze_launch_identity(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    implementation = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    return {"implementation_commit": implementation, "registry_sha256": str(ctx.get("registry_sha256", "")), "roster_sha256": ctx["SEPTEMBER_ROSTER_REPLAY"]["roster_sha256"], "shadow_receipt": ctx.get("SEPTEMBER_ENGINEERING_SHADOW", {}).get("root", "")}


def _build_launch_manifest(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    path = Path(ctx["control_root"]) / "R3_PROSPECTIVE_LAUNCH_MANIFEST_2026-09.json"
    body = {"campaign_id": "r3_prospective_context_v1", "status": "R3_READY_FOR_PROSPECTIVE_LAUNCH", "implementation_commit": ctx["LAUNCH_IDENTITY_FREEZE"]["implementation_commit"], "registry_sha256": ctx["LAUNCH_IDENTITY_FREEZE"].get("registry_sha256", ""), "roster_sha256": ctx["SEPTEMBER_ROSTER_REPLAY"]["roster_sha256"], "scientific_root": str(ctx["scientific_root"]), "final_holdout": "UNTOUCHED", "r2b2": "NOT_STARTED", "outcomes": "NOT_STARTED", "activation_not_before": ctx["clock"]}
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"manifest_path": str(path.resolve()), "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **body}


def _build_launch_seal(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
    path = Path(ctx["control_root"]) / "R3_PROSPECTIVE_LAUNCH_SEAL_RECEIPT.json"
    body = {"status": "SEALED", "manifest_path": ctx["LAUNCH_MANIFEST_BUILD"]["manifest_path"], "manifest_sha256": ctx["LAUNCH_MANIFEST_BUILD"]["manifest_sha256"], "implementation_commit": ctx["LAUNCH_IDENTITY_FREEZE"]["implementation_commit"], "roster_sha256": ctx["SEPTEMBER_ROSTER_REPLAY"]["roster_sha256"], "sealed_at_utc": datetime.now(UTC).isoformat(), "scientific_activation_not_before": ctx["clock"]}
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(body, indent=2, sort_keys=True) + "\n"); handle.flush(); os.fsync(handle.fileno())
    return {"seal_path": str(path.resolve()), "seal_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "status": "SEALED"}


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


def supervise_scientific_process(command: list[str], *, scientific_root: Path, control_root: Path, timeout_seconds: float = 60.0, popen: Callable[..., Any] = subprocess.Popen, probe: Callable[[Any, Path], Mapping[str, Any]] | None = None) -> Mapping[str, Any]:
    """Launch a collector child and require evidence of its first cycle."""
    process = popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid_path = Path(control_root) / "scientific_collector.pid"
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(getattr(process, "pid", "unknown")), encoding="utf-8")
    check = probe or (lambda _process, root: {"cycles_completed": 1, "manifest_chain_pass": (root / "raw_v1" / "manifest_chain.jsonl").is_file(), "health_pass": any(root.glob("health/*")), "evidence_mode": "SCIENTIFIC"})
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
    from binance_research.data import BinanceArchiveClient
    from binance_research.r3_timing import calibrated_now
    calibration = BinanceArchiveClient(Path("data/raw")).calibrate_server_clock("um")
    current = calibrated_now(datetime.now(UTC), calibration)
    return CalibratedClock(current, calibration.round_trip_ms / 2.0 + 1.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrated, fail-closed R3 post-boundary executor")
    parser.add_argument("--execute-production", action="store_true")
    parser.add_argument("--control-root", type=Path, default=CONTROL_ROOT)
    parser.add_argument("--scientific-root", type=Path, default=SCIENTIFIC_ROOT)
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--census-dir", type=Path, default=Path("data/census/r1_full_history_v1"))
    parser.add_argument("--roster-path", type=Path, default=Path("campaigns/r3_prospective_context_v1/rosters/2026-09.json"))
    parser.add_argument("--shadow-root", type=Path, default=Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\engineering_shadow_september_launch_v1"))
    parser.add_argument("--registry-sha256", default="")
    args = parser.parse_args(argv)
    if not args.execute_production:
        raise SystemExit("R3_BLOCKED_SEPTEMBER_ROSTER: use --execute-production after calibrated boundary")
    try:
        clock = _production_clock()
        result = execute_post_boundary(clock=clock, control_root=args.control_root, scientific_root=args.scientific_root, callbacks=None, initial_context={"raw_root": str(args.raw_root), "census_dir": str(args.census_dir), "roster_path": str(args.roster_path), "shadow_root": str(args.shadow_root), "registry_sha256": args.registry_sha256})
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
