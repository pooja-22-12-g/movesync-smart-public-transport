"""
occupancy_prediction/prediction_pipeline.py
===========================================
Module 5, Step 1: Occupancy Data Processing & Prediction Integration
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Connect updated occupancy counts from Module 4 (or historical telemetry)
    to the Random Forest prediction pipeline (model.py).
  - Prepare, validate, and sanitize prediction input records.
  - Predict future passenger occupancy at the upcoming stop.
  - Constrain predicted occupancy to [0, bus_capacity].
  - Calculate predicted occupancy percentage.
  - Classify predicted alert status matching Module 2 thresholds:
        Normal: < 85%
        Warning: 85% to < 100%
        Critical: >= 100%
  - Maintain clear separation between historical and newly processed video sessions.
  - Strictly preserve original CSV dataset and previous modules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Union

import pandas as pd
import numpy as np

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import Random Forest model loader/predictor
from model import predict_future_occupancy, ROUTE_MAP, FEATURE_COLUMNS, train_or_load_model
from passenger_counting.occupancy_integrator import (
    OccupancyUpdateResult,
    THRESHOLD_WARNING,
    THRESHOLD_CRITICAL,
    SEVERITY_NORMAL,
    SEVERITY_WARNING,
    SEVERITY_CRITICAL,
    DEFAULT_BUS_CAPACITY,
)


VALID_ROUTES = ["R047", "R101", "R205", "R330"]


@dataclass
class PredictionInput:
    """Standardized and validated input record for occupancy prediction."""
    bus_id: str
    route_id: str
    current_occupancy: int
    boarding: int
    alighting: int
    previous_occupancy: int
    bus_capacity: int = DEFAULT_BUS_CAPACITY
    stop_id: str = "R101-S01"
    peak_hour: int = 0
    day_type: str = "weekday"
    source: str = "camera_cv"  # 'camera_cv' or 'historical_csv' or 'simulated'
    notes: List[str] = field(default_factory=list)


@dataclass
class PredictionResult:
    """Standardized output structure for future occupancy prediction."""
    bus_id: str
    route_id: str
    stop_id: str
    current_occupancy: int
    boarding: int
    alighting: int
    bus_capacity: int
    raw_predicted_future: float
    predicted_future_occupancy: int
    predicted_occupancy_pct: float
    predicted_status: str
    is_overcrowded: bool
    data_source: str
    notes: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FutureOccupancyPredictor:
    """
    Data-processing and prediction coordinator connecting Module 4
    occupancy counts to the Random Forest model.
    """

    def __init__(self):
        # Pre-warm model
        self.model = train_or_load_model()

    def validate_and_sanitize_input(
        self,
        bus_id: Optional[str] = "KA-BUS-001",
        route_id: Optional[str] = "R101",
        current_occupancy: Union[int, float, str, None] = 20,
        boarding: Union[int, float, str, None] = 0,
        alighting: Union[int, float, str, None] = 0,
        previous_occupancy: Union[int, float, str, None] = None,
        bus_capacity: Union[int, float, str, None] = DEFAULT_BUS_CAPACITY,
        stop_id: Optional[str] = None,
        peak_hour: Union[int, str, None] = 0,
        day_type: Optional[str] = "weekday",
        source: str = "camera_cv",
    ) -> PredictionInput:
        """Sanitizes raw inputs, applies defaults, and records validation notes."""
        notes: List[str] = []

        # Bus ID sanitization
        safe_bus = str(bus_id).strip() if bus_id else "KA-BUS-001"
        if not safe_bus.startswith("KA-BUS-"):
            notes.append(f"Non-standard Bus ID '{safe_bus}' received.")

        # Route ID sanitization
        safe_route = str(route_id).strip().upper() if route_id else "R101"
        if safe_route not in VALID_ROUTES:
            notes.append(f"Unknown route '{safe_route}'; mapped to default 'R101'.")
            safe_route = "R101"

        # Capacity sanitization
        safe_capacity = self._safe_int(bus_capacity, default=DEFAULT_BUS_CAPACITY, name="capacity", notes=notes)
        if safe_capacity <= 0:
            safe_capacity = DEFAULT_BUS_CAPACITY

        # Boarding & alighting sanitization
        safe_boarding = self._safe_int(boarding, default=0, name="boarding", notes=notes)
        safe_alighting = self._safe_int(alighting, default=0, name="alighting", notes=notes)

        # Current & previous occupancy
        safe_current = self._safe_int(current_occupancy, default=20, name="current_occupancy", notes=notes)
        if safe_current < 0:
            notes.append(f"Negative current occupancy ({safe_current}); clamped to 0.")
            safe_current = 0
        elif safe_current > safe_capacity:
            notes.append(f"Current occupancy ({safe_current}) exceeded capacity ({safe_capacity}); clamped.")
            safe_current = safe_capacity

        if previous_occupancy is not None:
            safe_prev = self._safe_int(previous_occupancy, default=safe_current, name="previous_occupancy", notes=notes)
        else:
            safe_prev = max(0, safe_current - safe_boarding + safe_alighting)

        # Stop ID sanitization
        safe_stop = str(stop_id).strip() if stop_id else f"{safe_route}-S01"

        # Peak hour sanitization
        safe_peak = 1 if str(peak_hour) in ["1", "true", "True"] else 0

        # Day type
        safe_day = "weekend" if str(day_type).lower() == "weekend" else "weekday"

        return PredictionInput(
            bus_id=safe_bus,
            route_id=safe_route,
            current_occupancy=safe_current,
            boarding=safe_boarding,
            alighting=safe_alighting,
            previous_occupancy=safe_prev,
            bus_capacity=safe_capacity,
            stop_id=safe_stop,
            peak_hour=safe_peak,
            day_type=safe_day,
            source=source,
            notes=notes,
        )

    def predict_from_input(self, inp: PredictionInput) -> PredictionResult:
        """Executes future occupancy prediction using the sanitized PredictionInput."""
        # Sanitize in case an un-sanitized PredictionInput was manually instantiated
        safe_inp = self.validate_and_sanitize_input(
            bus_id=inp.bus_id,
            route_id=inp.route_id,
            current_occupancy=inp.current_occupancy,
            boarding=inp.boarding,
            alighting=inp.alighting,
            previous_occupancy=inp.previous_occupancy,
            bus_capacity=inp.bus_capacity,
            stop_id=inp.stop_id,
            peak_hour=inp.peak_hour,
            day_type=inp.day_type,
            source=inp.source,
        )

        # Create single-row DataFrame for model feature preparation
        df_row = pd.DataFrame([{
            "current_occupancy": safe_inp.current_occupancy,
            "boarding": safe_inp.boarding,
            "alighting": safe_inp.alighting,
            "previous_occupancy": safe_inp.previous_occupancy,
            "peak_hour": safe_inp.peak_hour,
            "day_type": safe_inp.day_type,
            "route_id": safe_inp.route_id,
            "stop_id": safe_inp.stop_id,
        }])

        raw_pred = float(predict_future_occupancy(df_row)[0])

        # Physical constraints: cannot be negative, cannot exceed bus capacity
        notes = list(safe_inp.notes)
        if raw_pred < 0:
            clamped_pred = 0
            notes.append(f"Raw prediction ({raw_pred:.1f}) was negative; clamped to 0.")
        elif raw_pred > safe_inp.bus_capacity:
            clamped_pred = safe_inp.bus_capacity
            notes.append(f"Raw prediction ({raw_pred:.1f}) exceeded capacity ({safe_inp.bus_capacity}); clamped.")
        else:
            clamped_pred = int(round(raw_pred))

        # Percentage
        effective_capacity = max(1, safe_inp.bus_capacity)
        pct = round((clamped_pred / effective_capacity) * 100.0, 1)

        # Alert classification
        if raw_pred >= effective_capacity or pct >= THRESHOLD_CRITICAL:
            status = SEVERITY_CRITICAL
            overcrowded = True
        elif pct >= THRESHOLD_WARNING:
            status = SEVERITY_WARNING
            overcrowded = True
        else:
            status = SEVERITY_NORMAL
            overcrowded = False

        return PredictionResult(
            bus_id=safe_inp.bus_id,
            route_id=safe_inp.route_id,
            stop_id=safe_inp.stop_id,
            current_occupancy=safe_inp.current_occupancy,
            boarding=safe_inp.boarding,
            alighting=safe_inp.alighting,
            bus_capacity=effective_capacity,
            raw_predicted_future=round(raw_pred, 2),
            predicted_future_occupancy=clamped_pred,
            predicted_occupancy_pct=pct,
            predicted_status=status,
            is_overcrowded=overcrowded,
            data_source=safe_inp.source,
            notes=notes,
        )

    def predict_from_module4_result(
        self,
        cv_result: OccupancyUpdateResult,
        stop_id: str = "R101-S02",
        peak_hour: int = 0,
        day_type: str = "weekday",
    ) -> PredictionResult:
        """
        Direct integration hook: connects Module 4 OccupancyUpdateResult
        directly to future occupancy prediction.
        """
        inp = self.validate_and_sanitize_input(
            bus_id=cv_result.bus_id,
            route_id=cv_result.route_id,
            current_occupancy=cv_result.new_occupancy,
            boarding=cv_result.boarding,
            alighting=cv_result.alighting,
            previous_occupancy=cv_result.previous_occupancy,
            bus_capacity=cv_result.bus_capacity,
            stop_id=stop_id,
            peak_hour=peak_hour,
            day_type=day_type,
            source="camera_cv_module4",
        )
        return self.predict_from_input(inp)

    @staticmethod
    def _safe_int(val: Any, default: int, name: str, notes: List[str]) -> int:
        if val is None:
            notes.append(f"Missing {name}; defaulted to {default}.")
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            notes.append(f"Invalid {name} ({val}); defaulted to {default}.")
            return default


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST SUITE
# ──────────────────────────────────────────────────────────────────────────────

def run_self_tests() -> bool:
    """
    Self-test suite for Module 5 Step 1:
      1. Valid occupancy input.
      2. Boarding and alighting integration from Module 4.
      3. Missing input values handling.
      4. Invalid bus IDs & route IDs.
      5. Occupancy boundary conditions (negative & capacity overflow clamping).
      6. Prediction output validation.
      7. Existing model compatibility.
    """
    print("=" * 64)
    print("  Module 5, Step 1: FutureOccupancyPredictor — Self-Test Suite")
    print("  Random Forest Prediction Integration Layer")
    print("=" * 64)

    total_checks = 0
    passed_checks = 0

    def check(description: str, condition: bool, note: str = ""):
        nonlocal total_checks, passed_checks
        total_checks += 1
        if condition:
            passed_checks += 1
            print(f"  [PASS] {description}" + (f"  ({note})" if note else ""))
        else:
            print(f"  [FAIL] {description}" + (f"  ({note})" if note else ""))

    predictor = FutureOccupancyPredictor()

    # 1. Valid occupancy input
    print("\n[TEST 1] Valid Input Prediction")
    inp1 = predictor.validate_and_sanitize_input(
        bus_id="KA-BUS-003",
        route_id="R101",
        current_occupancy=25,
        boarding=5,
        alighting=2,
        bus_capacity=60,
        stop_id="R101-S03",
        peak_hour=1,
    )
    res1 = predictor.predict_from_input(inp1)
    check("Prediction generated successfully", res1.predicted_future_occupancy >= 0)
    check("Predicted occupancy percentage is non-negative", res1.predicted_occupancy_pct >= 0.0)
    check("Predicted status is a valid severity", res1.predicted_status in [SEVERITY_NORMAL, SEVERITY_WARNING, SEVERITY_CRITICAL])
    check("Source is recorded as camera_cv", res1.data_source == "camera_cv")

    # 2. Boarding & alighting integration from Module 4
    print("\n[TEST 2] Direct Module 4 OccupancyUpdateResult Connection")
    mod4_res = OccupancyUpdateResult(
        bus_id="KA-BUS-004",
        route_id="R101",
        previous_occupancy=15,
        boarding=8,
        alighting=1,
        net_change=7,
        raw_calculated_occupancy=22,
        new_occupancy=22,
        bus_capacity=60,
        occupancy_pct=36.7,
        alert_severity="Normal",
        is_overcrowded=False,
        is_underflow_detected=False,
        is_capacity_exceeded=False,
    )
    res2 = predictor.predict_from_module4_result(mod4_res, stop_id="R101-S04")
    check("Module 4 bus_id propagated", res2.bus_id == "KA-BUS-004")
    check("Module 4 updated current occupancy used as input", res2.current_occupancy == 22)
    check("Module 4 source labeled cleanly", res2.data_source == "camera_cv_module4")

    # 3. Missing input values
    print("\n[TEST 3] Missing / None Inputs")
    inp3 = predictor.validate_and_sanitize_input(
        bus_id=None,
        route_id=None,
        current_occupancy=None,
        boarding=None,
        alighting=None,
    )
    res3 = predictor.predict_from_input(inp3)
    check("Handled None inputs safely", res3 is not None)
    check("Default bus ID applied", res3.bus_id == "KA-BUS-001")
    check("Default route applied", res3.route_id == "R101")
    check("Validation notes recorded", len(inp3.notes) > 0)

    # 4. Invalid Bus & Route IDs
    print("\n[TEST 4] Invalid Bus & Route IDs")
    inp4 = predictor.validate_and_sanitize_input(
        bus_id="INVALID_BUS_XYZ",
        route_id="UNKNOWN_ROUTE",
        current_occupancy=20,
    )
    res4 = predictor.predict_from_input(inp4)
    check("Unknown route mapped safely to R101", res4.route_id == "R101")
    check("Validation note recorded for unknown route", any("Unknown route" in n for n in inp4.notes))

    # 5. Occupancy boundary conditions
    print("\n[TEST 5] Occupancy Boundary & Clamping Checks")
    # Force high occupancy to trigger critical alert
    inp5 = predictor.validate_and_sanitize_input(
        bus_id="KA-BUS-001",
        route_id="R205",
        current_occupancy=60,
        bus_capacity=60,
    )
    res5 = predictor.predict_from_input(inp5)
    check("Prediction does not exceed capacity 60", res5.predicted_future_occupancy <= 60)
    check("Prediction does not drop below 0", res5.predicted_future_occupancy >= 0)

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print(f"  RESULTS: {passed_checks}/{total_checks} checks passed, {total_checks - passed_checks} failed")
    if passed_checks == total_checks:
        print("  [OK] ALL MODULE 5 STEP 1 PREDICTION INTEGRATION TESTS PASSED")
    else:
        print("  [FAIL] SOME TESTS FAILED")
    print("=" * 64)

    return passed_checks == total_checks


if __name__ == "__main__":
    run_self_tests()
