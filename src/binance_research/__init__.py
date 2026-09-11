"""Causal, research-only Binance indicator harness."""

from .features import CORE_FEATURE_SPECS, CoreFeatureEngine
from .predictability import HORIZON_BARS, build_forward_labels, evaluate_walk_forward, fit_logistic_model, probability_metrics
from .models import CoverageStatus, DatasetManifest, FeatureSpec

__all__ = [
    "CORE_FEATURE_SPECS",
    "CoreFeatureEngine",
    "HORIZON_BARS",
    "build_forward_labels",
    "evaluate_walk_forward",
    "fit_logistic_model",
    "probability_metrics",
    "CoverageStatus",
    "DatasetManifest",
    "FeatureSpec",
]

__version__ = "0.1.0"

