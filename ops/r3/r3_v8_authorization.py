"""Standing-policy and single-use child authorization for sealed R3 v8.

This module is deliberately operations-only.  It validates a checked-in
standing policy and mints a short-lived child receipt that the existing
``launch_r3_v8_resume.ps1`` consumes through ``r3_ops``.  No collector payload
or outcome data is opened here.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from ops.r3 import r3_ops


REPO_ROOT = Path(__file__).resolve().parents[2]
STANDING_POLICY_PATH = REPO_ROOT / "campaigns" / "r3_prospective_context_v1" / "operations" / "R3_V8_STANDING_RECOVERY_AUTHORIZATION_20260907.json"
CHILD_AUTH_ROOT = r3_ops.OPERATIONS_ROOT / "guardian" / "child_authorizations"
EXPECTED_POLICY_FILE_SHA256 = "6a23cf36e00b15ed5e5a46f1273052e946699a8e21a32b56588c4ae4f82e1e7c"
POLICY_RECORD_TYPE = "R3_V8_STANDING_RECOVERY_POLICY"
CHILD_AUTHORIZATION_KIND = "GUARDIAN_CHILD"
POLICY_EXPIRY_CEILING = datetime(2026, 10, 1, tzinfo=UTC)

EXPECTED_IDENTITY = {
    "root": r"D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8",
    "implementation_commit": "ecebc49dff41eeec33af62c2c85a75c5a0bd2922",
    "source_tree_sha256": "b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688",
    "registry_sha256": "c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a",
    "roster_sha256": "bb05514dfc78cfca3b736488b1454f4cb022da0110e2cbf69f53c505f543ea79",
    "launch_manifest_sha256": "cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659",
    "launch_seal_sha256": "ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85",
}

POLICY_KEYS = {
    "schema_version", "record_type", "policy_id", "issued_at_utc", "expires_at_utc", "mode",
    "scope", "allow_actions", "root", "identity", "child_authorization", "credentials",
    "outcome_firewall", "write_contract", "body_sha256",
}


class AuthorizationError(RuntimeError):
    """A fail-closed standing-policy or child-lease error."""


def _canonical_body_sha(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("body_sha256", None)
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise AuthorizationError(f"timestamp is not a string: {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorizationError(f"timestamp is malformed: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuthorizationError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _require_sha(value: Any, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(char not in "0123456789abcdefABCDEF" for char in text):
        raise AuthorizationError(f"{field} is not SHA256")
    return text.lower()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizationError(f"cannot load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AuthorizationError(f"JSON object required: {path}")
    return value


def _identity_matches(actual: Mapping[str, Any], *, context: str) -> None:
    if not isinstance(actual, Mapping):
        raise AuthorizationError(f"{context} identity is not an object")
    for field, expected in EXPECTED_IDENTITY.items():
        if str(actual.get(field)) != str(expected):
            raise AuthorizationError(f"{context} identity mismatch: {field}")


def load_standing_policy(path: Path = STANDING_POLICY_PATH, *, now: datetime | None = None) -> dict[str, Any]:
    """Validate the canonical standing policy and return its immutable file SHA."""
    path = Path(path)
    if not path.is_absolute():
        raise AuthorizationError("standing policy path must be absolute")
    if path.resolve() != STANDING_POLICY_PATH.resolve():
        raise AuthorizationError("standing policy path is not canonical")
    value = _load_json(path)
    if set(value) != POLICY_KEYS:
        raise AuthorizationError("standing policy schema drift")
    if value.get("schema_version") != 1 or value.get("record_type") != POLICY_RECORD_TYPE:
        raise AuthorizationError("standing policy record type/version")
    if value.get("mode") != "EXISTING_SEALED_V8_ONLY" or value.get("scope") != "R3_V8_RECOVERY_ONLY":
        raise AuthorizationError("standing policy mode/scope is not existing-v8 recovery")
    issued = _parse_time(value.get("issued_at_utc"))
    expires = _parse_time(value.get("expires_at_utc"))
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if expires <= issued or expires > POLICY_EXPIRY_CEILING:
        raise AuthorizationError("standing policy expiry exceeds the 2026-10-01 ceiling")
    if current < issued or current >= expires:
        raise AuthorizationError("standing policy is outside its validity window")
    if value.get("root") != EXPECTED_IDENTITY["root"]:
        raise AuthorizationError("standing policy root mismatch")
    _identity_matches({"root": value.get("root"), **(value.get("identity") or {})}, context="standing policy")
    actions = value.get("allow_actions")
    if actions != [
        "DETECT_RESUME_ELIGIBLE",
        "VERIFY_EXACT_V8_IDENTITY",
        "RUN_IMMUTABLE_PREFLIGHT",
        "MINT_SINGLE_USE_CHILD_AUTHORIZATION",
        "LAUNCH_EXISTING_V8_RESUME_ONLY",
    ]:
        raise AuthorizationError("standing policy action allowlist drift")
    if value.get("credentials") is not False:
        raise AuthorizationError("standing policy credentials must be false")
    child = value.get("child_authorization")
    if child != {
        "record_type": "R3_V8_RESUME_AUTHORIZATION",
        "authorization_kind": CHILD_AUTHORIZATION_KIND,
        "validity_minutes": 10,
        "single_use": True,
        "parent_policy_sha256_required": True,
        "preflight_receipt_required": True,
        "write_once": True,
        "atomic_publish_required": True,
        "credentials": False,
    }:
        raise AuthorizationError("standing policy child contract drift")
    if value.get("outcome_firewall") != {
        "outcomes_accessed": False,
        "final_holdout": "UNTOUCHED",
        "r2b2": "NOT_ACCESSED",
        "forceorder_v3_migration": "NOT_STARTED",
    }:
        raise AuthorizationError("standing policy outcome firewall drift")
    if value.get("write_contract") != {
        "write_once": True,
        "atomic_publish_required": True,
        "create_mode": "O_CREAT|O_EXCL",
        "overwrite": False,
        "flush_fsync_before_publish": True,
        "body_sha256_algorithm": "SHA256 of canonical UTF-8 JSON with body_sha256 omitted",
    }:
        raise AuthorizationError("standing policy write contract drift")
    if value.get("body_sha256") != _canonical_body_sha(value):
        raise AuthorizationError("standing policy body SHA mismatch")
    actual_file_sha = r3_ops._sha256(path)
    if actual_file_sha != EXPECTED_POLICY_FILE_SHA256:
        raise AuthorizationError("standing policy file SHA mismatch")
    r3_ops._reject_forbidden(value, context="standing policy")
    return {"path": str(path.resolve()), "policy": value, "policy_sha256": actual_file_sha}


def _preflight_metadata(preflight_path: Path) -> dict[str, Any]:
    path = Path(preflight_path)
    if not path.is_absolute() or not path.is_file():
        raise AuthorizationError("preflight receipt must be an absolute existing file")
    value = _load_json(path)
    if set(value) != r3_ops.PREFLIGHT_RECEIPT_FIELDS:
        raise AuthorizationError("preflight receipt schema drift")
    if value.get("record_type") != r3_ops.PREFLIGHT_RECEIPT_RECORD_TYPE or value.get("exit_code") != 0:
        raise AuthorizationError("preflight receipt is not successful")
    if value.get("no_launch_assertion") is not True or value.get("outcomes_accessed") is not False:
        raise AuthorizationError("preflight receipt lacks the no-launch/outcome firewall")
    if value.get("final_holdout") != "UNTOUCHED" or value.get("r2b2") != "NOT_ACCESSED" or value.get("forceorder_v3_migration") != "NOT_STARTED":
        raise AuthorizationError("preflight receipt firewall drift")
    writer = value.get("writer")
    if not isinstance(writer, dict) or writer.get("authorized_writer_count") != 0 or writer.get("lock_alive"):
        raise AuthorizationError("preflight receipt does not prove zero writers")
    output = value.get("output")
    if not isinstance(output, dict) or output.get("status") != "PASS":
        raise AuthorizationError("preflight receipt output is not PASS")
    return {"path": path.resolve(), "value": value, "sha256": r3_ops._sha256(path), "writer": writer}


def mint_child_authorization(
    policy_binding: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    preflight_path: Path,
    now: datetime | None = None,
    destination_root: Path = CHILD_AUTH_ROOT,
) -> dict[str, Any]:
    """Mint one atomic, ten-minute child lease bound to policy and preflight."""
    if not isinstance(policy_binding, Mapping) or policy_binding.get("policy_sha256") is None:
        raise AuthorizationError("standing policy binding is missing")
    policy_sha = _require_sha(policy_binding.get("policy_sha256"), "parent_policy_sha256")
    binding_path = policy_binding.get("path")
    if not isinstance(binding_path, str) or not binding_path:
        raise AuthorizationError("standing policy binding path is missing")
    verified_binding = load_standing_policy(Path(binding_path), now=now)
    if verified_binding["policy_sha256"] != policy_sha:
        raise AuthorizationError("standing policy binding SHA does not match the verified policy file")
    policy = verified_binding["policy"]
    _identity_matches({"root": policy.get("root"), **(policy.get("identity") or {})}, context="child policy")
    _identity_matches(identity, context="child snapshot")
    if str(identity.get("root")) != EXPECTED_IDENTITY["root"]:
        raise AuthorizationError("child snapshot root mismatch")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    issued = _parse_time(policy.get("issued_at_utc"))
    expires_policy = _parse_time(policy.get("expires_at_utc"))
    if current < issued or current >= expires_policy:
        raise AuthorizationError("standing policy is not currently valid")
    preflight = _preflight_metadata(Path(preflight_path))
    expires = current + timedelta(minutes=10)
    if expires > expires_policy or expires > POLICY_EXPIRY_CEILING:
        raise AuthorizationError("child authorization would exceed policy expiry")
    authorization_id = str(uuid.uuid4())
    child: dict[str, Any] = {
        "record_type": r3_ops.RESUME_AUTHORIZATION_RECORD_TYPE,
        "authorization_id": authorization_id,
        "issued_at_utc": current.isoformat(),
        "expires_at_utc": expires.isoformat(),
        "consumed_at_utc": None,
        "authorized_by": "r3-v8-guardian",
        "mode": "EXISTING_SEALED_V8_ONLY",
        "root": EXPECTED_IDENTITY["root"],
        "implementation_commit": EXPECTED_IDENTITY["implementation_commit"],
        "source_tree_sha256": EXPECTED_IDENTITY["source_tree_sha256"],
        "registry_sha256": EXPECTED_IDENTITY["registry_sha256"],
        "roster_sha256": EXPECTED_IDENTITY["roster_sha256"],
        "launch_manifest_sha256": EXPECTED_IDENTITY["launch_manifest_sha256"],
        "launch_seal_sha256": EXPECTED_IDENTITY["launch_seal_sha256"],
        "preflight_receipt_path": str(preflight["path"]),
        "preflight_receipt_sha256": preflight["sha256"],
        "preflight_exit_code": 0,
        "preflight_writer": preflight["writer"],
        "authorization_kind": CHILD_AUTHORIZATION_KIND,
        "parent_policy_sha256": policy_sha,
    }
    if set(child) != r3_ops.CHILD_RESUME_AUTHORIZATION_FIELDS:
        raise AuthorizationError("child authorization schema drift")
    r3_ops._reject_forbidden(child, context="guardian child authorization")
    destination = Path(destination_root)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"R3_V8_GUARDIAN_CHILD_{current.astimezone(UTC).strftime('%Y%m%dT%H%M%S%fZ')}_{authorization_id}.json"
    r3_ops._write_json_exclusive(path, child)
    return {
        "path": str(path.resolve()),
        "authorization": child,
        "authorization_sha256": r3_ops._sha256(path),
        "parent_policy_sha256": policy_sha,
        "preflight_receipt_sha256": preflight["sha256"],
        "issued_at_utc": child["issued_at_utc"],
        "expires_at_utc": child["expires_at_utc"],
    }


def verify_child_metadata(
    child_path: Path,
    *,
    policy_binding: Mapping[str, Any],
    identity: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify child provenance without consuming it; the launcher performs consume."""
    value = _load_json(Path(child_path))
    if set(value) != r3_ops.CHILD_RESUME_AUTHORIZATION_FIELDS:
        raise AuthorizationError("child authorization schema drift")
    if value.get("authorization_kind") != CHILD_AUTHORIZATION_KIND:
        raise AuthorizationError("child authorization kind invalid")
    if value.get("authorized_by") != "r3-v8-guardian":
        raise AuthorizationError("child authorization issuer invalid")
    expected_parent = _require_sha(policy_binding.get("policy_sha256"), "parent_policy_sha256")
    if value.get("parent_policy_sha256") != expected_parent:
        raise AuthorizationError("child authorization parent policy mismatch")
    _identity_matches(identity, context="child snapshot")
    for field, expected in (
        ("root", EXPECTED_IDENTITY["root"]),
        ("implementation_commit", EXPECTED_IDENTITY["implementation_commit"]),
        ("source_tree_sha256", EXPECTED_IDENTITY["source_tree_sha256"]),
        ("registry_sha256", EXPECTED_IDENTITY["registry_sha256"]),
        ("roster_sha256", EXPECTED_IDENTITY["roster_sha256"]),
        ("launch_manifest_sha256", EXPECTED_IDENTITY["launch_manifest_sha256"]),
        ("launch_seal_sha256", EXPECTED_IDENTITY["launch_seal_sha256"]),
    ):
        if str(value.get(field)) != str(expected):
            raise AuthorizationError(f"child identity mismatch: {field}")
    issued = _parse_time(value.get("issued_at_utc"))
    expires = _parse_time(value.get("expires_at_utc"))
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if expires - issued != timedelta(minutes=10):
        raise AuthorizationError("child authorization validity is not exactly ten minutes")
    if current < issued or current >= expires:
        raise AuthorizationError("child authorization is expired or not yet valid")
    if value.get("consumed_at_utc") is not None:
        raise AuthorizationError("child authorization has already been consumed")
    preflight = _preflight_metadata(Path(str(value.get("preflight_receipt_path"))))
    if preflight["sha256"] != value.get("preflight_receipt_sha256"):
        raise AuthorizationError("child preflight SHA mismatch")
    return {
        "status": "PASS",
        "path": str(Path(child_path).resolve()),
        "authorization_sha256": r3_ops._sha256(Path(child_path)),
        "parent_policy_sha256": expected_parent,
        "preflight_receipt_sha256": preflight["sha256"],
        "issued_at_utc": issued.isoformat(),
        "expires_at_utc": expires.isoformat(),
    }
