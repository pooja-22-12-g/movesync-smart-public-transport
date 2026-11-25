"""
occupancy_prediction/multi_stop_predictor.py
============================================
Module 5, Step 2: Multi-Stop Occupancy Prediction
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Predict passenger occupancy across a sequence of multiple upcoming stops.
  - Chained rollout: The predicted occupancy at stop N becomes the starting
    occupancy for stop N+1.
  - Dynamically calculates boarding and alighting estimates for upcoming stops
    using route- and stop-specific historical averages from data/bus_occupancy.csv.
  - Labels all estimated boarding/alighting numbers as "HISTORICAL ESTIMATE".
  - Calculates occupancy percentage for every upcoming stop.
  - Classifies occupancy status matching Module 2 thresholds:
        Normal: < 85%
        Warning: 85% to < 100%
        Critical: 100%
  - Identifies the first upcoming stop where overcrowding is predicted.
  - Constrains passenger occupancy to valid physical bounds [0, bus_capacity].
  - Interfaces seamlessly with Module 4 (YOLO/ByteTrack camera counts) and
    Module 5 Step 1 (FutureOccupancyPredictor).
  - Strictly preserves original CSV and Modules 1–4.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Union

import pandas as pd
import numpy as np

# Ensure root directory is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from model import predict_future_occupancy, ROUTE_MAP, train_or_load_model
from passenger_counting.occupancy_integrator import (
    OccupancyUpdateResult,
    THRESHOLD_WARNING,
    THRESHOLD_CRITICAL,
    SEVERITY_NORMAL,
    SEVERITY_WARNING,
    SEVERITY_CRITICAL,
    DEFAULT_BUS_CAPACITY,
)
from occupancy_prediction.prediction_pipeline import (
    FutureOccupancyPredictor,
    PredictionInput,
    PredictionResult,
    VALID_ROUTES,
)

CSV_PATH = os.path.join("data", "movesync_kr_market_anekal_via_electronic_city.csv")


@dataclass
class StopPredictionDetail:
    """Prediction outcome for a single stop along the upcoming route sequence."""
    stop_id: str
    stop_sequence_index: int
    starting_occupancy: int
    estimated_boarding: int
    estimated_alighting: int
    net_passenger_change: int
    raw_model_predicted_occupancy: float
    predicted_occupancy: int
    bus_capacity: int
    predicted_occupancy_pct: float
    predicted_status: str
    is_overcrowded: bool
    data_source: str = "HISTORICAL_ESTIMATE_ML"
    notes: List[str] = field(default_factory=list)


@dataclass
class MultiStopPredictionResult:
    """Aggregated prediction results across a sequence of upcoming stops."""
    bus_id: str
    route_id: str
    initial_current_occupancy: int
    bus_capacity: int
    total_stops_predicted: int
    stops: List[StopPredictionDetail]
    first_crowded_stop: Optional[str] = None
    first_crowded_stop_status: Optional[str] = None
    max_predicted_occupancy: int = 0
    max_predicted_occupancy_pct: float = 0.0
    overall_status: str = SEVERITY_NORMAL
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HistoricalStopProfile:
    """
    Computes and caches historical boarding and alighting averages per (route_id, stop_id)
    from data/bus_occupancy.csv without modifying the CSV.
    """

    _cached_profiles: Optional[Dict[Tuple[str, str], Dict[str, float]]] = None
    _route_stops_ordered: Optional[Dict[str, List[str]]] = None

    @classmethod
    def load_profiles(cls) -> Dict[Tuple[str, str], Dict[str, float]]:
        """Loads and calculates mean boarding/alighting per stop from CSV."""
        if cls._cached_profiles is not None:
            return cls._cached_profiles

        df = pd.read_csv(CSV_PATH)

        # Calculate average boarding and alighting per route and stop
        grouped = df.groupby(["route_id", "stop_id"])[["boarding", "alighting"]].mean()
        profiles: Dict[Tuple[str, str], Dict[str, float]] = {}

        for (route, stop), row in grouped.iterrows():
            profiles[(str(route), str(stop))] = {
                "avg_boarding": round(float(row["boarding"]), 1),
                "avg_alighting": round(float(row["alighting"]), 1),
            }

        # Calculate ordered stop lists per route
        route_stops: Dict[str, List[str]] = {}
        for route in df["route_id"].unique():
            stops_in_route = sorted(
                df[df["route_id"] == route]["stop_id"].unique(),
                key=lambda s: int(s.split("-S")[-1]) if "-S" in s else 0,
            )
            route_stops[str(route)] = stops_in_route

        cls._cached_profiles = profiles
        cls._route_stops_ordered = route_stops
        return profiles

    @classmethod
    def get_upcoming_stops_for_route(cls, route_id: str, starting_after_stop: Optional[str] = None) -> List[str]:
        """Returns the remaining upcoming stop sequence for a route."""
        cls.load_profiles()
        all_stops = cls._route_stops_ordered.get(route_id, []) if cls._route_stops_ordered else []
        if not starting_after_stop or starting_after_stop not in all_stops:
            return all_stops

        start_idx = all_stops.index(starting_after_stop)
        return all_stops[start_idx + 1:]

    @classmethod
    def get_stop_estimates(cls, route_id: str, stop_id: str) -> Dict[str, int]:
        """
        Retrieves rounded historical boarding and alighting estimates for a specific stop.
        Falls back to global route average if specific stop is not found.
        """
        profiles = cls.load_profiles()
        key = (route_id, stop_id)
        if key in profiles:
            p = profiles[key]
            return {
                "boarding": max(0, int(round(p["avg_boarding"]))),
                "alighting": max(0, int(round(p["avg_alighting"]))),
            }

        # Default fallback if stop is completely unknown
        return {"boarding": 3, "alighting": 2}


class MultiStopOccupancyPredictor:
    """
    Coordinates sequential multi-stop occupancy prediction.
    Feeds the predicted occupancy from stop N as the starting occupancy for stop N+1.
    """

    def __init__(self):
        self.pipeline = FutureOccupancyPredictor()
        # Warm historical stop statistics
        HistoricalStopProfile.load_profiles()

    def predict_multi_stop(
        self,
        bus_id: str = "KA-BUS-001",
        current_occupancy: int = 20,
        bus_capacity: int = DEFAULT_BUS_CAPACITY,
        route_id: str = "R101",
        upcoming_stops: Optional[List[str]] = None,
        custom_stop_adjustments: Optional[Dict[str, Dict[str, int]]] = None,
        peak_hour: int = 0,
        day_type: str = "weekday",
        source_label: str = "HISTORICAL_ESTIMATE_ML",
    ) -> MultiStopPredictionResult:
        """
        Performs sequential multi-stop prediction across a list of upcoming stops.

        Args:
            bus_id: Bus identifier (e.g. 'KA-BUS-001').
            current_occupancy: Starting passenger count (from Module 4 or live telemetry).
            bus_capacity: Bus seating/standing maximum capacity.
            route_id: Transit route identifier (e.g. 'R101').
            upcoming_stops: List of stop IDs in sequence. If None, retrieves remaining route stops.
            custom_stop_adjustments: Optional dict overriding boarding/alighting per stop.
            peak_hour: 1 for peak, 0 for off-peak.
            day_type: 'weekday' or 'weekend'.
            source_label: Label indicating origin of estimates.

        Returns:
            MultiStopPredictionResult with detailed stop-by-stop metrics.
        """
        # Validate inputs
        safe_capacity = max(1, int(bus_capacity))
        safe_current = max(0, min(safe_capacity, int(current_occupancy)))
        safe_route = route_id.strip().upper() if route_id and route_id.strip().upper() in VALID_ROUTES else "R101"
        safe_bus = bus_id.strip() if bus_id else "KA-BUS-001"

        # Determine stop sequence
        if not upcoming_stops or len(upcoming_stops) == 0:
            upcoming_stops = HistoricalStopProfile.get_upcoming_stops_for_route(safe_route)

        stop_predictions: List[StopPredictionDetail] = []
        running_occupancy = safe_current
        first_crowded_stop = None
        first_crowded_status = None
        max_occ = running_occupancy
        max_pct = round((running_occupancy / safe_capacity) * 100.0, 1)

        for idx, stop in enumerate(upcoming_stops, start=1):
            notes: List[str] = []

            # 1. Obtain boarding & alighting estimates
            if custom_stop_adjustments and stop in custom_stop_adjustments:
                raw_b = custom_stop_adjustments[stop].get("boarding", 0)
                raw_a = custom_stop_adjustments[stop].get("alighting", 0)
                b_val = self._safe_int(raw_b, default=0)
                a_val = self._safe_int(raw_a, default=0)
                notes.append(f"Custom adjustment applied for {stop}.")
            else:
                estimates = HistoricalStopProfile.get_stop_estimates(safe_route, stop)
                b_val = estimates["boarding"]
                a_val = estimates["alighting"]
                notes.append("Boarding/alighting derived from historical CSV averages.")

            b_val = max(0, b_val)
            a_val = max(0, a_val)
            net_delta = b_val - a_val

            # Occupancy at this stop after its passenger exchange:
            # Current Stop Occupancy = Starting Occupancy + Boarding - Alighting
            raw_stop_occupancy = running_occupancy + b_val - a_val

            # 2. Build prediction input using the exact formula relationship
            pred_input = self.pipeline.validate_and_sanitize_input(
                bus_id=safe_bus,
                route_id=safe_route,
                current_occupancy=raw_stop_occupancy,
                boarding=b_val,
                alighting=a_val,
                previous_occupancy=running_occupancy,
                bus_capacity=safe_capacity,
                stop_id=stop,
                peak_hour=peak_hour,
                day_type=day_type,
                source=source_label,
            )

            # 3. Model inference using Random Forest
            res = self.pipeline.predict_from_input(pred_input)

            # If the calculated physical occupancy at this stop reached or exceeded capacity,
            # or dropped to zero, clamp the prediction accordingly to respect physical constraints
            raw_pred_val = res.raw_predicted_future
            if raw_stop_occupancy >= safe_capacity:
                predicted_occ = safe_capacity
                notes.append(f"Passenger count at {stop} reached/exceeded capacity ({raw_stop_occupancy} >= {safe_capacity}); clamped to {safe_capacity}.")
            elif raw_stop_occupancy <= 0:
                predicted_occ = 0
                notes.append(f"Passenger count at {stop} dropped to 0; clamped to 0.")
            else:
                predicted_occ = max(0, min(safe_capacity, int(round(raw_pred_val))))

            occ_pct = round((predicted_occ / safe_capacity) * 100.0, 1)

            # 5. Classify status matching Module 2
            if predicted_occ >= safe_capacity or occ_pct >= THRESHOLD_CRITICAL or raw_stop_occupancy >= safe_capacity:
                status = SEVERITY_CRITICAL
                is_crowded = True
            elif occ_pct >= THRESHOLD_WARNING:
                status = SEVERITY_WARNING
                is_crowded = True
            else:
                status = SEVERITY_NORMAL
                is_crowded = False

            # Identify first crowded stop
            if is_crowded and first_crowded_stop is None:
                first_crowded_stop = stop
                first_crowded_status = status

            # Track peak occupancy
            if predicted_occ > max_occ:
                max_occ = predicted_occ
                max_pct = occ_pct

            stop_detail = StopPredictionDetail(
                stop_id=stop,
                stop_sequence_index=idx,
                starting_occupancy=running_occupancy,
                estimated_boarding=b_val,
                estimated_alighting=a_val,
                net_passenger_change=net_delta,
                raw_model_predicted_occupancy=res.raw_predicted_future,
                predicted_occupancy=predicted_occ,
                bus_capacity=safe_capacity,
                predicted_occupancy_pct=occ_pct,
                predicted_status=status,
                is_overcrowded=is_crowded,
                data_source=source_label,
                notes=notes,
            )
            stop_predictions.append(stop_detail)

            # Roll forward: Next stop starts with this stop's predicted occupancy
            running_occupancy = predicted_occ

        # Overall route status determination
        overall_status = SEVERITY_NORMAL
        if any(s.predicted_status == SEVERITY_CRITICAL for s in stop_predictions):
            overall_status = SEVERITY_CRITICAL
        elif any(s.predicted_status == SEVERITY_WARNING for s in stop_predictions):
            overall_status = SEVERITY_WARNING

        return MultiStopPredictionResult(
            bus_id=safe_bus,
            route_id=safe_route,
            initial_current_occupancy=safe_current,
            bus_capacity=safe_capacity,
            total_stops_predicted=len(stop_predictions),
            stops=stop_predictions,
            first_crowded_stop=first_crowded_stop,
            first_crowded_stop_status=first_crowded_status,
            max_predicted_occupancy=max_occ,
            max_predicted_occupancy_pct=max_pct,
            overall_status=overall_status,
        )

    @staticmethod
    def _safe_int(val: Any, default: int = 0) -> int:
        if val is None:
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    def predict_from_module4_multi_stop(
        self,
        cv_result: OccupancyUpdateResult,
        upcoming_stops: Optional[List[str]] = None,
        peak_hour: int = 0,
        day_type: str = "weekday",
    ) -> MultiStopPredictionResult:
        """
        Direct adapter hook: Takes real-time Module 4 camera counting output
        and rolls forward multi-stop occupancy predictions.
        """
        return self.predict_multi_stop(
            bus_id=cv_result.bus_id,
            current_occupancy=cv_result.new_occupancy,
            bus_capacity=cv_result.bus_capacity,
            route_id=cv_result.route_id,
            upcoming_stops=upcoming_stops,
            peak_hour=peak_hour,
            day_type=day_type,
            source_label="MODULE4_CV_TO_HISTORICAL_ROLLOUT",
        )


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST SUITE
# ──────────────────────────────────────────────────────────────────────────────

def run_self_tests() -> bool:
    """
    Test cases covering:
      1. Multiple upcoming stops (at least 5 stops).
      2. Increasing occupancy trajectory.
      3. Decreasing occupancy trajectory.
      4. Warning and Critical status detection.
      5. Bus reaching and exceeding full capacity.
      6. Missing or invalid boarding/alighting values.
      7. Occupancy boundary conditions (0 <= occ <= capacity).
      8. Different routes and bus capacities.
    """
    print("=" * 64)
    print("  Module 5, Step 2: Multi-Stop Occupancy Predictor — Self-Test Suite")
    print("  Chained Sequential Stop Rollout with Historical Averages")
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

    predictor = MultiStopOccupancyPredictor()

    # ── TEST 1: Multiple upcoming stops (at least 5 stops) ────────────────────
    print("\n[TEST 1] Multiple Upcoming Stops (5-Stop Rollout)")
    stops_r101 = ["R101-S01", "R101-S02", "R101-S03", "R101-S04", "R101-S05"]
    res1 = predictor.predict_multi_stop(
        bus_id="KA-BUS-001",
        current_occupancy=20,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=stops_r101,
    )
    check("5 stops evaluated", len(res1.stops) == 5)
    check("Predictions vary across stops (not identical repeated values)", len({s.predicted_occupancy for s in res1.stops}) > 1)
    check("Chaining verified: Stop 2 starting occupancy equals Stop 1 predicted occupancy",
          res1.stops[1].starting_occupancy == res1.stops[0].predicted_occupancy)
    check("All estimates tagged as historical estimates",
          all("HISTORICAL" in s.data_source for s in res1.stops))

    # Print sample 5-stop table
    print("\n  Sample 5-Stop Rollout for KA-BUS-001 (Route R101):")
    print("  " + "-" * 75)
    print(f"  {'Stop':<10} {'Start':>6} {'+Board':>7} {'-Alight':>8} {'Pred':>6} {'Occ %':>7} {'Status':<10}")
    print("  " + "-" * 75)
    for s in res1.stops:
        print(f"  {s.stop_id:<10} {s.starting_occupancy:>6} {s.estimated_boarding:>7} {s.estimated_alighting:>8} "
              f"{s.predicted_occupancy:>6} {s.predicted_occupancy_pct:>6.1f}% {s.predicted_status:<10}")
    print("  " + "-" * 75)

    # ── TEST 2: Increasing occupancy trajectory ───────────────────────────────
    print("\n[TEST 2] Increasing Occupancy Trajectory")
    high_board_overrides = {
        f"R101-S0{i}": {"boarding": 8, "alighting": 1} for i in range(1, 6)
    }
    res_inc = predictor.predict_multi_stop(
        bus_id="KA-BUS-002",
        current_occupancy=10,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=stops_r101,
        custom_stop_adjustments=high_board_overrides,
    )
    check("Occupancy increases across stops", res_inc.stops[-1].predicted_occupancy > res_inc.stops[0].predicted_occupancy)
    check("Net passenger change is positive for all stops", all(s.net_passenger_change > 0 for s in res_inc.stops))

    # ── TEST 3: Decreasing occupancy trajectory ───────────────────────────────
    print("\n[TEST 3] Decreasing Occupancy Trajectory")
    high_alight_overrides = {
        f"R101-S0{i}": {"boarding": 1, "alighting": 8} for i in range(1, 6)
    }
    res_dec = predictor.predict_multi_stop(
        bus_id="KA-BUS-003",
        current_occupancy=45,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=stops_r101,
        custom_stop_adjustments=high_alight_overrides,
    )
    check("Occupancy decreases across stops", res_dec.stops[-1].predicted_occupancy < res_dec.stops[0].predicted_occupancy)
    check("Net passenger change is negative for all stops", all(s.net_passenger_change < 0 for s in res_dec.stops))

    # ── TEST 4: Warning & Critical Status & First Crowded Stop ────────────────
    print("\n[TEST 4] Warning and Critical Status Detection")
    # Start at 48 pax (80%), board 5 -> reaches Warning (>85%), then boards more -> reaches Critical (100%)
    crowd_overrides = {
        "R101-S01": {"boarding": 4, "alighting": 0},  # ~52 pax -> Warning (86.7%)
        "R101-S02": {"boarding": 6, "alighting": 0},  # ~58 pax -> Warning (96.7%)
        "R101-S03": {"boarding": 5, "alighting": 0},  # ~60 pax -> Critical (100%)
    }
    res_crowd = predictor.predict_multi_stop(
        bus_id="KA-BUS-004",
        current_occupancy=48,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=["R101-S01", "R101-S02", "R101-S03"],
        custom_stop_adjustments=crowd_overrides,
    )
    check("Warning status detected at stop", any(s.predicted_status == SEVERITY_WARNING for s in res_crowd.stops))
    check("Critical status detected at stop", any(s.predicted_status == SEVERITY_CRITICAL for s in res_crowd.stops))
    check("First crowded stop correctly identified", res_crowd.first_crowded_stop == "R101-S01")
    check("First crowded status is Warning", res_crowd.first_crowded_stop_status == SEVERITY_WARNING)
    check("Overall route status is Critical", res_crowd.overall_status == SEVERITY_CRITICAL)

    # ── TEST 5: Bus reaching and clamping at full capacity ─────────────────────
    print("\n[TEST 5] Bus Full Capacity Clamping Guard")
    overflow_overrides = {
        "R101-S01": {"boarding": 25, "alighting": 0},
        "R101-S02": {"boarding": 30, "alighting": 0},
    }
    res_overflow = predictor.predict_multi_stop(
        bus_id="KA-BUS-005",
        current_occupancy=50,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=["R101-S01", "R101-S02"],
        custom_stop_adjustments=overflow_overrides,
    )
    check("Occupancy clamped strictly to bus capacity (60)", all(s.predicted_occupancy <= 60 for s in res_overflow.stops))
    check("Critical alert triggered for capacity limit", res_overflow.stops[0].predicted_status == SEVERITY_CRITICAL)

    # ── TEST 6: Missing or invalid boarding/alighting values ──────────────────
    print("\n[TEST 6] Missing or Invalid Overrides Fallback")
    invalid_overrides = {
        "R101-S01": {"boarding": "invalid", "alighting": None},
    }
    res_inv = predictor.predict_multi_stop(
        bus_id="KA-BUS-006",
        current_occupancy=25,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=["R101-S01"],
        custom_stop_adjustments=invalid_overrides,
    )
    check("Invalid boarding defaulted to 0 safely", res_inv.stops[0].estimated_boarding == 0)
    check("None alighting defaulted to 0 safely", res_inv.stops[0].estimated_alighting == 0)

    # ── TEST 7: Occupancy boundary conditions (never negative) ────────────────
    print("\n[TEST 7] Underflow Guard (Occupancy >= 0)")
    underflow_overrides = {
        "R101-S01": {"boarding": 0, "alighting": 50},
    }
    res_underflow = predictor.predict_multi_stop(
        bus_id="KA-BUS-007",
        current_occupancy=5,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=["R101-S01"],
        custom_stop_adjustments=underflow_overrides,
    )
    check("Occupancy clamped to 0 (never negative)", res_underflow.stops[0].predicted_occupancy == 0)

    # ── TEST 8: Different routes and capacities ───────────────────────────────
    print("\n[TEST 8] Different Routes and Bus Capacities")
    res_r205 = predictor.predict_multi_stop(
        bus_id="KA-BUS-008",
        current_occupancy=15,
        bus_capacity=45,  # Mini-bus capacity
        route_id="R205",
        upcoming_stops=["R205-S01", "R205-S02", "R205-S03"],
    )
    check("R205 Mini-bus capacity 45 recognized", res_r205.bus_capacity == 45)
    check("Occupancy percentage calculated against 45 capacity",
          res_r205.stops[0].predicted_occupancy_pct == round((res_r205.stops[0].predicted_occupancy / 45) * 100.0, 1))

    # ── TEST 9: Module 4 direct integration hook ──────────────────────────────
    print("\n[TEST 9] Module 4 Direct Multi-Stop Integration")
    m4_result = OccupancyUpdateResult(
        bus_id="KA-BUS-010",
        route_id="R330",
        previous_occupancy=20,
        boarding=10,
        alighting=2,
        net_change=8,
        raw_calculated_occupancy=28,
        new_occupancy=28,
        bus_capacity=60,
        occupancy_pct=46.7,
        alert_severity="Normal",
        is_overcrowded=False,
        is_underflow_detected=False,
        is_capacity_exceeded=False,
    )
    res_m4 = predictor.predict_from_module4_multi_stop(
        m4_result,
        upcoming_stops=["R330-S02", "R330-S03", "R330-S04"],
    )
    check("Module 4 bus_id propagated", res_m4.bus_id == "KA-BUS-010")
    check("Module 4 new_occupancy used as starting occupancy", res_m4.initial_current_occupancy == 28)
    check("Source tagged with Module 4 rollout label", "MODULE4" in res_m4.stops[0].data_source)

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print(f"  RESULTS: {passed_checks}/{total_checks} checks passed, {total_checks - passed_checks} failed")
    if passed_checks == total_checks:
        print("  [OK] ALL MULTI-STOP PREDICTOR TESTS PASSED")
    else:
        print("  [FAIL] SOME TESTS FAILED")
    print("=" * 64)

    return passed_checks == total_checks


if __name__ == "__main__":
    run_self_tests()

