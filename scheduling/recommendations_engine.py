"""
scheduling/recommendations_engine.py
====================================
Module 6, Step 1: Scheduling Input Preparation and Recommendations Foundation
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Formulate structured scheduling records uniting route telemetry, current
    occupancy, and Module 5 future predictions.
  - Generate data-driven scheduling advisories:
      * Additional bus required (critical / high recurring overcrowding)
      * Increased service frequency / reduced headway (high boarding demand)
      * Sufficient capacity / standard timetable maintained
      * Reduced service frequency / reallocation candidate (low demand)
  - Explicitly mark all outputs as ADVISORY / RECOMMENDATION ONLY.
  - Decoupled from Streamlit UI and physical dispatch actuators.
  - Strictly preserves original CSV dataset and Modules 1–5.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

# Ensure root directory is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scheduling.route_demand_analyzer import RouteDemandAnalyzer, RouteDemandProfile
from occupancy_prediction.prediction_pipeline import FutureOccupancyPredictor, PredictionInput, PredictionResult
from occupancy_prediction.multi_stop_predictor import MultiStopOccupancyPredictor, MultiStopPredictionResult
from passenger_counting.occupancy_integrator import (
    THRESHOLD_WARNING,
    THRESHOLD_CRITICAL,
    SEVERITY_NORMAL,
    SEVERITY_WARNING,
    SEVERITY_CRITICAL,
    DEFAULT_BUS_CAPACITY,
)

CSV_PATH = os.path.join("data", "movesync_kr_market_anekal_via_electronic_city.csv")
VALID_ROUTES = ["KR_MARKET_ANEKAL_VIA_ECITY", "R047", "R101", "R205", "R330"]


@dataclass
class SchedulingInputRecord:
    """Consolidated input structure for scheduling evaluation."""
    route_id: str
    bus_id: str
    bus_capacity: int
    current_occupancy: int
    current_occupancy_pct: float
    current_severity: str
    predicted_occupancy: int
    predicted_occupancy_pct: float
    predicted_severity: str
    peak_hour: int
    day_type: str
    route_demand_tier: str
    provenance: str = "TELEMETRY_AND_ML_FORECAST"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SchedulingRecommendation:
    """Actionable scheduling advisory generated from demand analysis and prediction."""
    route_id: str
    bus_id: Optional[str]
    recommendation_type: str
    # Types:
    #   'ADD_ADDITIONAL_BUS'
    #   'INCREASE_SERVICE_FREQUENCY'
    #   'MAINTAIN_CURRENT_SCHEDULE'
    #   'REDUCE_SERVICE_FREQUENCY'
    priority: str  # 'HIGH', 'MEDIUM', 'LOW'
    reasoning: str
    recommended_headway_adjustment_min: int  # e.g. -5 (more frequent), 0 (none), +10 (less frequent)
    suggested_action: str
    is_implemented: bool = False  # Always False: indicates advisory nature, no automated dispatch
    disclaimer: str = "DATA-DRIVEN ADVISORY ONLY — Requires transit authority dispatch confirmation."
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SchedulingRecommendationsEngine:
    """
    Evaluates current and forecasted route demands to formulate scheduling recommendations.
    Adheres to transparent heuristic threshold logic based on historical profiles and ML predictions.
    """

    def __init__(self, demand_analyzer: Optional[RouteDemandAnalyzer] = None):
        self.demand_analyzer = demand_analyzer or RouteDemandAnalyzer()
        self._route_profiles = self.demand_analyzer.get_route_demand_summary()

    def build_scheduling_input(
        self,
        route_id: str = "R101",
        bus_id: str = "KA-BUS-001",
        current_occupancy: int = 25,
        bus_capacity: int = DEFAULT_BUS_CAPACITY,
        predicted_occupancy: Optional[int] = None,
        peak_hour: int = 0,
        day_type: str = "weekday",
    ) -> SchedulingInputRecord:
        """
        Creates a validated, typed scheduling input record.
        """
        cap = max(1, int(bus_capacity))
        curr = max(0, min(cap, int(current_occupancy)))
        curr_pct = round((curr / cap) * 100.0, 1)

        if curr_pct >= THRESHOLD_CRITICAL:
            curr_sev = SEVERITY_CRITICAL
        elif curr_pct >= THRESHOLD_WARNING:
            curr_sev = SEVERITY_WARNING
        else:
            curr_sev = SEVERITY_NORMAL

        # If predicted_occupancy is not provided, estimate from prediction pipeline or current
        if predicted_occupancy is None:
            pred = min(cap, curr + 2)
        else:
            pred = max(0, min(cap, int(predicted_occupancy)))

        pred_pct = round((pred / cap) * 100.0, 1)
        if pred_pct >= THRESHOLD_CRITICAL:
            pred_sev = SEVERITY_CRITICAL
        elif pred_pct >= THRESHOLD_WARNING:
            pred_sev = SEVERITY_WARNING
        else:
            pred_sev = SEVERITY_NORMAL

        route_prof = self._route_profiles.get(route_id)
        tier = route_prof.demand_tier if route_prof else "MODERATE_DEMAND"

        return SchedulingInputRecord(
            route_id=route_id,
            bus_id=bus_id,
            bus_capacity=cap,
            current_occupancy=curr,
            current_occupancy_pct=curr_pct,
            current_severity=curr_sev,
            predicted_occupancy=pred,
            predicted_occupancy_pct=pred_pct,
            predicted_severity=pred_sev,
            peak_hour=1 if str(peak_hour) in ["1", "true", "True"] else 0,
            day_type="weekend" if str(day_type).lower() == "weekend" else "weekday",
            route_demand_tier=tier,
        )

    def generate_recommendation_from_input(
        self, record: SchedulingInputRecord
    ) -> SchedulingRecommendation:
        """
        Synthesizes route profile metrics and live/predicted states into a scheduling recommendation.
        """
        route_prof = self._route_profiles.get(record.route_id)
        r_id = record.route_id
        bus_id = record.bus_id

        # Rule 1: Imminent or current Critical Overcrowding (>=100% capacity)
        if record.predicted_severity == SEVERITY_CRITICAL or record.current_severity == SEVERITY_CRITICAL:
            return SchedulingRecommendation(
                route_id=r_id,
                bus_id=bus_id,
                recommendation_type="ADD_ADDITIONAL_BUS",
                priority="HIGH",
                reasoning=(
                    f"Bus {bus_id} on {r_id} is forecast to hit full capacity "
                    f"({record.predicted_occupancy}/{record.bus_capacity} pax, {record.predicted_occupancy_pct}%). "
                    f"Historical critical frequency on this route is {route_prof.critical_occurrences if route_prof else 'high'} occurrences."
                ),
                recommended_headway_adjustment_min=-5,
                suggested_action="Deploy standby relief bus or express backup immediately to absorb platform queuing.",
            )

        # Rule 2: Warning Overcrowding (85%-99%) during Peak Hour
        if (record.predicted_severity == SEVERITY_WARNING or record.current_severity == SEVERITY_WARNING) and record.peak_hour == 1:
            return SchedulingRecommendation(
                route_id=r_id,
                bus_id=bus_id,
                recommendation_type="INCREASE_SERVICE_FREQUENCY",
                priority="MEDIUM",
                reasoning=(
                    f"Route {r_id} exhibits heavy peak-hour passenger demand with predicted occupancy reaching "
                    f"{record.predicted_occupancy_pct}%. Shortening headway will prevent transition to critical capacity."
                ),
                recommended_headway_adjustment_min=-3,
                suggested_action="Compress timetable headway (e.g. from 15 min to 12 min) during active peak corridor.",
            )

        # Rule 3: Chronic Low Demand on Weekend or Off-Peak (occupancy < 25%)
        if record.peak_hour == 0 and record.current_occupancy_pct < 25.0 and record.predicted_occupancy_pct < 25.0:
            return SchedulingRecommendation(
                route_id=r_id,
                bus_id=bus_id,
                recommendation_type="REDUCE_SERVICE_FREQUENCY",
                priority="LOW",
                reasoning=(
                    f"Sustained low passenger loading detected on {r_id} during off-peak operations "
                    f"(current {record.current_occupancy_pct}%, predicted {record.predicted_occupancy_pct}%). "
                    f"Capacity is significantly underutilized."
                ),
                recommended_headway_adjustment_min=5,
                suggested_action="Relax schedule headway or reallocate fleet units to higher-demand corridors to conserve operational fuel.",
            )

        # Rule 4: Stable / Normal Operations
        return SchedulingRecommendation(
            route_id=r_id,
            bus_id=bus_id,
            recommendation_type="MAINTAIN_CURRENT_SCHEDULE",
            priority="LOW",
            reasoning=(
                f"Fleet occupancy ({record.current_occupancy_pct}%) and future projections ({record.predicted_occupancy_pct}%) "
                f"remain well within safe bounds (<85%). Service levels match current passenger flow."
            ),
            recommended_headway_adjustment_min=0,
            suggested_action="Continue standard operating timetable without modification.",
        )

    def get_route_wide_recommendations(self) -> List[SchedulingRecommendation]:
        """
        Evaluates overall historical demand per route to produce network-level fleet recommendations.
        """
        recs: List[SchedulingRecommendation] = []
        for r_id, prof in self._route_profiles.items():
            if prof.demand_tier == "HIGH_DEMAND":
                recs.append(SchedulingRecommendation(
                    route_id=r_id,
                    bus_id=None,
                    recommendation_type="INCREASE_SERVICE_FREQUENCY",
                    priority="HIGH",
                    reasoning=(
                        f"Route {r_id} is categorized as HIGH_DEMAND with {prof.critical_occurrences} critical "
                        f"and {prof.warning_occurrences} warning crowding occurrences ({prof.warning_rate_pct}% of runs). "
                        f"Peak hours ({prof.peak_demand_period}) consistently strain available seating."
                    ),
                    recommended_headway_adjustment_min=-5,
                    suggested_action=f"Increase scheduled bus allocations on {r_id} during {prof.peak_demand_period}.",
                ))
            elif prof.demand_tier == "MODERATE_DEMAND":
                recs.append(SchedulingRecommendation(
                    route_id=r_id,
                    bus_id=None,
                    recommendation_type="MAINTAIN_CURRENT_SCHEDULE",
                    priority="MEDIUM",
                    reasoning=(
                        f"Route {r_id} shows balanced passenger volumes (mean occupancy {prof.average_occupancy} pax, "
                        f"{prof.average_occupancy_pct}%). Warning occurrences ({prof.warning_occurrences}) are manageable."
                    ),
                    recommended_headway_adjustment_min=0,
                    suggested_action="Maintain scheduled headway; monitor during peak periods.",
                ))
            else:
                recs.append(SchedulingRecommendation(
                    route_id=r_id,
                    bus_id=None,
                    recommendation_type="MAINTAIN_CURRENT_SCHEDULE",
                    priority="LOW",
                    reasoning=f"Route {r_id} maintains low risk of overcrowding (mean occupancy {prof.average_occupancy} pax).",
                    recommended_headway_adjustment_min=0,
                    suggested_action="Timetable capacity is sufficient.",
                ))

        return recs

