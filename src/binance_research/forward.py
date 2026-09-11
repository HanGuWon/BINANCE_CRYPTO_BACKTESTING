"""Outcome-blind forward/provenance contracts for Predictability V1."""
from __future__ import annotations
import hashlib, json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Sequence
import numpy as np
import pandas as pd

def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

def sha256_file(path: Path | str) -> str:
    candidate = Path(path)
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def verify_expected_sha256(path: Path | str, expected: str | None, *, label: str = "artifact") -> str:
    actual = sha256_file(path)
    if expected is not None and actual.casefold() != str(expected).casefold():
        raise ValueError(f"{label} SHA256 mismatch: expected {expected}, got {actual}")
    return actual

def prediction_identity(*, market: str, symbol: str, timeframe: str, decision_time: object, horizon: str, model_id: str, campaign_id: str, model_artifact_sha256: str | None = None, dataset_sha256: str | None = None, source_tree_sha256: str | None = None, feature_registry_sha256: str | None = None, config_sha256: str | None = None, mode: str | None = None) -> str:
    timestamp = pd.Timestamp(decision_time)
    if pd.isna(timestamp): raise ValueError("decision_time is required for prediction identity")
    timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    payload = {"campaign_id": str(campaign_id), "decision_time": timestamp.isoformat(), "horizon": str(horizon), "market": str(market), "model_id": str(model_id), "symbol": str(symbol), "timeframe": str(timeframe), "model_artifact_sha256": model_artifact_sha256, "dataset_sha256": dataset_sha256, "source_tree_sha256": source_tree_sha256, "feature_registry_sha256": feature_registry_sha256, "config_sha256": config_sha256, "mode": mode}
    return hashlib.sha256(_canonical_json(payload)).hexdigest()

def model_artifact_payload(model: Any, **metadata: Any) -> dict[str, Any]:
    values = asdict(model) if is_dataclass(model) else (dict(model) if isinstance(model, dict) else dict(vars(model)))
    return {"artifact_schema": "predictability-v1-model-v1", "model": values, "metadata": metadata}

def write_model_artifact(path: Path, model: Any, *, allow_identical: bool = False, **metadata: Any) -> str:
    destination = Path(path); destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json(model_artifact_payload(model, **metadata)) + bytes([10]); digest = hashlib.sha256(payload).hexdigest()
    if destination.exists():
        if allow_identical and destination.read_bytes() == payload: return digest
        raise FileExistsError(f"refusing to overwrite model artifact: {destination}")
    destination.write_bytes(payload); return digest

def append_predictions_write_once(path: Path, rows: pd.DataFrame | Sequence[dict[str, Any]], *, allow_replay: bool = False) -> None:
    incoming = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame.from_records(rows)
    if "prediction_id" not in incoming.columns: raise ValueError("prediction_id is required for write-once predictions")
    if incoming["prediction_id"].isna().any() or incoming["prediction_id"].duplicated().any(): raise ValueError("prediction_id must be non-null and unique within an append")
    destination = Path(path)
    if destination.exists():
        existing = pd.read_csv(destination)
        if "prediction_id" not in existing.columns: raise ValueError("existing prediction store lacks immutable prediction_id")
        ids = incoming["prediction_id"].astype(str); overlap = set(existing["prediction_id"].astype(str)) & set(ids)
        if overlap and not allow_replay: raise ValueError(f"duplicate prediction_id refused: {sorted(overlap)[0]}")
        for prediction_id in sorted(overlap):
            old = existing[existing["prediction_id"].astype(str) == prediction_id].iloc[0]; new = incoming[ids == prediction_id].iloc[0]
            common = [column for column in incoming.columns if column in existing.columns and column != "prediction_recorded_at"]
            if any(str(old[column]) != str(new[column]) for column in common): raise ValueError(f"conflicting prediction_id refused: {prediction_id}")
        incoming = incoming[~ids.isin(overlap)].copy()
        if incoming.empty: return
        incoming = pd.concat([existing, incoming], ignore_index=True, sort=False)
    destination.parent.mkdir(parents=True, exist_ok=True); temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists(): raise FileExistsError(f"stale temporary prediction store exists: {temporary}")
    incoming.to_csv(temporary, index=False); temporary.replace(destination)

def append_jsonl_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Append a receipt atomically, preserving prior bytes on interruption."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing = destination.read_bytes() if destination.exists() else b""
    line = _canonical_json(payload) + b"\n"
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise FileExistsError(f"stale temporary receipt exists: {temporary}")
    temporary.write_bytes(existing + line)
    temporary.replace(destination)

def guard_final_holdout_path(path: Path | str) -> None:
    candidate = Path(path)
    if "final_holdout" in str(candidate).casefold(): raise PermissionError("final-holdout input requires explicit post-freeze authorization")
    for metadata_path in (candidate.with_suffix(candidate.suffix + ".metadata.json"), candidate.parent / "metadata.json", candidate.parent / "holdout_metadata.json"):
        if metadata_path.exists():
            try: metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError): continue
            if bool(metadata.get("final_holdout")) or str(metadata.get("split", "")).casefold() == "final_holdout": raise PermissionError("input metadata marks final holdout; explicit authorization required")

def paired_log_loss_difference(labels: Sequence[float], baseline: Sequence[float], model: Sequence[float]) -> np.ndarray:
    y=np.asarray(labels,dtype=float); b=np.clip(np.asarray(baseline,dtype=float),1e-12,1-1e-12); m=np.clip(np.asarray(model,dtype=float),1e-12,1-1e-12)
    if not (len(y)==len(b)==len(m)): raise ValueError("paired score inputs must have equal length")
    return -(y*np.log(b)+(1-y)*np.log(1-b)) + (y*np.log(m)+(1-y)*np.log(1-m))

def holm_adjust(pvalues: Sequence[float]) -> np.ndarray:
    values=np.asarray(pvalues,dtype=float)
    if np.any(~np.isfinite(values)) or np.any((values<0)|(values>1)): raise ValueError("p-values must be finite and in [0, 1]")
    order=np.argsort(values,kind="stable"); adjusted=np.empty(len(values)); running=0.0
    for rank,index in enumerate(order): running=max(running,(len(values)-rank)*values[index]); adjusted[index]=min(1.0,running)
    return adjusted

def calendar_block_bootstrap(values: Sequence[float], timestamps: Sequence[object], *, block_days: int = 1, samples: int = 1000, seed: int = 1729) -> tuple[float,float]:
    if block_days<1 or samples<1: raise ValueError("block_days and samples must be positive")
    clean=pd.DataFrame({"value":values,"timestamp":pd.to_datetime(timestamps,utc=True,errors="coerce")}).dropna()
    if clean.empty: return np.nan,np.nan
    clean["block"]=clean["timestamp"].dt.floor(f"{block_days}D"); blocks=[g["value"].to_numpy(dtype=float) for _,g in clean.groupby("block",sort=True)]
    if len(blocks)<2: return np.nan,np.nan
    rng=np.random.default_rng(seed); draws=np.empty(samples)
    for i in range(samples): draws[i]=np.concatenate([blocks[j] for j in rng.integers(0,len(blocks),size=len(blocks))]).mean()
    return float(np.quantile(draws,.025)),float(np.quantile(draws,.975))

def funding_cashflow(events: pd.DataFrame | Sequence[dict[str, Any]], entry_time: object, exit_time: object, side: str, notional: float = 1.0) -> float:
    """Deterministic synthetic funding cashflow; positive rate is paid by LONG."""
    if side not in {"LONG", "SHORT"}: raise ValueError("side must be LONG or SHORT")
    start, end = pd.Timestamp(entry_time), pd.Timestamp(exit_time)
    if start.tzinfo is None: start = start.tz_localize("UTC")
    if end.tzinfo is None: end = end.tz_localize("UTC")
    frame = events.copy() if isinstance(events, pd.DataFrame) else pd.DataFrame.from_records(events)
    if frame.empty or "funding_time" not in frame or "funding_rate" not in frame: return 0.0
    times = pd.to_datetime(frame["funding_time"], utc=True, errors="coerce")
    rates = pd.to_numeric(frame["funding_rate"], errors="coerce")
    mask = times.notna() & rates.notna() & (times >= start) & (times < end)
    sign = -1.0 if side == "LONG" else 1.0
    return float(sign * rates.loc[mask].sum() * float(notional))


