"""
occupancy_prediction/crowding_forecaster.py
==========================================
Module 5, Step 3: Crowding Forecasting & Early Warning System
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Analyze multi-stop occupancy predictions from multi_stop_predictor.py.
  - Detect advance overcrowding thresholds across the upcoming route sequence:
        Warning: >= 85% to < 100%
        Critical: >= 100% (or reaching full seating capacity)
  - Calculate early-warning lead times:
        * First warning stop ID and stops remaining until warning.
        * First critical stop ID and stops remaining until critical.
  - Generate clear, actionable operational dispatch messages for transport authorities
    and passenger-facing advisory notices.
  - Classify overall forecast condition:
        * Normal: no upcoming stop breaches 85%.
        * Warning: at least one stop breaches 85% but remains below 100%.
        * Critical: at least one stop reaches 100% (or capacity).
  - Explicitly identify full capacity exhaustion stops.
  - Distinguish historical estimates from live camera/sensor observations.
  - Provide structured result classes for dashboard presentation.
  - Reuses existing multi_stop_predictor.py and model.py (strictly no duplicate ML models).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

# Ensure root directory is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from passenger_counting.occupancy_integrator import (
    THRESHOLD_WARNING,
    THRESHOLD_CRITICAL,
    SEVERITY_NORMAL,
    SEVERITY_WARNING,
    SEVERITY_CRITICAL,
    DEFAULT_BUS_CAPACITY,
)
from occupancy_prediction.multi_stop_predictor import (
    MultiStopOccupancyPredictor,
    MultiStopPredictionResult,
    StopPredictionDetail,
)


@dataclass
class EarlyWarningNotice:
    """Actionable warning advisory generated for transport controllers."""
    level: str  # 'NORMAL', 'WARNING', 'CRITICAL'
    headline: str
    authority_action_message: str
    passenger_advice_message: str
    first_warning_stop: Optional[str] = None
    stops_to_warning: Optional[int] = None
    first_critical_stop: Optional[str] = None
    stops_to_critical: Optional[int] = None
    full_capacity_stop: Optional[str] = None


@dataclass
class CrowdingForecastResult:
    """Structured result containing multi-stop forecasts and early warning metrics."""
    bus_id: str
    route_id: str
    current_occupancy: int
    bus_capacity: int
    current_occupancy_pct: float
    current_status: str
    forecast_condition: str  # 'Normal', 'Warning', 'Critical'
    first_warning_stop: Optional[str] = None
    stops_until_warning: Optional[int] = None
    first_critical_stop: Optional[str] = None
    stops_until_critical: Optional[int] = None
    full_capacity_reached: bool = False
    full_capacity_stop: Optional[str] = None
    max_predicted_occupancy: int = 0
    max_predicted_occupancy_pct: float = 0.0
    total_stops_evaluated: int = 0
    early_warning: EarlyWarningNotice = field(default_factory=lambda: EarlyWarningNotice(
        level="NORMAL",
        headline="Normal fleet conditions",
        authority_action_message="Standard operations; no action required.",
        passenger_advice_message="Plenty of seating available.",
    ))
    stop_forecasts: List[Dict[str, Any]] = field(default_factory=list)
    data_provenance: str = "HISTORICAL_ESTIMATES_ML"
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CrowdingForecaster:
    """
    Forecasting and early warning engine. Analyzes upcoming stop predictions,
    calculates warning horizons, and produces actionable operational advice.
    """

    def __init__(self, predictor: Optional[MultiStopOccupancyPredictor] = None):
        self.predictor = predictor or MultiStopOccupancyPredictor()

    def forecast_from_multi_stop_result(
        self,
        multi_stop_result: MultiStopPredictionResult,
    ) -> CrowdingForecastResult:
        """
        Analyzes an existing MultiStopPredictionResult and extracts early warning metrics.
        """
        bus_id = multi_stop_result.bus_id
        route_id = multi_stop_result.route_id
        capacity = max(1, multi_stop_result.bus_capacity)
        curr_occ = max(0, min(capacity, multi_stop_result.initial_current_occupancy))
        curr_pct = round((curr_occ / capacity) * 100.0, 1)

        # Current status classification
        if curr_occ >= capacity or curr_pct >= THRESHOLD_CRITICAL:
            curr_status = SEVERITY_CRITICAL
        elif curr_pct >= THRESHOLD_WARNING:
            curr_status = SEVERITY_WARNING
        else:
            curr_status = SEVERITY_NORMAL

        stops = multi_stop_result.stops or []
        first_warn_stop = None
        stops_to_warn = None
        first_crit_stop = None
        stops_to_crit = None
        full_cap_stop = None
        full_cap_reached = False

        max_occ = curr_occ
        max_pct = curr_pct
        stop_summaries = []

        for idx, s in enumerate(stops, start=1):
            occ = s.predicted_occupancy
            pct = s.predicted_occupancy_pct
            status = s.predicted_status

            if occ > max_occ:
                max_occ = occ
                max_pct = pct

            # Check Warning (>= 85%)
            if pct >= THRESHOLD_WARNING and first_warn_stop is None:
                first_warn_stop = s.stop_id
                stops_to_warn = idx

            # Check Critical (>= 100% or capacity)
            if (pct >= THRESHOLD_CRITICAL or occ >= capacity) and first_crit_stop is None:
                first_crit_stop = s.stop_id
                stops_to_crit = idx
                full_cap_stop = s.stop_id
                full_cap_reached = True

            stop_summaries.append({
                "stop_id": s.stop_id,
                "sequence_index": idx,
                "starting_occupancy": s.starting_occupancy,
                "estimated_boarding": s.estimated_boarding,
                "estimated_alighting": s.estimated_alighting,
                "predicted_occupancy": occ,
                "predicted_occupancy_pct": pct,
                "predicted_status": status,
                "is_overcrowded": s.is_overcrowded,
                "data_source": s.data_source,
            })

        # Determine overall forecast condition
        if first_crit_stop is not None or curr_status == SEVERITY_CRITICAL:
            forecast_cond = SEVERITY_CRITICAL
        elif first_warn_stop is not None or curr_status == SEVERITY_WARNING:
            forecast_cond = SEVERITY_WARNING
        else:
            forecast_cond = SEVERITY_NORMAL

        # Generate warning notices
        notice = self._generate_early_warning_notice(
            bus_id=bus_id,
            route_id=route_id,
            condition=forecast_cond,
            capacity=capacity,
            max_occ=max_occ,
            max_pct=max_pct,
            first_warn_stop=first_warn_stop,
            stops_to_warn=stops_to_warn,
            first_crit_stop=first_crit_stop,
            stops_to_crit=stops_to_crit,
        )

        return CrowdingForecastResult(
            bus_id=bus_id,
            route_id=route_id,
            current_occupancy=curr_occ,
            bus_capacity=capacity,
            current_occupancy_pct=curr_pct,
            current_status=curr_status,
            forecast_condition=forecast_cond,
            first_warning_stop=first_warn_stop,
            stops_until_warning=stops_to_warn,
            first_critical_stop=first_crit_stop,
            stops_until_critical=stops_to_crit,
            full_capacity_reached=full_cap_reached,
            full_capacity_stop=full_cap_stop,
            max_predicted_occupancy=max_occ,
            max_predicted_occupancy_pct=max_pct,
            total_stops_evaluated=len(stops),
            early_warning=notice,
            stop_forecasts=stop_summaries,
            data_provenance="HISTORICAL_ESTIMATES_ML (Predicted via Random Forest)",
        )

    def forecast_upcoming_occupancy(
        self,
        bus_id: str = "KA-BUS-001",
        current_occupancy: int = 20,
        bus_capacity: int = DEFAULT_BUS_CAPACITY,
        route_id: str = "R101",
        upcoming_stops: Optional[List[str]] = None,
        custom_stop_adjustments: Optional[Dict[str, Dict[str, int]]] = None,
        peak_hour: int = 0,
        day_type: str = "weekday",
    ) -> CrowdingForecastResult:
        """
        Coordinates full multi-stop prediction and immediately evaluates early warnings.
        """
        # Execute multi-stop predictor
        ms_res = self.predictor.predict_multi_stop(
            bus_id=bus_id,
            current_occupancy=current_occupancy,
            bus_capacity=bus_capacity,
            route_id=route_id,
            upcoming_stops=upcoming_stops,
            custom_stop_adjustments=custom_stop_adjustments,
            peak_hour=peak_hour,
            day_type=day_type,
            source_label="HISTORICAL_ESTIMATE_ML",
        )
        return self.forecast_from_multi_stop_result(ms_res)

    def _generate_early_warning_notice(
        self,
        bus_id: str,
        route_id: str,
        condition: str,
        capacity: int,
        max_occ: int,
        max_pct: float,
        first_warn_stop: Optional[str],
        stops_to_warn: Optional[int],
        first_crit_stop: Optional[str],
        stops_to_crit: Optional[int],
    ) -> EarlyWarningNotice:
        """Constructs human-readable messages for control authorities and passengers."""
        if condition == SEVERITY_CRITICAL:
            lead = f"in {stops_to_crit} stops" if stops_to_crit and stops_to_crit > 1 else "at the next stop"
            stop_str = f"at {first_crit_stop}" if first_crit_stop else ""

            headline = f"CRITICAL OVERCROWDING FORECAST for Bus {bus_id} ({route_id})"
            auth_msg = (
                f"🚨 URGENT: Bus {bus_id} is forecast to hit full capacity ({max_occ}/{capacity} pax, {max_pct}%) "
                f"{stop_str} {lead}. Recommend dispatching an auxiliary relief bus on {route_id} or advising "
                f"station marshals to manage boarding queues."
            )
            pax_msg = (
                f"Bus {bus_id} on route {route_id} is expected to be completely full {stop_str}. "
                f"Passengers are advised to consider the next scheduled bus."
            )
            level = "CRITICAL"

        elif condition == SEVERITY_WARNING:
            lead = f"in {stops_to_warn} stops" if stops_to_warn and stops_to_warn > 1 else "at the next stop"
            stop_str = f"at {first_warn_stop}" if first_warn_stop else ""

            headline = f"HIGH OCCUPANCY WARNING FORECAST for Bus {bus_id} ({route_id})"
            auth_msg = (
                f"⚠️ ADVISORY: Bus {bus_id} is forecast to exceed {THRESHOLD_WARNING:.0f}% capacity "
                f"({max_occ}/{capacity} pax, {max_pct}%) {stop_str} {lead}. Monitor incoming boarding "
                f"and consider dynamic headway adjustments."
            )
            pax_msg = (
                f"Bus {bus_id} on route {route_id} will have limited seat availability {stop_str} ({max_pct}% full)."
            )
            level = "WARNING"

        else:
            headline = f"Normal Operating Conditions for Bus {bus_id} ({route_id})"
            auth_msg = (
                f"🟢 Fleet status normal. Peak predicted occupancy is {max_occ}/{capacity} ({max_pct}%), "
                f"well within comfortable passenger limits. No intervention needed."
            )
            pax_msg = f"Seating is comfortably available on Bus {bus_id} across all upcoming stops."
            level = "NORMAL"

        return EarlyWarningNotice(
            level=level,
            headline=headline,
            authority_action_message=auth_msg,
            passenger_advice_message=pax_msg,
            first_warning_stop=first_warn_stop,
            stops_to_warning=stops_to_warn,
            first_critical_stop=first_crit_stop,
            stops_to_critical=stops_to_crit,
            full_capacity_stop=first_crit_stop if condition == SEVERITY_CRITICAL else None,
        )


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST SUITE
# ──────────────────────────────────────────────────────────────────────────────

def run_self_tests() -> bool:
    """
    Test cases covering:
      1. No overcrowding forecast (Normal).
      2. Warning at an upcoming stop (Warning).
      3. Critical at an upcoming stop (Critical).
      4. Bus reaching full capacity (100%).
      5. Increasing occupancy trajectory.
      6. Decreasing occupancy trajectory.
      7. Missing or empty prediction data.
      8. Invalid stop sequences.
      9. Different bus capacities.
      10. Integration with existing MultiStopOccupancyPredictor.
    """
    print("=" * 64)
    print("  Module 5, Step 3: CrowdingForecaster — Self-Test Suite")
    print("  Early Warning Horizon & Advisory Generation")
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

    forecaster = CrowdingForecaster()

    # ── TEST 1: No Overcrowding Forecast (Normal) ─────────────────────────────
    print("\n[TEST 1] No Overcrowding Forecast (Normal)")
    res_normal = forecaster.forecast_upcoming_occupancy(
        bus_id="KA-BUS-001",
        current_occupancy=15,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=["R101-S01", "R101-S02", "R101-S03"],
    )
    check("Forecast condition is Normal", res_normal.forecast_condition == SEVERITY_NORMAL)
    check("First warning stop is None", res_normal.first_warning_stop is None)
    check("First critical stop is None", res_normal.first_critical_stop is None)
    check("Notice level is NORMAL", res_normal.early_warning.level == "NORMAL")
    check("Authority message confirms normal operations", "normal" in res_normal.early_warning.authority_action_message.lower())

    # ── TEST 2: Warning at an Upcoming Stop ───────────────────────────────────
    print("\n[TEST 2] Warning at an Upcoming Stop")
    # Starts at 35 pax (58%), at Stop 1: 40 pax, at Stop 2: reaches Warning (52 pax = 86.7%)
    warn_overrides = {
        "R101-S01": {"boarding": 5, "alighting": 0},  # ~40 pax (66.7%) -> Normal
        "R101-S02": {"boarding": 12, "alighting": 0}, # ~52 pax (86.7%) -> Warning
        "R101-S03": {"boarding": 1, "alighting": 2},  # ~51 pax -> Warning
    }
    res_warn = forecaster.forecast_upcoming_occupancy(
        bus_id="KA-BUS-002",
        current_occupancy=35,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=["R101-S01", "R101-S02", "R101-S03"],
        custom_stop_adjustments=warn_overrides,
    )
    check("Forecast condition is Warning", res_warn.forecast_condition == SEVERITY_WARNING)
    check("First warning stop identified correctly as R101-S02", res_warn.first_warning_stop == "R101-S02")
    check("Stops remaining until warning is 2", res_warn.stops_until_warning == 2)
    check("First critical stop remains None", res_warn.first_critical_stop is None)
    check("Notice level is WARNING", res_warn.early_warning.level == "WARNING")

    # Print sample Warning notice
    print("\n  Sample Warning Forecast Notice:")
    print(f"  Headline : {res_warn.early_warning.headline}")
    print(f"  Authority: {res_warn.early_warning.authority_action_message}")
    print(f"  Passenger: {res_warn.early_warning.passenger_advice_message}\n")

    # ── TEST 3: Critical at an Upcoming Stop & Full Capacity ───────────────────
    print("\n[TEST 3] Critical Overcrowding and Full Capacity Reached")
    # Starts at 35 pax, at Stop 1: ~40 pax, at Stop 2: ~52 pax (Warning), at Stop 3: reaches 60 pax (Critical)
    crit_overrides = {
        "R101-S01": {"boarding": 5, "alighting": 0},  # ~40 pax -> Normal
        "R101-S02": {"boarding": 12, "alighting": 0}, # ~52 pax -> Warning
        "R101-S03": {"boarding": 10, "alighting": 0}, # ~60 pax -> Critical (full capacity)
    }
    res_crit = forecaster.forecast_upcoming_occupancy(
        bus_id="KA-BUS-003",
        current_occupancy=35,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=["R101-S01", "R101-S02", "R101-S03"],
        custom_stop_adjustments=crit_overrides,
    )
    check("Forecast condition is Critical", res_crit.forecast_condition == SEVERITY_CRITICAL)
    check("First warning stop identified (R101-S02)", res_crit.first_warning_stop == "R101-S02")
    check("Stops until warning is 2", res_crit.stops_until_warning == 2)
    check("First critical stop identified (R101-S03)", res_crit.first_critical_stop == "R101-S03")
    check("Stops until critical is 3", res_crit.stops_until_critical == 3)
    check("Full capacity reached flag is True", res_crit.full_capacity_reached)
    check("Full capacity stop is R101-S03", res_crit.full_capacity_stop == "R101-S03")
    check("Notice level is CRITICAL", res_crit.early_warning.level == "CRITICAL")
    check("Authority message advises relief bus", "relief bus" in res_crit.early_warning.authority_action_message.lower())

    # Print sample Critical notice
    print("\n  Sample Critical Forecast Notice:")
    print(f"  Headline : {res_crit.early_warning.headline}")
    print(f"  Authority: {res_crit.early_warning.authority_action_message}")
    print(f"  Passenger: {res_crit.early_warning.passenger_advice_message}\n")

    # ── TEST 4: Increasing Occupancy Trajectory ───────────────────────────────
    print("\n[TEST 4] Increasing Occupancy Trajectory")
    res_inc = forecaster.forecast_upcoming_occupancy(
        bus_id="KA-BUS-004",
        current_occupancy=10,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=["R101-S01", "R101-S02", "R101-S03"],
        custom_stop_adjustments={
            f"R101-S0{i}": {"boarding": 8, "alighting": 1} for i in range(1, 4)
        },
    )
    check("Occupancy trend increases", res_inc.max_predicted_occupancy > res_inc.current_occupancy)

    # ── TEST 5: Decreasing Occupancy Trajectory ───────────────────────────────
    print("\n[TEST 5] Decreasing Occupancy Trajectory")
    res_dec = forecaster.forecast_upcoming_occupancy(
        bus_id="KA-BUS-005",
        current_occupancy=50,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=["R101-S01", "R101-S02", "R101-S03"],
        custom_stop_adjustments={
            f"R101-S0{i}": {"boarding": 1, "alighting": 10} for i in range(1, 4)
        },
    )
    check("Decreasing trend ends below starting occupancy", res_dec.stop_forecasts[-1]["predicted_occupancy"] < res_dec.current_occupancy)

    # ── TEST 6: Missing / Empty Prediction Data Handling ──────────────────────
    print("\n[TEST 6] Missing & Empty Prediction Handling")
    empty_result = MultiStopPredictionResult(
        bus_id="KA-BUS-006",
        route_id="R101",
        initial_current_occupancy=20,
        bus_capacity=60,
        total_stops_predicted=0,
        stops=[],
    )
    res_empty = forecaster.forecast_from_multi_stop_result(empty_result)
    check("Empty stop result handled safely without exception", res_empty is not None)
    check("Forecast condition defaults to Normal", res_empty.forecast_condition == SEVERITY_NORMAL)

    # ── TEST 7: Invalid Stop Sequences Fallback ───────────────────────────────
    print("\n[TEST 7] Invalid Stop Sequences Handling")
    res_inv = forecaster.forecast_upcoming_occupancy(
        bus_id="KA-BUS-007",
        current_occupancy=25,
        bus_capacity=60,
        route_id="R101",
        upcoming_stops=["UNKNOWN_STOP_1", "UNKNOWN_STOP_2"],
    )
    check("Unknown stop IDs handled gracefully using default fallbacks", len(res_inv.stop_forecasts) == 2)

    # ── TEST 8: Different Bus Capacities ──────────────────────────────────────
    print("\n[TEST 8] Different Bus Capacities")
    res_mini = forecaster.forecast_upcoming_occupancy(
        bus_id="KA-BUS-008",
        current_occupancy=35,
        bus_capacity=40,  # 35/40 = 87.5% -> starts already in Warning
        route_id="R205",
        upcoming_stops=["R205-S01"],
    )
    check("Mini-bus capacity 40 recognized", res_mini.bus_capacity == 40)
    check("Current status classified as Warning (87.5%)", res_mini.current_status == SEVERITY_WARNING)
    check("Forecast condition is Warning", res_mini.forecast_condition == SEVERITY_WARNING)

    # ── TEST 9: Integration with MultiStopOccupancyPredictor ──────────────────
    print("\n[TEST 9] Integration with MultiStopOccupancyPredictor")
    ms_engine = MultiStopOccupancyPredictor()
    ms_output = ms_engine.predict_multi_stop(
        bus_id="KA-BUS-009",
        current_occupancy=22,
        bus_capacity=60,
        route_id="R330",
        upcoming_stops=["R330-S01", "R330-S02", "R330-S03", "R330-S04"],
    )
    res_integ = forecaster.forecast_from_multi_stop_result(ms_output)
    check("MultiStopPredictionResult directly consumed", res_integ.total_stops_evaluated == 4)
    check("Bus ID correctly maintained", res_integ.bus_id == "KA-BUS-009")
    check("Route ID correctly maintained", res_integ.route_id == "R330")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print(f"  RESULTS: {passed_checks}/{total_checks} checks passed, {total_checks - passed_checks} failed")
    if passed_checks == total_checks:
        print("  [OK] ALL CROWDING FORECASTER TESTS PASSED")
    else:
        print("  [FAIL] SOME TESTS FAILED")
    print("=" * 64)

    return passed_checks == total_checks


if __name__ == "__main__":
    run_self_tests()

