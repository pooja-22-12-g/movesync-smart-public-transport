"""
scheduling/__init__.py
======================
Module 6: Intelligent Bus Scheduling and Fleet Optimization
"""

from scheduling.route_demand_analyzer import (
    RouteDemandAnalyzer,
    RouteDemandProfile,
    HourlyDemandProfile,
    VALID_ROUTES,
    DEFAULT_CAPACITY,
    WARNING_OCCUPANCY,
    CRITICAL_OCCUPANCY,
)

from scheduling.recommendations_engine import (
    SchedulingRecommendationsEngine,
    SchedulingInputRecord,
    SchedulingRecommendation,
)

from scheduling.headway_optimizer import (
    HeadwayOptimizer,
    PeriodHeadwayRecommendation,
    DepartureSlot,
    RouteOptimizedTimetable,
    DEFAULT_MIN_HEADWAY_MIN,
    DEFAULT_MAX_HEADWAY_MIN,
    DEFAULT_FLEET_SIZE_PER_ROUTE,
    BASELINE_HEADWAYS_MIN,
    PERIOD_MORNING_PEAK,
    PERIOD_EVENING_PEAK,
    PERIOD_OFF_PEAK,
    PERIOD_WEEKEND,
)

from scheduling.dispatch_advisor import (
    DispatchAdvisor,
    DispatchPriority,
    InterventionStatus,
    FleetDepotState,
    DispatchInterventionRecommendation,
    ALL_KNOWN_BUSES,
)

__all__ = [
    "RouteDemandAnalyzer",
    "RouteDemandProfile",
    "HourlyDemandProfile",
    "SchedulingRecommendationsEngine",
    "SchedulingInputRecord",
    "SchedulingRecommendation",
    "HeadwayOptimizer",
    "PeriodHeadwayRecommendation",
    "DepartureSlot",
    "RouteOptimizedTimetable",
    "DispatchAdvisor",
    "DispatchPriority",
    "InterventionStatus",
    "FleetDepotState",
    "DispatchInterventionRecommendation",
    "ALL_KNOWN_BUSES",
    "VALID_ROUTES",
    "DEFAULT_CAPACITY",
    "WARNING_OCCUPANCY",
    "CRITICAL_OCCUPANCY",
    "DEFAULT_MIN_HEADWAY_MIN",
    "DEFAULT_MAX_HEADWAY_MIN",
    "DEFAULT_FLEET_SIZE_PER_ROUTE",
    "BASELINE_HEADWAYS_MIN",
    "PERIOD_MORNING_PEAK",
    "PERIOD_EVENING_PEAK",
    "PERIOD_OFF_PEAK",
    "PERIOD_WEEKEND",
]
