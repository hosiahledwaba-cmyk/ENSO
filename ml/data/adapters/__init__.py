"""Dataset adapters package."""

from ml.data.adapters.base import BaseDatasetAdapter
from ml.data.adapters.chirps_rainfall import ChirpsRainfallAdapter
from ml.data.adapters.noaa_nino34 import NoaaNino34Adapter
from ml.data.adapters.noaa_oni import NoaaOniAdapter

__all__ = [
    "BaseDatasetAdapter",
    "ChirpsRainfallAdapter",
    "NoaaNino34Adapter",
    "NoaaOniAdapter",
]
