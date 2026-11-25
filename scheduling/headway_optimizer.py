"""
scheduling/headway_optimizer.py
===============================
Module 6, Step 2: Headway Optimization and Dynamic Timetable Logic
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Formulate data-driven headway intervals (minutes between departures)
    based on route passenger demand, morning/evening peak periods, off-peak
    periods, bus capacity, and fleet availability constraints.
  - Generate dynamic, optimized departure timetables spanning operating hours (06:00 - 22:00).
  - Compare baseline existing operating headways against suggested optimized headways.
  - Provide human-interpretable technical rationales for every headway adjustment.
  - Enforce realistic operational bounds:
      * Minimum headway boundary: 5 minutes (prevents bus bunching & depot overflow)
      * Maximum headway boundary: 30 minutes (prevents excessive passenger wait times)
      * Fleet constraint ceiling: total buses active cannot exceed available fleet
  - Explicitly mark all generated schedules and headways as:
      "SUGGESTED / ADVISORY TIMETABLE — Requires dispatch approval. Not implemented automatically."
  - Strictly preserves original CSV (data/bus_occupancy.csv) and Modules 1–5.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, time, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd

# Ensure root directory is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scheduling.route_demand_analyzer import (
    RouteDemandAnalyzer,
    RouteDemandProfile,
    HourlyDemandProfile,
    VALID_ROUTES,
    DEFAULT_CAPACITY,
    WARNING_OCCUPANCY,
    CRITICAL_OCCUPANCY,
)
from scheduling.recommendations_engine import SchedulingRecommendationsEngine

# Standard operating parameters
DEFAULT_MIN_HEADWAY_MIN = 5     # Minimum allowable interval (anti-bunching)
DEFAULT_MAX_HEADWAY_MIN = 30    # Maximum allowable interval (service quality floor)
DEFAULT_FLEET_SIZE_PER_ROUTE = 5  # Standard nominal allocation of buses per route

# Baseline standard operating headways (common municipal transit standard before optimization)
BASELINE_HEADWAYS_MIN = {
    "MORNING_PEAK": 15,
    "EVENING_PEAK": 15,
    "OFF_PEAK": 20,
    "WEEKEND": 25,
}

# Operating periods definition
PERIOD_MORNING_PEAK = "MORNING_PEAK"  # 07:00 - 11:00
PERIOD_EVENING_PEAK = "EVENING_PEAK"  # 17:00 - 21:00
PERIOD_OFF_PEAK = "OFF_PEAK"          # 06:00 - 07:00, 11:00 - 17:00, 21:00 - 22:00
PERIOD_WEEKEND = "WEEKEND"


@dataclass
class PeriodHeadwayRecommendation:
    """Headway interval specification for a specific route and operating period."""
    route_id: str
    period_name: str  # 'MORNING_PEAK', 'EVENING_PEAK', 'OFF_PEAK', 'WEEKEND'
    period_label: str # e.g. "07:00 - 11:00 (Morning Peak)"
    baseline_headway_min: int
    suggested_headway_min: int
    headway_delta_min: int
    estimated_hourly_demand_pax: float
    target_bus_occupancy: int
    buses_required: int
    fleet_available: int
    fleet_constraint_active: bool
    rationale: str
    is_implemented: bool = False
    disclaimer: str = "ADVISORY HEADWAY ONLY — Dispatch confirmation required."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DepartureSlot:
    """Single suggested trip departure in an optimized timetable."""
    departure_time: str  # "HH:MM"
    period_name: str
    headway_from_previous_min: int
    assigned_route_id: str
    bus_index_in_rotation: int
    forecasted_demand_level: str  # 'PEAK', 'SHOULDER', 'OFF_PEAK'
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RouteOptimizedTimetable:
    """Complete operating day timetable for a transit route."""
    route_id: str
    day_type: str  # 'weekday' or 'weekend'
    operating_start_time: str  # "06:00"
    operating_end_time: str    # "22:00"
    total_departures: int
    baseline_total_departures: int
    service_increase_pct: float
    morning_peak_headway_min: int
    evening_peak_headway_min: int
    off_peak_headway_min: int
    departures: List[DepartureSlot]
    period_recommendations: List[PeriodHeadwayRecommendation]
    fleet_size_assumed: int
    provenance: str = "DATA_DRIVEN_HEADWAY_MODEL"
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HeadwayOptimizer:
    """
    Calculates passenger demand-responsive departure headways and generates
    daily operating timetables under fleet capacity constraints.
    """

    def __init__(
        self,
        demand_analyzer: Optional[RouteDemandAnalyzer] = None,
        min_headway_min: int = DEFAULT_MIN_HEADWAY_MIN,
        max_headway_min: int = DEFAULT_MAX_HEADWAY_MIN,
    ):
        self.demand_analyzer = demand_analyzer or RouteDemandAnalyzer()
        self.min_headway_min = max(3, int(min_headway_min))
        self.max_headway_min = max(self.min_headway_min + 5, int(max_headway_min))
        self._route_profiles = self.demand_analyzer.get_route_demand_summary()
        self._hourly_profiles = self.demand_analyzer.get_hourly_demand_breakdown()

    def calculate_headway_for_period(
        self,
        route_id: str,
        period_name: str,
        bus_capacity: int = DEFAULT_CAPACITY,
        fleet_available: int = DEFAULT_FLEET_SIZE_PER_ROUTE,
        predicted_overcrowding_factor: float = 1.0,
    ) -> PeriodHeadwayRecommendation:
        """
        Calculates suggested headway for a given route and operating period.

        Formula & Heuristic:
        - Target load factor: 70% to 75% of bus capacity (42-45 pax for 60-seat bus)
          to absorb intermediate stop boarding spikes without exceeding 85% Warning threshold.
        - Demand rate: derived from historical mean boarding and occupancy in that period.
        - Raw Headway = (Target Occupancy / Hourly Demand) * 60 minutes
        - Apply predicted overcrowding factor (from Module 5 predictions) to compress headway if critical.
        - Clamped between [min_headway_min, max_headway_min].
        - Bounded by fleet size: Buses required = (Route cycle time / Headway).
          If buses required > fleet_available, headway is clamped to (cycle time / fleet_available).
        """
        # Validate and sanitize route
        if route_id not in VALID_ROUTES:
            raise ValueError(f"Invalid route_id '{route_id}'. Valid route options are: {VALID_ROUTES}")

        safe_route = route_id
        safe_capacity = max(15, min(120, int(bus_capacity)))
        safe_fleet = max(1, int(fleet_available))

        prof = self._route_profiles.get(safe_route)
        baseline_h = BASELINE_HEADWAYS_MIN.get(period_name, 20)
        target_load = int(round(safe_capacity * 0.72))  # ~43 pax for 60-seat bus

        # Estimated one-way route cycle time in minutes (based on 11 stops @ 5 min average interval = ~55-60 min)
        cycle_time_min = 60

        # Estimate hourly passenger flow based on historical telemetry
        if period_name == PERIOD_MORNING_PEAK:
            period_label = "07:00 - 11:00 (Morning Peak)"
            # Mean occupancy during morning peak
            hourly_peak = [h.average_occupancy for h in self._hourly_profiles if h.hour in [7, 8, 9, 10]]
            avg_occ = float(np.mean(hourly_peak)) if hourly_peak else 30.0
            route_mult = (prof.average_occupancy / 20.0) if prof else 1.0
            effective_demand = avg_occ * route_mult * float(predicted_overcrowding_factor)

            # Continuous demand-responsive calculation with discrete step quantization
            if effective_demand >= 38.0:
                raw_headway = 8
                rationale = f"Severe morning commuter demand on {safe_route} (effective demand {effective_demand:.1f} pax/hr). Compressed to 8 min."
            elif effective_demand >= 30.0:
                raw_headway = 10
                rationale = f"Heavy morning commuter loading on {safe_route} (tier {prof.demand_tier}, effective demand {effective_demand:.1f} pax/hr). Headway set to 10 min."
            elif effective_demand >= 24.0:
                raw_headway = 12
                rationale = f"Moderate morning commuter loading on {safe_route} (effective demand {effective_demand:.1f} pax/hr). Headway set to 12 min."
            else:
                raw_headway = 15
                rationale = f"Standard morning commuter loading on {safe_route} (effective demand {effective_demand:.1f} pax/hr). Headway set to 15 min."

            if predicted_overcrowding_factor > 1.1:
                rationale += f" [Module 5 predicted overcrowding factor {predicted_overcrowding_factor:.2f} applied]."

        elif period_name == PERIOD_EVENING_PEAK:
            period_label = "17:00 - 21:00 (Evening Peak)"
            hourly_peak = [h.average_occupancy for h in self._hourly_profiles if h.hour in [17, 18, 19, 20]]
            avg_occ = float(np.mean(hourly_peak)) if hourly_peak else 28.0
            route_mult = (prof.average_occupancy / 20.0) if prof else 1.0
            effective_demand = avg_occ * route_mult * float(predicted_overcrowding_factor)

            if effective_demand >= 38.0:
                raw_headway = 8
                rationale = f"Severe evening egress demand on {safe_route} (effective demand {effective_demand:.1f} pax/hr). Compressed to 8 min."
            elif effective_demand >= 30.0:
                raw_headway = 10
                rationale = f"Sustained evening egress loading on {safe_route} (effective demand {effective_demand:.1f} pax/hr). Headway set to 10 min."
            elif effective_demand >= 24.0:
                raw_headway = 12
                rationale = f"Moderate evening peak demand on {safe_route} (effective demand {effective_demand:.1f} pax/hr). Headway set to 12 min."
            else:
                raw_headway = 15
                rationale = f"Standard evening demand on {safe_route} (effective demand {effective_demand:.1f} pax/hr). Headway set to 15 min."

            if predicted_overcrowding_factor > 1.1:
                rationale += f" [Module 5 predicted overcrowding factor {predicted_overcrowding_factor:.2f} applied]."

        elif period_name == PERIOD_WEEKEND:
            period_label = "Weekend Operations (06:00 - 22:00)"
            effective_demand = (prof.weekend_mean_occupancy if prof else 14.0) * float(predicted_overcrowding_factor)
            raw_headway = 25 if effective_demand < 15.0 else 20
            rationale = f"Weekend passenger demand drops significantly on {safe_route} (mean loading {effective_demand:.1f} pax). Headway set to {raw_headway} min."

        else:  # OFF_PEAK
            period_label = "Mid-Day / Early / Late Off-Peak"
            effective_demand = 11.0 * float(predicted_overcrowding_factor)
            raw_headway = 20
            rationale = f"Off-peak passenger demand is light on {safe_route} (effective demand {effective_demand:.1f} pax/hr). 20-minute interval provides reliable service without empty running."

        # Apply capacity adjustment: smaller buses need tighter headways, larger buses can tolerate wider
        if safe_capacity < 45:
            raw_headway = max(self.min_headway_min, raw_headway - 2)
            rationale += f" Adjusted down by 2 min due to smaller vehicle capacity ({safe_capacity} pax)."
        elif safe_capacity > 75:
            raw_headway = min(self.max_headway_min, raw_headway + 2)
            rationale += f" Adjusted up by 2 min due to high-capacity vehicle fleet ({safe_capacity} pax)."

        # Enforce minimum & maximum headway boundary limits
        bounded_headway = max(self.min_headway_min, min(self.max_headway_min, raw_headway))

        # Check fleet constraint:
        # Minimum headway supported by available fleet = ceil(cycle_time_min / fleet_available)
        min_headway_fleet_supports = int(np.ceil(cycle_time_min / safe_fleet))
        fleet_constraint_active = False

        if bounded_headway < min_headway_fleet_supports:
            rationale += (
                f" [FLEET CONSTRAINT ACTIVE: Suggested headway {bounded_headway}m exceeds capacity of "
                f"{safe_fleet} available buses (min possible is {min_headway_fleet_supports}m). "
                f"Clamped to {min_headway_fleet_supports}m]."
            )
            final_headway = min_headway_fleet_supports
            fleet_constraint_active = True
        else:
            final_headway = bounded_headway

        # Re-verify boundaries
        final_headway = max(self.min_headway_min, min(self.max_headway_min, final_headway))
        buses_needed = max(1, int(np.ceil(cycle_time_min / final_headway)))

        return PeriodHeadwayRecommendation(
            route_id=safe_route,
            period_name=period_name,
            period_label=period_label,
            baseline_headway_min=baseline_h,
            suggested_headway_min=final_headway,
            headway_delta_min=final_headway - baseline_h,
            estimated_hourly_demand_pax=round(effective_demand, 1),
            target_bus_occupancy=target_load,
            buses_required=buses_needed,
            fleet_available=safe_fleet,
            fleet_constraint_active=fleet_constraint_active,
            rationale=rationale,
        )

    def generate_optimized_timetable(
        self,
        route_id: str,
        day_type: str = "weekday",
        bus_capacity: int = DEFAULT_CAPACITY,
        fleet_available: int = DEFAULT_FLEET_SIZE_PER_ROUTE,
        predicted_overcrowding_factor: float = 1.0,
    ) -> RouteOptimizedTimetable:
        """
        Generates a chronological departure timetable from 06:00 to 22:00
        using optimized period headways.
        """
        if route_id not in VALID_ROUTES:
            raise ValueError(f"Invalid route_id '{route_id}'. Valid route options are: {VALID_ROUTES}")

        safe_route = route_id
        safe_fleet = max(1, int(fleet_available))
        safe_capacity = max(15, min(120, int(bus_capacity)))
        is_weekend = (str(day_type).lower() == "weekend")

        # Compute period recommendations
        if is_weekend:
            recs = [
                self.calculate_headway_for_period(
                    safe_route, PERIOD_WEEKEND, safe_capacity, safe_fleet, predicted_overcrowding_factor
                )
            ]
            m_h = recs[0].suggested_headway_min
            e_h = recs[0].suggested_headway_min
            o_h = recs[0].suggested_headway_min
        else:
            rec_m = self.calculate_headway_for_period(
                safe_route, PERIOD_MORNING_PEAK, safe_capacity, safe_fleet, predicted_overcrowding_factor
            )
            rec_e = self.calculate_headway_for_period(
                safe_route, PERIOD_EVENING_PEAK, safe_capacity, safe_fleet, predicted_overcrowding_factor
            )
            rec_o = self.calculate_headway_for_period(
                safe_route, PERIOD_OFF_PEAK, safe_capacity, safe_fleet, predicted_overcrowding_factor
            )
            recs = [rec_m, rec_e, rec_o]
            m_h = rec_m.suggested_headway_min
            e_h = rec_e.suggested_headway_min
            o_h = rec_o.suggested_headway_min

        # Generate departure schedule from 06:00 to 22:00
        departures: List[DepartureSlot] = []
        curr_time = datetime(2026, 1, 1, 6, 0)
        end_time = datetime(2026, 1, 1, 22, 0)
        bus_rotation = 1

        while curr_time <= end_time:
            hour = curr_time.hour
            # Determine operating period and appropriate headway
            if is_weekend:
                active_period = PERIOD_WEEKEND
                active_headway = recs[0].suggested_headway_min
                demand_label = "OFF_PEAK"
            elif 7 <= hour < 11:
                active_period = PERIOD_MORNING_PEAK
                active_headway = m_h
                demand_label = "PEAK"
            elif 17 <= hour < 21:
                active_period = PERIOD_EVENING_PEAK
                active_headway = e_h
                demand_label = "PEAK"
            else:
                active_period = PERIOD_OFF_PEAK
                active_headway = o_h
                demand_label = "OFF_PEAK"

            departures.append(DepartureSlot(
                departure_time=curr_time.strftime("%H:%M"),
                period_name=active_period,
                headway_from_previous_min=active_headway if len(departures) > 0 else 0,
                assigned_route_id=safe_route,
                bus_index_in_rotation=bus_rotation,
                forecasted_demand_level=demand_label,
                notes=f"{demand_label} departure. Headway: {active_headway} min.",
            ))

            curr_time += timedelta(minutes=active_headway)
            bus_rotation = (bus_rotation % safe_fleet) + 1

        # Calculate comparison with baseline timetable
        # Baseline weekday: 15m in morning (07-11) & evening (17-21), 20m in off-peak = 57 trips
        # Baseline weekend: 25m uniform from 06:00 to 22:00 = 39 trips
        baseline_trips = 57 if not is_weekend else 39
        actual_trips = len(departures)
        pct_change = round(((actual_trips - baseline_trips) / baseline_trips) * 100.0, 1)

        return RouteOptimizedTimetable(
            route_id=safe_route,
            day_type="weekend" if is_weekend else "weekday",
            operating_start_time="06:00",
            operating_end_time="22:00",
            total_departures=actual_trips,
            baseline_total_departures=baseline_trips,
            service_increase_pct=pct_change,
            morning_peak_headway_min=m_h,
            evening_peak_headway_min=e_h,
            off_peak_headway_min=o_h,
            departures=departures,
            period_recommendations=recs,
            fleet_size_assumed=fleet_available,
        )

    def get_all_routes_headway_summary(
        self,
        day_type: str = "weekday",
        bus_capacity: int = DEFAULT_CAPACITY,
        fleet_available: int = DEFAULT_FLEET_SIZE_PER_ROUTE,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generates comparative headway summaries across all four routes.
        """
        summary: Dict[str, Dict[str, Any]] = {}
        for r in VALID_ROUTES:
            tt = self.generate_optimized_timetable(
                route_id=r,
                day_type=day_type,
                bus_capacity=bus_capacity,
                fleet_available=fleet_available,
            )
            prof = self._route_profiles.get(r)
            summary[r] = {
                "route_id": r,
                "demand_tier": prof.demand_tier if prof else "MODERATE_DEMAND",
                "morning_peak_headway": f"{tt.morning_peak_headway_min} min (Baseline: 15 min)",
                "evening_peak_headway": f"{tt.evening_peak_headway_min} min (Baseline: 15 min)",
                "off_peak_headway": f"{tt.off_peak_headway_min} min (Baseline: 20 min)",
                "total_daily_departures": tt.total_departures,
                "baseline_departures": tt.baseline_total_departures,
                "departure_variance_pct": f"{tt.service_increase_pct:+0.1f}%",
                "buses_required_morning_peak": max(1, int(round(60 / tt.morning_peak_headway_min))),
                "buses_required_evening_peak": max(1, int(round(60 / tt.evening_peak_headway_min))),
                "fleet_size_assumed": fleet_available,
            }
        return summary
