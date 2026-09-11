"""Causal, research-only Binance indicator harness."""

from .features import CORE_FEATURE_SPECS, CoreFeatureEngine
from .predictability import HORIZON_BARS, build_forward_labels, evaluate_walk_forward, fit_logistic_model, mature_training_mask, probability_metrics, resolve_horizon_bars
from .models import CoverageStatus, DatasetManifest, FeatureSpec

__all__ = [
    "CORE_FEATURE_SPECS",
    "CoreFeatureEngine",
    "HORIZON_BARS",
    "build_forward_labels",
    "mature_training_mask",
    "evaluate_walk_forward",
    "fit_logistic_model",
    "probability_metrics",
    "resolve_horizon_bars",
    "CoverageStatus",
    "DatasetManifest",
    "FeatureSpec",
]

__version__ = "0.1.0"

