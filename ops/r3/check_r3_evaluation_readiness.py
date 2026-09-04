"""Outcome-blind R3 evaluation-readiness gate (V2).

The checker consumes contract and metadata only. It has no dependency on a
materializer, executor, label builder, result store, or historical outcome
artifact. Gap attrition is calculated from explicit timestamped records
mapped to UTC six-hour blocks; aggregate counters without records fail closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "r3-evaluation-readiness-v2"
INVENTORY_RECORD_TYPE = "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_V2"
HORIZON_KEY = "R3_HORIZON_15M_NEXT_NATIVE_BAR_V1"
HORIZON_INTERVAL = "15m"
HORIZON_BARS = 1
PRIMARY_HYPOTHESES = ("R3_H01", "R3_H02", "R3_H03", "R3_H04", "R3_H05", "R3_H06")
MINIMA = {
    "calendar_days": 30,
    "utc_6h_blocks": 120,
    "roster_months": 2,
    "R3_H01": 5_000,
    "R3_H02": 5_000,
    "R3_H03": 1_000,
    "R3_H04": 1_000,
    "R3_H05": 5_000,
    "R3_H06": 5_000,
}
VALID_GAP_CATEGORIES = frozenset({"MISSING_CYCLE", "RESTART_GAP", "SOURCE_UNAVAILABLE", "ROLLOVER_GAP", "INCOMPLETE_BUCKET"})
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROSTER_PATH = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "rosters" / "2026-09.json"

FORBIDDEN_KEY_TOKENS = frozenset({
    "gross_return", "net_return", "future_return", "forward_label", "pnl", "sharpe", "sortino",
    "hit_rate", "win_rate", "mfe", "mae", "candidate_ranking", "performance_metric", "holdout_rows", "r2b2",
})
BROAD_FORBIDDEN_TOKENS = frozenset({"outcome", "return", "pnl", "sharpe", "hit_rate", "future", "holdout", "r2b2"})
ALLOWED_SAFETY_KEYS = frozenset({
    "outcomes_accessed", "outcome_values_accessed", "outcome_analysis_status", "performance_fields_seen",
    "confirmatory_root_accessed", "secondary_campaign_accessed", "final_holdout_status", "final_holdout", "r2b2_status",
})
PATH_KEYS = frozenset({"path", "root", "file", "artifact", "uri", "source"})
FORBIDDEN_PATH_TOKENS = frozenset({"final_holdout", "holdout", "r2b2", "future_return", "gross_return", "net_return", "pnl", "sharpe", "hit_rate", "performance"})
_ROSTER_MONTH_RE = re.compile(r"^(20\d{2}-(?:0[1-9]|1[0-2]))$")


class ReadinessInputError(ValueError):
    """Raised when metadata violates the outcome-blind contract."""


def _normal_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _reject_forbidden(value: Any, *, path: str = "$", parent_key: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normal_key(key)
            if normalized not in ALLOWED_SAFETY_KEYS and (
                normalized in FORBIDDEN_KEY_TOKENS or any(token in normalized for token in BROAD_FORBIDDEN_TOKENS)
            ):
                raise ReadinessInputError(f"forbidden metadata key at {path}.{key}")
            _reject_forbidden(child, path=f"{path}.{key}", parent_key=normalized)
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_forbidden(child, path=f"{path}[{index}]", parent_key=parent_key)
        return
    if isinstance(value, str) and _normal_key(parent_key) in PATH_KEYS:
        lowered = value.replace("\\", "/").lower()
        if any(token in lowered for token in FORBIDDEN_PATH_TOKENS) or any(token in lowered for token in BROAD_FORBIDDEN_TOKENS):
            raise ReadinessInputError(f"forbidden metadata path at {path}")


def _as_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ReadinessInputError(f"{field} must be boolean")
    return value


def _number(mapping: Mapping[str, Any], key: str, default: int = 0) -> int:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReadinessInputError(f"{key} must be numeric")
    if value < 0:
        raise ReadinessInputError(f"{key} must be non-negative")
    return int(value)


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ReadinessInputError(f"{field} must be an ISO-8601 UTC timestamp")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReadinessInputError(f"{field} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ReadinessInputError(f"{field} must be UTC with an explicit offset")
    return parsed.astimezone(timezone.utc)


def _utc_6h_block_id(value: datetime) -> str:
    block = value.replace(hour=(value.hour // 6) * 6, minute=0, second=0, microsecond=0)
    return block.isoformat()


def utc_6h_block_ids_for_gap(start: Any, end: Any = None) -> tuple[str, ...]:
    """Return every UTC six-hour block touched by the closed gap interval."""
    start_dt = _parse_utc(start, "gap.start_time")
    end_dt = start_dt if end in (None, "") else _parse_utc(end, "gap.end_time")
    if end_dt < start_dt:
        raise ReadinessInputError("gap end precedes gap start")
    cursor = start_dt.replace(hour=(start_dt.hour // 6) * 6, minute=0, second=0, microsecond=0)
    last = end_dt.replace(hour=(end_dt.hour // 6) * 6, minute=0, second=0, microsecond=0)
    blocks: list[str] = []
    while cursor <= last:
        blocks.append(cursor.isoformat())
        cursor += timedelta(hours=6)
    return tuple(blocks)


def derive_gap_accounting(inventory: Mapping[str, Any]) -> dict[str, Any]:
    """Validate explicit gap records and derive unique excluded blocks."""
    availability = inventory.get("availability_and_gaps", {})
    if not isinstance(availability, Mapping):
        raise ReadinessInputError("availability_and_gaps must be an object")
    records = availability.get("gap_records", [])
    if not isinstance(records, list):
        raise ReadinessInputError("gap_records must be an explicit list of records")
    excluded: set[str] = set()
    block_reasons: dict[str, set[str]] = {}
    normalized_records: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ReadinessInputError(f"gap_records[{index}] must be an object")
        category = str(record.get("category", "")).strip().upper()
        if category not in VALID_GAP_CATEGORIES:
            raise ReadinessInputError(f"gap_records[{index}] has unknown category")
        start = record.get("start_time", record.get("start"))
        if start is None:
            raise ReadinessInputError(f"gap_records[{index}] has no start_time")
        end = record.get("end_time", record.get("end"))
        block_ids = utc_6h_block_ids_for_gap(start, end)
        normalized_records.append({
            "category": category,
            "start_time": _parse_utc(start, f"gap_records[{index}].start_time").isoformat(),
            "end_time": None if end in (None, "") else _parse_utc(end, f"gap_records[{index}].end_time").isoformat(),
            "utc_6h_block_ids": list(block_ids),
        })
        for block_id in block_ids:
            excluded.add(block_id)
            block_reasons.setdefault(block_id, set()).add(category)

    # Aggregate counters are descriptive only when their explicit records are
    # present. A positive counter without records is an unaccounted gap.
    aggregate = sum(_number(availability, key) for key in (
        "health_gap_count", "health_restart_count", "source_unavailable_records", "rollover_gap_count", "incomplete_bucket_count"
    ))
    cycles = inventory.get("cycles", {})
    if not isinstance(cycles, Mapping):
        raise ReadinessInputError("cycles must be an object")
    aggregate += _number(cycles, "missing_cycle_count")
    streams = inventory.get("streams", {})
    if isinstance(streams, Mapping):
        for stream in streams.values():
            if isinstance(stream, Mapping):
                aggregate += _number(stream, "gap_records") + _number(stream, "source_unavailable_records")
    complete_flag = availability.get("gap_accounting_complete")
    if complete_flag is not True and aggregate > 0:
        raise ReadinessInputError("positive aggregate gap counters require explicit gap_records and gap_accounting_complete=true")
    if complete_flag is False:
        raise ReadinessInputError("gap accounting is marked incomplete")
    if aggregate > 0 and not normalized_records:
        raise ReadinessInputError("aggregate gaps are not represented by explicit records")
    return {
        "complete": True,
        "raw_gap_count": len(normalized_records),
        "aggregate_gap_count": aggregate,
        "excluded_block_ids": sorted(excluded),
        "excluded_block_count": len(excluded),
        "block_reasons": {block: sorted(block_reasons[block]) for block in sorted(block_reasons)},
        "records": normalized_records,
        "rule": "explicit timestamped gaps mapped to each touched UTC_6H block; overlapping gaps count once; no imputation/backfill",
    }


def _effective_counts(inventory: Mapping[str, Any], gap_accounting: Mapping[str, Any] | None = None) -> tuple[dict[str, int], dict[str, int]]:
    availability = inventory.get("availability_and_gaps", {})
    calendar = inventory.get("calendar", {})
    presence = inventory.get("causal_input_presence", {})
    if not isinstance(calendar, Mapping) or not isinstance(presence, Mapping):
        raise ReadinessInputError("calendar and causal_input_presence must be objects")
    definitions = {
        "R3_H01": ("H01_execution_quality_context", "usable_observations", "raw_observations"),
        "R3_H02": ("H02_price_oi_quadrant", "usable_symbol_buckets", "raw_symbol_buckets"),
        "R3_H03": ("H03_liquidation_continuation", "observed_events", "raw_events"),
        "R3_H04": ("H04_liquidation_reversion", "observed_events", "raw_events"),
        "R3_H05": ("H05_crowding_stress_modifier", "usable_symbol_buckets", "raw_symbol_buckets"),
        "R3_H06": ("H06_btc_breadth_concordance", "usable_kline_symbol_buckets", "raw_symbol_buckets"),
    }
    raw: dict[str, int] = {}
    for hypothesis, (field, fallback_key, raw_key) in definitions.items():
        entry = presence.get(field, {})
        if not isinstance(entry, Mapping):
            raise ReadinessInputError(f"{field} must be an object")
        raw[hypothesis] = _number(entry, raw_key, _number(entry, fallback_key))
    raw_blocks = _number(calendar, "independent_utc_6h_blocks")
    excluded = set((gap_accounting or {}).get("excluded_block_ids", []))
    block_counts = calendar.get("eligible_by_utc_6h_block")
    if block_counts is not None and not isinstance(block_counts, Mapping):
        raise ReadinessInputError("eligible_by_utc_6h_block must be an object")
    if block_counts is None and excluded:
        supplied = calendar.get("eligible_utc_6h_blocks")
        if not isinstance(supplied, list):
            raise ReadinessInputError("excluded blocks require explicit eligible_utc_6h_blocks or eligible_by_utc_6h_block")
        effective_blocks = sum(1 for block in supplied if str(block) not in excluded)
    elif block_counts is not None:
        effective_blocks = sum(1 for block in block_counts if str(block) not in excluded)
    else:
        effective_blocks = raw_blocks
    effective = dict(raw)
    # An inventory may provide exact per-hypothesis eligible block maps. Never
    # infer an observation count by subtracting aggregate gap counters.
    for hypothesis in PRIMARY_HYPOTHESES:
        mapped = presence.get(f"eligible_{hypothesis}_by_utc_6h_block")
        prefix = definitions[hypothesis][0]
        nested = presence.get(prefix)
        if mapped is None and isinstance(nested, Mapping):
            mapped = nested.get("eligible_by_utc_6h_block")
        if isinstance(mapped, Mapping):
            effective[hypothesis] = sum(_number({"value": value}, "value") for block, value in mapped.items() if str(block) not in excluded)
        elif isinstance(nested, Mapping):
            primary_count = nested.get("primary_eligible_observations")
            if primary_count is not None and not excluded:
                effective[hypothesis] = _number({"value": primary_count}, "value")
    raw["_utc_6h_blocks"] = raw_blocks
    effective["_utc_6h_blocks"] = effective_blocks
    return raw, effective


def _gate(required: int, observed: int) -> dict[str, Any]:
    return {"required": required, "observed": observed, "pass": observed >= required}


def _canonical_roster_hash(value: Mapping[str, Any]) -> str:
    body = {
        "effective_month": value.get("effective_month"), "market": value.get("market"),
        "symbols": tuple(sorted(set(value.get("symbols", [])))),
        "prior_ranking": tuple(sorted(value.get("prior_ranking", []), key=lambda row: str(row.get("symbol", "")) if isinstance(row, Mapping) else str(row))),
        "source_sha256": value.get("source_sha256"), "effective_start": value.get("effective_start"), "effective_end": value.get("effective_end"),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _load_json(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise ReadinessInputError(f"{path} must contain an object")
    return value


def _verify_roster_artifact(path: Path) -> str:
    value = _load_json(path)
    required = ("effective_month", "market", "symbols", "prior_ranking", "source_sha256", "roster_sha256", "schema")
    if any(key not in value for key in required) or value.get("schema") != "r3_roster_v1" or value.get("market") != "um":
        raise ReadinessInputError(f"invalid roster artifact: {path}")
    month = value.get("effective_month")
    if not isinstance(month, str) or _ROSTER_MONTH_RE.fullmatch(month) is None:
        raise ReadinessInputError(f"invalid roster month in {path}")
    symbols = value.get("symbols")
    if not isinstance(symbols, list) or not symbols or any(not isinstance(symbol, str) for symbol in symbols) or len(set(symbols)) != len(symbols):
        raise ReadinessInputError(f"invalid roster symbols in {path}")
    source_sha = value.get("source_sha256")
    if not isinstance(source_sha, str) or re.fullmatch(r"[0-9a-f]{64}", source_sha) is None:
        raise ReadinessInputError(f"invalid roster source hash in {path}")
    source_path = value.get("source_path")
    if source_path:
        source = Path(str(source_path))
        if not source.is_absolute():
            source = REPO_ROOT / source
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != source_sha:
            raise ReadinessInputError(f"roster source hash mismatch: {path}")
    if value.get("roster_sha256") != _canonical_roster_hash(value):
        raise ReadinessInputError(f"roster hash mismatch: {path}")
    replay = path.with_name(path.stem + "_replay.json")
    if not replay.is_file() and month == "2026-09":
        replay = Path(r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\launch_control\2026-09-production-v8\september_roster_replay.json")
    if replay.is_file():
        replay_value = _load_json(replay)
        replay_proof = replay_value.get("proof", replay_value)
        if replay_value.get("status") != "PASS" or replay_proof.get("replayed") is not True or replay_proof.get("roster_sha256") != value.get("roster_sha256"):
            raise ReadinessInputError(f"roster replay proof mismatch: {replay}")
    else:
        raise ReadinessInputError(f"roster replay proof missing: {replay}")
    return month


def _load_roster_months(paths: Path | Sequence[Path] | None) -> list[str]:
    if paths is None:
        return []
    if isinstance(paths, Path):
        paths = [paths]
    return sorted(set(_verify_roster_artifact(Path(path)) for path in paths))


def evaluate_readiness(amendment: Mapping[str, Any], inventory: Mapping[str, Any], spec: Mapping[str, Any], *, roster_months: Sequence[str] = (), human_authorized: bool = False) -> dict[str, Any]:
    _reject_forbidden(amendment, path="amendment")
    _reject_forbidden(inventory, path="inventory")
    _reject_forbidden(spec, path="spec")
    for label, payload in (("amendment", amendment), ("inventory", inventory), ("spec", spec)):
        if payload.get("outcome_values_accessed") is True:
            raise ReadinessInputError(f"{label}.outcome_values_accessed must be false")
    if not isinstance(human_authorized, bool):
        raise ReadinessInputError("human_authorized must be boolean")
    if inventory.get("record_type") not in {INVENTORY_RECORD_TYPE, "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY"}:
        raise ReadinessInputError("unexpected inventory record_type")
    integrity = inventory.get("integrity", {})
    if not isinstance(integrity, Mapping):
        raise ReadinessInputError("integrity must be an object")
    for key in ("payload_values_retained", "performance_fields_seen", "confirmatory_root_accessed", "secondary_campaign_accessed"):
        if _as_bool(integrity.get(key, False), key):
            raise ReadinessInputError(f"{key} indicates an integrity failure")
    if spec.get("final_holdout_status") != "UNTOUCHED":
        raise ReadinessInputError("final holdout is not marked UNTOUCHED")
    if spec.get("r2b2_status") != "NOT_STARTED":
        raise ReadinessInputError("secondary campaign is not marked NOT_STARTED")
    if spec.get("outcome_analysis_status") != "NOT_STARTED":
        raise ReadinessInputError("evaluation is already marked started")

    horizon_keys = amendment.get("evaluation_horizon_keys", spec.get("evaluation_horizon_keys", []))
    if not isinstance(horizon_keys, list):
        raise ReadinessInputError("evaluation_horizon_keys must be a list")
    horizon_sha = amendment.get("evaluation_horizon_sha256", spec.get("evaluation_horizon_sha256", ""))
    interval = amendment.get("evaluation_horizon_interval", spec.get("evaluation_horizon_interval", HORIZON_INTERVAL))
    bars = amendment.get("evaluation_horizon_bars", spec.get("evaluation_horizon_bars", HORIZON_BARS))
    alternatives = amendment.get("evaluation_horizon_alternatives", spec.get("evaluation_horizon_alternatives", []))
    exact_horizon = horizon_keys == [HORIZON_KEY] and isinstance(horizon_sha, str) and re.fullmatch(r"[0-9a-f]{64}", horizon_sha) is not None and interval == HORIZON_INTERVAL and bars == HORIZON_BARS and alternatives == []
    gap_accounting = derive_gap_accounting(inventory)
    raw_counts, effective_counts = _effective_counts(inventory, gap_accounting)
    cycles = inventory.get("cycles", {})
    availability = inventory.get("availability_and_gaps", {})
    calendar = inventory.get("calendar", {})
    duplicate_cycles = _number(cycles, "duplicate_cycle_ids")
    missing_cycles = _number(cycles, "missing_cycle_count")
    boundary = availability.get("strict_15m_boundary", {})
    boundary_rejected = _number(boundary, "rejected") if isinstance(boundary, Mapping) else 0
    no_imputation = availability.get("no_imputation") is True
    completeness_pass = duplicate_cycles == 0 and boundary_rejected == 0 and no_imputation and gap_accounting["complete"]
    gates: dict[str, Any] = {
        "calendar_days": _gate(MINIMA["calendar_days"], _number(calendar, "observed_utc_days")),
        "utc_6h_blocks": _gate(MINIMA["utc_6h_blocks"], effective_counts["_utc_6h_blocks"]),
        "roster_months": _gate(MINIMA["roster_months"], len(set(roster_months))),
        "completeness": {"pass": completeness_pass, "duplicate_cycle_ids": duplicate_cycles, "missing_cycle_count": missing_cycles, "strict_boundary_rejected": boundary_rejected, "no_imputation": no_imputation, "gap_accounting_complete": gap_accounting["complete"], "raw_gap_count": gap_accounting["raw_gap_count"]},
        "hypotheses": {},
    }
    for hypothesis in PRIMARY_HYPOTHESES:
        gates["hypotheses"][hypothesis] = _gate(MINIMA[hypothesis], effective_counts[hypothesis])
    reasons: list[str] = []
    if not exact_horizon:
        reasons.append("HORIZON_NOT_FROZEN")
    if not all(gate["pass"] for name, gate in gates.items() if name != "hypotheses"):
        reasons.append("GLOBAL_METADATA_MINIMA_NOT_MET")
    if not all(gate["pass"] for gate in gates["hypotheses"].values()):
        reasons.append("HYPOTHESIS_MINIMA_NOT_MET")
    if not human_authorized:
        reasons.append("HUMAN_AUTHORIZATION_MISSING")
    contract_ok = exact_horizon and completeness_pass
    minima_ok = all(gates[name]["pass"] for name in ("calendar_days", "utc_6h_blocks", "roster_months")) and all(gate["pass"] for gate in gates["hypotheses"].values())
    state = "R3_EVALUATION_PREREGISTRATION_BLOCKED" if not contract_ok else ("R3_EVALUATION_ELIGIBLE_NOT_STARTED" if minima_ok else "R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES")
    return {
        "record_type": "R3_EVALUATION_READINESS_RECEIPT_V2", "contract_version": CONTRACT_VERSION, "state": state, "reasons": reasons,
        "auto_start": False, "human_authorized": human_authorized,
        "horizon": {"frozen": exact_horizon, "key": HORIZON_KEY if horizon_keys == [HORIZON_KEY] else None, "key_count": len(horizon_keys), "sha256_present": bool(horizon_sha), "interval": HORIZON_INTERVAL, "bars": HORIZON_BARS, "alternatives": []},
        "gates": gates, "gap_accounting": gap_accounting,
        "gap_attrition": {"raw_utc_6h_blocks": raw_counts["_utc_6h_blocks"], "effective_utc_6h_blocks": effective_counts["_utc_6h_blocks"], "raw_hypothesis_counts": {h: raw_counts[h] for h in PRIMARY_HYPOTHESES}, "effective_hypothesis_counts": {h: effective_counts[h] for h in PRIMARY_HYPOTHESES}, "rule": gap_accounting["rule"]},
        "family": {"hypotheses": list(PRIMARY_HYPOTHESES), "count": len(PRIMARY_HYPOTHESES), "correction": "HOLM_STEP_DOWN_ALPHA_0.05"},
        "firewall": {"metadata_only": True, "final_holdout": "UNTOUCHED", "r2b2": "NOT_STARTED", "outcomes_accessed": False, "outcome_values_accessed": False},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amendment", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--roster", type=Path, action="append")
    parser.add_argument("--roster-months", type=Path, help="deprecated alias for a verified roster artifact")
    parser.add_argument("--human-authorization", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if "R3_EVALUATION_AMENDMENT_V2" not in args.amendment.read_text(encoding="utf-8"):
            raise ReadinessInputError("V2 amendment marker missing")
        inventory = _load_json(args.inventory)
        spec = tomllib.loads(args.spec.read_text(encoding="utf-8"))
        contract = {key: spec.get(key) for key in ("evaluation_horizon_keys", "evaluation_horizon_sha256", "evaluation_horizon_interval", "evaluation_horizon_bars", "evaluation_horizon_alternatives")}
        roster_paths = args.roster or ([args.roster_months] if args.roster_months else [DEFAULT_ROSTER_PATH])
        result = evaluate_readiness(contract, inventory, spec, roster_months=_load_roster_months(roster_paths), human_authorized=args.human_authorization)
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError, ReadinessInputError, TypeError, ValueError) as exc:
        print(json.dumps({"record_type": "R3_EVALUATION_READINESS_RECEIPT_V2", "contract_version": CONTRACT_VERSION, "state": "R3_EVALUATION_PREREGISTRATION_BLOCKED", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            print(f"refusing to overwrite {args.output}", file=sys.stderr)
            return 2
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
