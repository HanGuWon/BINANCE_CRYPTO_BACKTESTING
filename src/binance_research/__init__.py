"""Causal, research-only Binance indicator harness."""

from .features import CORE_FEATURE_SPECS, CoreFeatureEngine
from .models import CoverageStatus, DatasetManifest, FeatureSpec

__all__ = [
    "CORE_FEATURE_SPECS",
    "CoreFeatureEngine",
    "CoverageStatus",
    "DatasetManifest",
    "FeatureSpec",
]

__version__ = "0.1.0"

