"""
scheduling/dispatch_advisor.py
==============================
Module 6, Step 3: Dispatch Interventions & Relief Bus Logic
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Detect severe and predicted critical overcrowding across transit routes.
  - Evaluate depot fleet availability before recommending relief bus dispatches.
  - Rank dispatch interventions by priority (CRITICAL, HIGH, MEDIUM, LOW).
  - Explicitly flag when fleet capacity is exhausted (spare fleet = 0).
  - Track intervention lifecycle (RECOMMENDED -> APPROVED / REJECTED -> EXECUTED).
  - Provide an empirical recovery monitoring mechanism to compare pre-intervention
    and post-intervention occupancy readings.
  - Strictly preserves original CSV (data/bus_occupancy.csv) and Modules 1–5.
  - ADVISORY ONLY: Does not simulate real-world physical vehicle movement.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Union

# Ensure root directory is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scheduling.route_demand_analyzer import (
    RouteDemandAnalyzer,
    VALID_ROUTES,
    DEFAULT_CAPACITY,
    WARNING_OCCUPANCY,
    CRITICAL_OCCUPANCY,
)
from scheduling.headway_optimizer import HeadwayOptimizer
from passenger_counting.occupancy_integrator import (
    THRESHOLD_WARNING,
    THRESHOLD_CRITICAL,
    SEVERITY_NORMAL,
    SEVERITY_WARNING,
    SEVERITY_CRITICAL,
)

CSV_PATH = os.path.join("data", "movesync_kr_market_anekal_via_electronic_city.csv")
ALL_KNOWN_BUSES = [f"KA-BUS-{i:03d}" for i in range(1, 21)]


class DispatchPriority(str, Enum):
    CRITICAL = "CRITICAL"   # Bus currently >=100% or forecast to hit 100% in <=2 stops
    HIGH = "HIGH"           # Bus in warning zone (>=85%) with positive boarding trend
    MEDIUM = "MEDIUM"       # Bus predicted to enter warning within 3-5 stops
    LOW = "LOW"             # Routine operational observation / no immediate intervention


class InterventionStatus(str, Enum):
    RECOMMENDED = "RECOMMENDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISPATCHED = "DISPATCHED"
    RECOVERY_OBSERVED = "RECOVERY_OBSERVED"
    NO_SPARE_AVAILABLE = "NO_SPARE_AVAILABLE"


@dataclass
class FleetDepotState:
    """Represents the depot fleet availability for a specific route or network."""
    route_id: str
    total_assigned_buses: int
    active_in_service_buses: int
    spare_standby_buses: int
    maintenance_buses: int = 0

    @property
    def has_spare_available(self) -> bool:
        return self.spare_standby_buses > 0


@dataclass
class DispatchInterventionRecommendation:
    """Actionable relief bus and dispatch intervention advisory."""
    intervention_id: str
    route_id: str
    target_bus_id: str
    current_occupancy: int
    bus_capacity: int
    current_occupancy_pct: float
    predicted_occupancy: int
    predicted_occupancy_pct: float
    first_critical_stop: Optional[str]
    stops_until_critical: Optional[int]
    priority: DispatchPriority
    recommended_action: str
    is_relief_bus_recommended: bool
    spare_buses_available: int
    depot_fleet_status: str  # 'SPARE_AVAILABLE', 'FLEET_EXHAUSTED'
    status: InterventionStatus
    authority_approval_timestamp: Optional[str] = None
    pre_intervention_occupancy: Optional[int] = None
    post_intervention_occupancy: Optional[int] = None
    occupancy_reduction_pct: Optional[float] = None
    recovery_confirmed: bool = False
    disclaimer: str = "ADVISORY DISPATCH ONLY — Requires human controller approval."
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DispatchAdvisor:
    """
    Evaluates real-time, predicted, and historical route conditions to generate
    prioritized dispatch interventions and relief bus recommendations.
    """

    def __init__(
        self,
        demand_analyzer: Optional[RouteDemandAnalyzer] = None,
        headway_optimizer: Optional[HeadwayOptimizer] = None,
    ):
        self.demand_analyzer = demand_analyzer or RouteDemandAnalyzer()
        self.headway_optimizer = headway_optimizer or HeadwayOptimizer(demand_analyzer=self.demand_analyzer)
        self._route_profiles = self.demand_analyzer.get_route_demand_summary()
        self.intervention_history: Dict[str, DispatchInterventionRecommendation] = {}

    def get_route_depot_state(
        self,
        route_id: str,
        total_assigned: int = 5,
        active_in_service: int = 4,
        maintenance: int = 0,
    ) -> FleetDepotState:
        """
        Calculates spare standby vehicle availability for a route depot.
        """
        if route_id not in VALID_ROUTES:
            raise ValueError(f"Invalid route_id '{route_id}'. Valid routes: {VALID_ROUTES}")

        safe_total = max(1, int(total_assigned))
        safe_maint = max(0, min(safe_total, int(maintenance)))
        safe_active = max(0, min(safe_total - safe_maint, int(active_in_service)))
        spares = max(0, safe_total - safe_active - safe_maint)

        return FleetDepotState(
            route_id=route_id,
            total_assigned_buses=safe_total,
            active_in_service_buses=safe_active,
            spare_standby_buses=spares,
            maintenance_buses=safe_maint,
        )

    def evaluate_dispatch_need(
        self,
        route_id: str,
        bus_id: str,
        current_occupancy: int,
        bus_capacity: int = DEFAULT_CAPACITY,
        predicted_occupancy: Optional[int] = None,
        first_critical_stop: Optional[str] = None,
        stops_until_critical: Optional[int] = None,
        fleet_depot_state: Optional[FleetDepotState] = None,
    ) -> DispatchInterventionRecommendation:
        """
        Evaluates current loading, predictions, and fleet availability to generate an intervention.
        """
        # Strict validation
        if route_id not in VALID_ROUTES:
            raise ValueError(f"Invalid route_id '{route_id}'. Valid routes: {VALID_ROUTES}")
        if bus_id not in ALL_KNOWN_BUSES:
            raise ValueError(f"Invalid bus_id '{bus_id}'. Known buses: KA-BUS-001 to KA-BUS-020")

        cap = max(15, min(120, int(bus_capacity)))
        curr = max(0, min(cap, int(current_occupancy)))
        curr_pct = round((curr / cap) * 100.0, 1)

        pred = curr if predicted_occupancy is None else max(0, min(cap, int(predicted_occupancy)))
        pred_pct = round((pred / cap) * 100.0, 1)

        depot = fleet_depot_state or self.get_route_depot_state(route_id)
        spares = depot.spare_standby_buses

        # Intervention ID
        inv_id = f"INT-{route_id}-{bus_id}-{datetime.now().strftime('%H%M%S')}"

        # ── Priority & Action Evaluation ─────────────────────────────────────
        # Condition 1: CRITICAL (Currently >= 100% capacity OR predicted to hit 100% within <= 2 stops)
        is_crit_now = (curr_pct >= THRESHOLD_CRITICAL)
        is_crit_soon = (pred_pct >= THRESHOLD_CRITICAL or (stops_until_critical is not None and stops_until_critical <= 2))

        if is_crit_now or is_crit_soon:
            priority = DispatchPriority.CRITICAL
            if spares > 0:
                action = (
                    f"🚨 URGENT RELIEF DISPATCH: Bus {bus_id} on {route_id} is at or near critical capacity "
                    f"({curr}/{cap} pax, predicted {pred}/{cap} pax). Dispatch 1 standby relief bus immediately "
                    f"from depot ({spares} spare available) to run shadow/relief service."
                )
                recommend_relief = True
                status = InterventionStatus.RECOMMENDED
                depot_status = "SPARE_AVAILABLE"
            else:
                action = (
                    f"⚠️ CRITICAL OVERCROWDING BUT NO SPARE FLEET: Bus {bus_id} on {route_id} is critically loaded "
                    f"({curr_pct}%), but depot spare fleet is 0. Recommend short-turning preceding unit or "
                    f"implementing emergency station crowd metering."
                )
                recommend_relief = False
                status = InterventionStatus.NO_SPARE_AVAILABLE
                depot_status = "FLEET_EXHAUSTED"

        # Condition 2: HIGH (Warning zone >= 85% or predicted critical within 3-4 stops)
        elif curr_pct >= THRESHOLD_WARNING or pred_pct >= THRESHOLD_WARNING:
            priority = DispatchPriority.HIGH
            if spares > 0:
                action = (
                    f"⚠️ PREVENTIVE RELIEF ADVISORY: Bus {bus_id} on {route_id} is heavily loaded ({curr_pct}%). "
                    f"Prepare 1 standby relief bus ({spares} available) or compress route headway to 10 min."
                )
                recommend_relief = True
                status = InterventionStatus.RECOMMENDED
                depot_status = "SPARE_AVAILABLE"
            else:
                action = (
                    f"Route {route_id} loading high ({curr_pct}%), no spare vehicles available. "
                    f"Maintain active monitoring and queue management."
                )
                recommend_relief = False
                status = InterventionStatus.NO_SPARE_AVAILABLE
                depot_status = "FLEET_EXHAUSTED"

        # Condition 3: MEDIUM (Predicted warning in upcoming stops)
        elif pred_pct >= 75.0:
            priority = DispatchPriority.MEDIUM
            action = (
                f"Moderate-to-high passenger build-up predicted on {route_id} ({pred_pct}%). "
                f"Fleet capacity sufficient; continue standard monitoring."
            )
            recommend_relief = False
            status = InterventionStatus.RECOMMENDED
            depot_status = "SPARE_AVAILABLE" if spares > 0 else "FLEET_EXHAUSTED"

        # Condition 4: LOW (Normal loading)
        else:
            priority = DispatchPriority.LOW
            action = (
                f"Bus {bus_id} on {route_id} operating under normal passenger load ({curr_pct}%). "
                f"No dispatch intervention required."
            )
            recommend_relief = False
            status = InterventionStatus.RECOMMENDED
            depot_status = "SPARE_AVAILABLE" if spares > 0 else "FLEET_EXHAUSTED"

        rec = DispatchInterventionRecommendation(
            intervention_id=inv_id,
            route_id=route_id,
            target_bus_id=bus_id,
            current_occupancy=curr,
            bus_capacity=cap,
            current_occupancy_pct=curr_pct,
            predicted_occupancy=pred,
            predicted_occupancy_pct=pred_pct,
            first_critical_stop=first_critical_stop,
            stops_until_critical=stops_until_critical,
            priority=priority,
            recommended_action=action,
            is_relief_bus_recommended=recommend_relief,
            spare_buses_available=spares,
            depot_fleet_status=depot_status,
            status=status,
            pre_intervention_occupancy=curr,
        )

        self.intervention_history[inv_id] = rec
        return rec

    def rank_interventions(
        self, interventions: List[DispatchInterventionRecommendation]
    ) -> List[DispatchInterventionRecommendation]:
        """
        Ranks multiple active interventions by priority order:
        CRITICAL (1) > HIGH (2) > MEDIUM (3) > LOW (4),
        sub-ranked by current occupancy percentage descending.
        """
        priority_weights = {
            DispatchPriority.CRITICAL: 1,
            DispatchPriority.HIGH: 2,
            DispatchPriority.MEDIUM: 3,
            DispatchPriority.LOW: 4,
        }
        return sorted(
            interventions,
            key=lambda x: (
                priority_weights.get(x.priority, 5),
                -x.current_occupancy_pct,
                -x.predicted_occupancy_pct,
            ),
        )

    def record_authority_decision(
        self, intervention_id: str, approved: bool
    ) -> DispatchInterventionRecommendation:
        """
        Records an authority decision to approve or reject a dispatch intervention.
        """
        if intervention_id not in self.intervention_history:
            raise KeyError(f"Intervention ID '{intervention_id}' not found in active records.")

        rec = self.intervention_history[intervention_id]
        if approved:
            rec.status = InterventionStatus.APPROVED
            rec.authority_approval_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            rec.status = InterventionStatus.REJECTED

        return rec

    def record_recovery_reading(
        self, intervention_id: str, post_occupancy: int
    ) -> DispatchInterventionRecommendation:
        """
        Records a post-intervention telemetry reading to empirically evaluate
        whether overcrowding subsided following the intervention.
        """
        if intervention_id not in self.intervention_history:
            raise KeyError(f"Intervention ID '{intervention_id}' not found in active records.")

        rec = self.intervention_history[intervention_id]
        rec.post_intervention_occupancy = max(0, min(rec.bus_capacity, int(post_occupancy)))

        if rec.pre_intervention_occupancy and rec.pre_intervention_occupancy > 0:
            reduction = (
                (rec.pre_intervention_occupancy - rec.post_intervention_occupancy)
                / rec.pre_intervention_occupancy
            ) * 100.0
            rec.occupancy_reduction_pct = round(reduction, 1)

            # Recovery confirmed if post-occupancy is below warning threshold (<85%)
            post_pct = (rec.post_intervention_occupancy / rec.bus_capacity) * 100.0
            if post_pct < THRESHOLD_WARNING and rec.status == InterventionStatus.APPROVED:
                rec.status = InterventionStatus.RECOVERY_OBSERVED
                rec.recovery_confirmed = True

        return rec

