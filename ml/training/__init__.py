"""Climate model training, baseline benchmarking, and rolling-origin evaluation."""

from ml.training.baseline import ClimatologyBaseline
from ml.training.config import DEFAULT_PREDICTOR_FEATURES, TrainingConfig
from ml.training.cross_validation import RollingOriginEvaluator
from ml.training.experiment import ClimateModelExperiment
from ml.training.models import LogisticRegressionPredictor, XGBoostPredictor

__all__ = [
    "DEFAULT_PREDICTOR_FEATURES",
    "ClimateModelExperiment",
    "ClimatologyBaseline",
    "LogisticRegressionPredictor",
    "RollingOriginEvaluator",
    "TrainingConfig",
    "XGBoostPredictor",
]
