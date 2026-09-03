"""Outcome-blind R3 evaluation-readiness gate.

This module reads only the frozen evaluation contract and metadata summaries.
It has no import path to a materializer, executor, label builder, or result
store.  It returns a readiness state; it never starts a process or writes a
run checkpoint.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "r3-evaluation-readiness-v1"
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

# These are exact field names, not broad substrings.  Safety flags such as
# ``performance_fields_seen`` are explicitly allowed because they prove that
# the forbidden material was not read.
FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "gross_return",
        "net_return",
        "future_return",
        "forward_label",
        "pnl",
        "sharpe",
        "sortino",
        "hit_rate",
        "win_rate",
        "mfe",
        "mae",
        "candidate_ranking",
        "performance_metric",
        "outcome_values",
        "holdout_rows",
        "r2b2",
    }
)
BROAD_FORBIDDEN_TOKENS = frozenset({"outcome", "return", "pnl", "sharpe", "hit_rate", "future", "holdout", "r2b2"})
ALLOWED_SAFETY_KEYS = frozenset(
    {
        "outcomes_accessed",
        "outcome_analysis_status",
        "performance_fields_seen",
        "confirmatory_root_accessed",
        "secondary_campaign_accessed",
        "final_holdout_status",
        "final_holdout",
        "r2b2_status",
    }
)
PATH_KEYS = frozenset({"path", "root", "file", "artifact", "uri", "source"})
FORBIDDEN_PATH_TOKENS = frozenset(
    {
        "final_holdout",
        "holdout",
        "r2b2",
        "future_return",
        "gross_return",
        "net_return",
        "pnl",
        "sharpe",
        "hit_rate",
        "performance",
    }
)
_ROSTER_MONTH_RE = re.compile(r"^(20\d{2}-\d{2})$")


class ReadinessInputError(ValueError):
    """Raised when an input is outside the metadata-only contract."""


def _normal_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _reject_forbidden(value: Any, *, path: str = "$", parent_key: str = "") -> None:
    """Reject result-bearing fields and unsafe paths before any counting."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normal_key(key)
            if normalized not in ALLOWED_SAFETY_KEYS and (
                normalized in FORBIDDEN_KEY_TOKENS
                or any(token in normalized for token in BROAD_FORBIDDEN_TOKENS)
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
    return max(0, int(value))


def _effective_counts(inventory: Mapping[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    """Apply conservative metadata-only gap attrition to usable counts."""

    availability = inventory.get("availability_and_gaps", {})
    cycles = inventory.get("cycles", {})
    gap_count = max(
        _number(availability, "gap_records"),
        _number(availability, "health_gap_count"),
        _number(availability, "health_restart_count"),
    )
    # The inventory exposes aggregate health gaps rather than a per-gap block
    # map.  Conservatively remove one complete block whenever any gap/restart
    # is reported; per-hypothesis counts remove each reported gap.  No payload
    # or future observation is read.
    raw_blocks = _number(inventory.get("calendar", {}), "independent_utc_6h_blocks")
    effective_blocks = max(0, raw_blocks - (1 if gap_count else 0))
    presence = inventory.get("causal_input_presence", {})
    raw: dict[str, int] = {
        "R3_H01": _number(presence.get("H01_execution_quality_context", {}), "usable_observations"),
        "R3_H02": _number(presence.get("H02_price_oi_quadrant", {}), "usable_symbol_buckets"),
        "R3_H03": _number(presence.get("H03_liquidation_continuation", {}), "observed_events"),
        "R3_H04": _number(presence.get("H04_liquidation_reversion", {}), "observed_events"),
        "R3_H05": _number(presence.get("H05_crowding_stress_modifier", {}), "usable_symbol_buckets"),
        "R3_H06": _number(presence.get("H06_btc_breadth_concordance", {}), "usable_kline_symbol_buckets"),
    }
    effective = {hypothesis: max(0, count - min(count, gap_count)) for hypothesis, count in raw.items()}
    effective["_gap_count"] = gap_count
    effective["_utc_6h_blocks"] = effective_blocks
    # Preserve the raw values for the receipt without retaining observations.
    raw["_gap_count"] = gap_count
    raw["_utc_6h_blocks"] = raw_blocks
    return raw, effective


def _gate(required: int, observed: int) -> dict[str, Any]:
    return {"required": required, "observed": observed, "pass": observed >= required}


def evaluate_readiness(
    amendment: Mapping[str, Any],
    inventory: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    roster_months: Sequence[str] = (),
    human_authorized: bool = False,
) -> dict[str, Any]:
    """Evaluate a metadata-only readiness snapshot.

    The function is deliberately pure.  Synthetic callers can supply mappings;
    the CLI supplies mappings loaded from the frozen amendment/spec/inventory.
    """

    _reject_forbidden(amendment, path="amendment")
    _reject_forbidden(inventory, path="inventory")
    _reject_forbidden(spec, path="spec")
    if not isinstance(human_authorized, bool):
        raise ReadinessInputError("human_authorized must be boolean")

    if inventory.get("record_type") != "R3_OUTCOME_BLIND_EVIDENCE_INVENTORY":
        raise ReadinessInputError("unexpected inventory record_type")
    integrity = inventory.get("integrity", {})
    if _as_bool(integrity.get("payload_values_retained", True), "payload_values_retained"):
        raise ReadinessInputError("payload values are not permitted")
    if _as_bool(integrity.get("performance_fields_seen", True), "performance_fields_seen"):
        raise ReadinessInputError("forbidden performance fields were seen")
    if _as_bool(integrity.get("confirmatory_root_accessed", True), "confirmatory_root_accessed"):
        raise ReadinessInputError("confirmatory root was accessed")
    if _as_bool(integrity.get("secondary_campaign_accessed", True), "secondary_campaign_accessed"):
        raise ReadinessInputError("secondary campaign was accessed")
    if spec.get("final_holdout_status") != "UNTOUCHED":
        raise ReadinessInputError("final holdout is not marked UNTOUCHED")
    if spec.get("r2b2_status") != "NOT_STARTED":
        raise ReadinessInputError("secondary campaign is not marked NOT_STARTED")
    if spec.get("outcome_analysis_status") != "NOT_STARTED":
        raise ReadinessInputError("evaluation is already marked started")

    cycles = inventory.get("cycles", {})
    availability = inventory.get("availability_and_gaps", {})
    dependence = inventory.get("dependence", {})
    calendar = inventory.get("calendar", {})
    raw_counts, effective_counts = _effective_counts(inventory)
    duplicate_cycles = _number(cycles, "duplicate_cycle_ids")
    missing_cycles = _number(cycles, "missing_cycle_count")
    boundary = availability.get("strict_15m_boundary", {})
    boundary_rejected = _number(boundary, "rejected")
    no_imputation = availability.get("no_imputation") is True
    gap_records = _number(availability, "gap_records")

    gates: dict[str, Any] = {
        "calendar_days": _gate(MINIMA["calendar_days"], _number(calendar, "observed_utc_days")),
        "utc_6h_blocks": _gate(MINIMA["utc_6h_blocks"], effective_counts["_utc_6h_blocks"]),
        "roster_months": _gate(MINIMA["roster_months"], len(set(roster_months))),
        "completeness": {
            "pass": duplicate_cycles == 0 and missing_cycles == 0 and boundary_rejected == 0 and no_imputation,
            "duplicate_cycle_ids": duplicate_cycles,
            "missing_cycle_count": missing_cycles,
            "strict_boundary_rejected": boundary_rejected,
            "no_imputation": no_imputation,
            "gap_records": gap_records,
        },
        "hypotheses": {},
    }
    for hypothesis in PRIMARY_HYPOTHESES:
        gates["hypotheses"][hypothesis] = _gate(MINIMA[hypothesis], effective_counts[hypothesis])

    horizon_keys = amendment.get("evaluation_horizon_keys", spec.get("evaluation_horizon_keys", []))
    if not isinstance(horizon_keys, list):
        raise ReadinessInputError("evaluation_horizon_keys must be a list")
    horizon_frozen = len(horizon_keys) == 1 and bool(amendment.get("evaluation_horizon_sha256"))
    reasons: list[str] = []
    if not horizon_frozen:
        reasons.append("HORIZON_NOT_FROZEN")
    if not all(gate["pass"] for name, gate in gates.items() if name != "hypotheses"):
        reasons.append("GLOBAL_METADATA_MINIMA_NOT_MET")
    if not all(gate["pass"] for gate in gates["hypotheses"].values()):
        reasons.append("HYPOTHESIS_MINIMA_NOT_MET")
    if not human_authorized:
        reasons.append("HUMAN_AUTHORIZATION_MISSING")

    return {
        "record_type": "R3_EVALUATION_READINESS_RECEIPT",
        "contract_version": CONTRACT_VERSION,
        "state": "R3_EVALUATION_ELIGIBLE_NOT_STARTED" if not reasons else "R3_EVALUATION_PREREGISTRATION_BLOCKED",
        "reasons": reasons,
        "auto_start": False,
        "human_authorized": human_authorized,
        "horizon": {
            "frozen": horizon_frozen,
            "key_count": len(horizon_keys),
            "sha256_present": bool(amendment.get("evaluation_horizon_sha256")),
        },
        "gates": gates,
        "gap_attrition": {
            "reported_gap_or_restart_count": effective_counts["_gap_count"],
            "raw_utc_6h_blocks": raw_counts["_utc_6h_blocks"],
            "effective_utc_6h_blocks": effective_counts["_utc_6h_blocks"],
            "raw_hypothesis_counts": {h: raw_counts[h] for h in PRIMARY_HYPOTHESES},
            "effective_hypothesis_counts": {h: effective_counts[h] for h in PRIMARY_HYPOTHESES},
            "rule": "remove one UTC block if any gap/restart is reported and one count per reported gap/restart; never impute",
        },
        "family": {
            "hypotheses": list(PRIMARY_HYPOTHESES),
            "count": len(PRIMARY_HYPOTHESES),
            "correction": "HOLM_STEP_DOWN_ALPHA_0.05",
        },
        "firewall": {
            "metadata_only": True,
            "final_holdout": "UNTOUCHED",
            "r2b2": "NOT_STARTED",
            "outcomes_accessed": False,
        },
    }


def _load_json(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise ReadinessInputError(f"{path} must contain an object")
    return value


def _load_roster_months(path: Path | None) -> list[str]:
    if path is None:
        return []
    value = _load_json(path)
    months = value.get("verified_roster_months", [])
    if not isinstance(months, list) or not all(isinstance(month, str) for month in months):
        raise ReadinessInputError("verified_roster_months must be a list of YYYY-MM strings")
    if any(_ROSTER_MONTH_RE.fullmatch(month) is None for month in months):
        raise ReadinessInputError("invalid roster month")
    return sorted(set(months))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amendment", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--roster-months", type=Path)
    parser.add_argument("--human-authorization", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        amendment_text = args.amendment.read_text(encoding="utf-8")
        # The prose file is not itself a data source; the exact horizon status
        # is supplied by campaign_spec.  Retain a marker check to prevent a
        # receipt from being built against an unrelated contract.
        if "R3_EVALUATION_PREREGISTRATION_BLOCKED" not in amendment_text:
            raise ReadinessInputError("amendment marker missing")
        inventory = _load_json(args.inventory)
        # The amendment is Markdown, so contract fields come from campaign_spec.
        spec_text = args.spec.read_text(encoding="utf-8")
        spec = tomllib.loads(spec_text)
        contract = {
            "evaluation_horizon_keys": spec.get("evaluation_horizon_keys", []),
            "evaluation_horizon_source": spec.get("evaluation_horizon_source", ""),
            "amendment_path": str(args.amendment),
        }
        result = evaluate_readiness(
            contract,
            inventory,
            spec,
            roster_months=_load_roster_months(args.roster_months),
            human_authorized=args.human_authorization,
        )
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError, ReadinessInputError) as exc:
        print(json.dumps({"record_type": "R3_EVALUATION_READINESS_RECEIPT", "state": "R3_EVALUATION_PREREGISTRATION_BLOCKED", "error": str(exc)}, indent=2), file=sys.stderr)
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
