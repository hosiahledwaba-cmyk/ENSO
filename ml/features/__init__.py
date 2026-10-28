"""ENSO Shield feature engineering and target generation module."""

from ml.features.config import (
    FeaturePipelineConfig,
    ForecastTimelineConfig,
    SpatialMetadata,
    SplitConfig,
    TargetConfig,
)
from ml.features.data_dictionary import FEATURE_DATA_DICTIONARY, VariableDefinition
from ml.features.generator import FeatureExtractionError, FeatureGenerator
from ml.features.leakage import (
    PartitionOverlapError,
    TargetLeakageDetector,
    TargetLeakageError,
    TemporalOrderViolationError,
)
from ml.features.pipeline import FeaturePipeline
from ml.features.target import ReferenceDistribution, TargetComputationError

__all__ = [
    "FEATURE_DATA_DICTIONARY",
    "FeatureExtractionError",
    "FeatureGenerator",
    "FeaturePipeline",
    "FeaturePipelineConfig",
    "ForecastTimelineConfig",
    "PartitionOverlapError",
    "ReferenceDistribution",
    "SpatialMetadata",
    "SplitConfig",
    "TargetComputationError",
    "TargetConfig",
    "TargetLeakageDetector",
    "TargetLeakageError",
    "TemporalOrderViolationError",
    "VariableDefinition",
]
