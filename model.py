"""
model.py
========
Random Forest Future Occupancy Prediction Model
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Trains and loads the Random Forest Regressor predicting `future_occupancy`
    (expected passenger count at the upcoming stop).
  - Uses historical features from `data/bus_occupancy.csv`.
  - Feature set:
      * current_occupancy
      * boarding
      * alighting
      * previous_occupancy
      * peak_hour
      * day_type (encoded)
      * route_id (encoded)
      * stop_order / stop index
  - Model serialization: saved to `models/random_forest_occupancy.joblib`.
"""

from __future__ import annotations

import os
import joblib
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score


MODEL_DIR = "models"
MODEL_FILE = os.path.join(MODEL_DIR, "random_forest_occupancy.joblib")
CSV_PATH = os.path.join("data", "bus_occupancy.csv")

# Feature definition
FEATURE_COLUMNS = [
    "current_occupancy",
    "boarding",
    "alighting",
    "previous_occupancy",
    "peak_hour",
    "is_weekend",
    "route_code",
    "stop_num",
]
TARGET_COLUMN = "future_occupancy"

ROUTE_MAP = {"R047": 0, "R101": 1, "R205": 2, "R330": 3}


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extracts and encodes numerical features for model inference/training."""
    feat = pd.DataFrame()
    feat["current_occupancy"] = df["current_occupancy"].astype(int)
    feat["boarding"] = df["boarding"].astype(int)
    feat["alighting"] = df["alighting"].astype(int)
    feat["previous_occupancy"] = df["previous_occupancy"].astype(int)
    feat["peak_hour"] = df["peak_hour"].astype(int)
    feat["is_weekend"] = (df["day_type"].str.lower() == "weekend").astype(int)
    feat["route_code"] = df["route_id"].map(ROUTE_MAP).fillna(0).astype(int)

    # Extract numeric stop order from e.g. R101-S04 -> 4
    if "stop_id" in df.columns:
        feat["stop_num"] = df["stop_id"].apply(
            lambda s: int(str(s).split("-S")[-1]) if "-S" in str(s) else 1
        )
    else:
        feat["stop_num"] = 1

    return feat[FEATURE_COLUMNS]


def train_or_load_model() -> RandomForestRegressor:
    """Loads existing trained model if present, or trains and persists Random Forest."""
    if os.path.exists(MODEL_FILE):
        return joblib.load(MODEL_FILE)

    os.makedirs(MODEL_DIR, exist_ok=True)
    df = pd.read_csv(CSV_PATH)
    X = prepare_features(df)
    y = df[TARGET_COLUMN].values

    rf = RandomForestRegressor(
        n_estimators=100,
        max_depth=12,
        min_samples_split=4,
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X, y)
    joblib.dump(rf, MODEL_FILE)
    return rf


def predict_future_occupancy(features_df: pd.DataFrame) -> np.ndarray:
    """Predicts future occupancy for upcoming stop using Random Forest."""
    model = train_or_load_model()
    X = prepare_features(features_df)
    return model.predict(X)


if __name__ == "__main__":
    print("Training/verifying Random Forest model...")
    rf_model = train_or_load_model()
    df_raw = pd.read_csv(CSV_PATH)
    X_val = prepare_features(df_raw)
    preds = rf_model.predict(X_val)
    mae = mean_absolute_error(df_raw[TARGET_COLUMN], preds)
    r2 = r2_score(df_raw[TARGET_COLUMN], preds)
    print(f"Random Forest Model verified! Train MAE: {mae:.2f} passengers, R2: {r2:.3f}")

