from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class CoverageStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    HISTORICAL_UNAVAILABLE = "HISTORICAL_UNAVAILABLE"
    NOT_REQUESTED = "NOT_REQUESTED"


@dataclass(frozen=True)
class FeatureSpec:
    feature_id: str
    family: str
    required_inputs: tuple[str, ...]
    parameters: dict[str, Any]
    warmup: int
    continuous_columns: tuple[str, ...]
    state_column: str | None = None
    signal_column: str | None = None
    documentation: str = ""


@dataclass(frozen=True)
class IntegrityIssue:
    code: str
    severity: str
    detail: str
    count: int = 1


@dataclass
class DatasetManifest:
    schema_version: int
    source: str
    market_type: str
    dataset: str
    symbol: str
    interval: str | None
    first_timestamp: str | None
    last_timestamp: str | None
    row_count: int
    downloaded_at: str
    computed_sha256: str
    published_sha256: str | None = None
    coverage_status: CoverageStatus = CoverageStatus.AVAILABLE
    coverage_note: str = ""
    issues: list[IntegrityIssue] = field(default_factory=list)
    archive_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["coverage_status"] = self.coverage_status.value
        return payload

