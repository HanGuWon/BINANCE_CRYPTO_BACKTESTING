from pathlib import Path
import hashlib, json, pytest
from binance_research.forward import verify_model_artifact

def test_model_artifact_tamper_rejected(tmp_path: Path):
    path = tmp_path / "model.json"
    payload = {"artifact_schema":"predictability-v1-model-v1","model":{"coef":[1]},"metadata":{"campaign_id":"cmp","training_cutoff":"t"}}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    verified = verify_model_artifact(path, digest, expected_metadata={"campaign_id":"cmp"})
    assert verified["_sha256"] == digest
    path.write_bytes(raw + b"x")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        verify_model_artifact(path, digest)
