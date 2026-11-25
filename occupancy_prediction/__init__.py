"""
occupancy_prediction package
============================
Module 5: Future Occupancy Prediction & Scheduling Optimization
Smart Public Transport Occupancy and Fleet Monitoring System
"""

from occupancy_prediction.prediction_pipeline import (
    FutureOccupancyPredictor,
    PredictionInput,
    PredictionResult,
    VALID_ROUTES,
)
from occupancy_prediction.multi_stop_predictor import (
    MultiStopOccupancyPredictor,
    HistoricalStopProfile,
    StopPredictionDetail,
    MultiStopPredictionResult,
)
from occupancy_prediction.crowding_forecaster import (
    CrowdingForecaster,
    CrowdingForecastResult,
    EarlyWarningNotice,
)

__all__ = [
    "FutureOccupancyPredictor",
    "PredictionInput",
    "PredictionResult",
    "VALID_ROUTES",
    "MultiStopOccupancyPredictor",
    "HistoricalStopProfile",
    "StopPredictionDetail",
    "MultiStopPredictionResult",
    "CrowdingForecaster",
    "CrowdingForecastResult",
    "EarlyWarningNotice",
]

