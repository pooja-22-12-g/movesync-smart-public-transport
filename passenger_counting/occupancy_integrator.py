"""
passenger_counting/occupancy_integrator.py
==========================================
Module 4, Step 4: Occupancy Calculation Integration
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Safely integrate camera/video-based boarding and alighting counts with the
    system's bus occupancy calculations.
  - Formula:
        New Occupancy = Previous Occupancy + Boarding - Alighting
  - Guard against negative occupancy (clamped at 0 with underflow detection).
  - Guard against exceeding bus capacity (clamped at capacity with overflow warning).
  - Calculate accurate occupancy percentage: (New Occupancy / Capacity) * 100.
  - Generate alert warnings matching Module 2 overcrowding thresholds:
        Normal: < 85%
        Warning: 85% to < 100%
        Critical: >= 100% (or exceeded)
  - Handle missing, None, or invalid data types safely without crashes.
  - Maintain separate totals for boarding, alighting, and net passenger delta.
  - Completely independent of the Streamlit dashboard and UI.
  - Strictly does NOT modify data/bus_occupancy.csv or Modules 1, 2, 3.
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Union


# Reuse threshold standards from Module 2 (Overcrowding Alerts)
THRESHOLD_WARNING = 85.0
THRESHOLD_CRITICAL = 100.0

SEVERITY_NORMAL = "Normal"
SEVERITY_WARNING = "Warning"
SEVERITY_CRITICAL = "Critical"

DEFAULT_BUS_CAPACITY = 60


@dataclass
class OccupancyUpdateResult:
    """Represents the validated result of an occupancy calculation."""
    bus_id: str
    route_id: str
    previous_occupancy: int
    boarding: int
    alighting: int
    net_change: int
    raw_calculated_occupancy: int
    new_occupancy: int
    bus_capacity: int
    occupancy_pct: float
    alert_severity: str
    is_overcrowded: bool
    is_underflow_detected: bool
    is_capacity_exceeded: bool
    validation_notes: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OccupancyIntegrator:
    """
    Manages stateful and stateless occupancy calculations for bus video sessions.
    Decoupled from video frames, hardware sensors, and UI rendering.
    """

    def __init__(self, bus_id: str = "KA-BUS-001", route_id: str = "R101", bus_capacity: int = DEFAULT_BUS_CAPACITY):
        self.bus_id = bus_id
        self.route_id = route_id
        self.bus_capacity = max(1, int(bus_capacity))
        self.current_occupancy: int = 0
        self.cumulative_boarding: int = 0
        self.cumulative_alighting: int = 0
        self.history: List[OccupancyUpdateResult] = []

    def set_initial_occupancy(self, initial_occupancy: int):
        """Sets the starting occupancy for a session, clamping safely to valid bounds."""
        clamped = max(0, min(self.bus_capacity, int(initial_occupancy)))
        self.current_occupancy = clamped

    def update(
        self,
        boarding: Union[int, float, str, None],
        alighting: Union[int, float, str, None],
        previous_occupancy: Optional[Union[int, float, str]] = None,
        bus_id: Optional[str] = None,
        route_id: Optional[str] = None,
        bus_capacity: Optional[int] = None,
    ) -> OccupancyUpdateResult:
        """
        Calculates new occupancy using:
            New Occupancy = Previous Occupancy + Boarding - Alighting

        Validates against negative numbers, capacity overflow, and malformed inputs.
        """
        notes: List[str] = []

        # 1. Resolve bus identification & capacity
        active_bus_id = bus_id or self.bus_id
        active_route_id = route_id or self.route_id
        active_capacity = bus_capacity if bus_capacity is not None else self.bus_capacity
        if not isinstance(active_capacity, (int, float)) or active_capacity <= 0:
            notes.append(f"Invalid capacity ({active_capacity}); reset to default {DEFAULT_BUS_CAPACITY}.")
            active_capacity = DEFAULT_BUS_CAPACITY
        else:
            active_capacity = int(active_capacity)

        # 2. Resolve previous occupancy
        if previous_occupancy is not None:
            safe_prev = self._sanitize_integer(previous_occupancy, default=0, field_name="previous_occupancy", notes=notes)
        else:
            safe_prev = self.current_occupancy

        # 3. Sanitize boarding and alighting
        safe_boarding = self._sanitize_integer(boarding, default=0, field_name="boarding", notes=notes)
        safe_alighting = self._sanitize_integer(alighting, default=0, field_name="alighting", notes=notes)

        # 4. Compute formula
        net_change = safe_boarding - safe_alighting
        raw_occupancy = safe_prev + safe_boarding - safe_alighting

        # 5. Bounds validation and clamping
        is_underflow = raw_occupancy < 0
        is_capacity_exceeded = raw_occupancy > active_capacity

        if is_underflow:
            clamped_occupancy = 0
            notes.append(f"Occupancy underflow ({raw_occupancy} < 0); clamped to 0.")
        elif is_capacity_exceeded:
            clamped_occupancy = active_capacity
            notes.append(f"Capacity exceeded ({raw_occupancy} > {active_capacity}); clamped to {active_capacity}.")
        else:
            clamped_occupancy = raw_occupancy

        # 6. Calculate percentage
        occupancy_pct = round((clamped_occupancy / active_capacity) * 100.0, 1)

        # 7. Severity classification matching Module 2
        if raw_occupancy >= active_capacity or occupancy_pct >= THRESHOLD_CRITICAL:
            alert_severity = SEVERITY_CRITICAL
            is_overcrowded = True
        elif occupancy_pct >= THRESHOLD_WARNING:
            alert_severity = SEVERITY_WARNING
            is_overcrowded = True
        else:
            alert_severity = SEVERITY_NORMAL
            is_overcrowded = False

        # 8. Update internal state
        self.current_occupancy = clamped_occupancy
        self.cumulative_boarding += safe_boarding
        self.cumulative_alighting += safe_alighting

        result = OccupancyUpdateResult(
            bus_id=active_bus_id,
            route_id=active_route_id,
            previous_occupancy=safe_prev,
            boarding=safe_boarding,
            alighting=safe_alighting,
            net_change=net_change,
            raw_calculated_occupancy=raw_occupancy,
            new_occupancy=clamped_occupancy,
            bus_capacity=active_capacity,
            occupancy_pct=occupancy_pct,
            alert_severity=alert_severity,
            is_overcrowded=is_overcrowded,
            is_underflow_detected=is_underflow,
            is_capacity_exceeded=is_capacity_exceeded,
            validation_notes=notes,
        )

        self.history.append(result)
        return result

    @staticmethod
    def _sanitize_integer(val: Any, default: int, field_name: str, notes: List[str]) -> int:
        """Safely sanitizes inputs, converting floats/numeric strings and guarding negatives."""
        if val is None:
            notes.append(f"Missing {field_name}; defaulted to {default}.")
            return default
        try:
            num = int(float(val))
            if num < 0:
                notes.append(f"Negative {field_name} ({val}) encountered; clamped to 0.")
                return 0
            return num
        except (ValueError, TypeError):
            notes.append(f"Invalid non-numeric {field_name} ({val}); defaulted to {default}.")
            return default


# ──────────────────────────────────────────────────────────────────────────────
# SELF-TEST SUITE
# ──────────────────────────────────────────────────────────────────────────────

def run_self_tests() -> bool:
    """
    Unit test suite covering:
      1. Normal boarding.
      2. Normal alighting.
      3. Simultaneous boarding and alighting.
      4. Zero passenger movement.
      5. Occupancy reaching full capacity.
      6. Occupancy exceeding capacity.
      7. Occupancy becoming negative.
      8. Missing or invalid input data.
    """
    print("=" * 64)
    print("  Module 4, Step 4: OccupancyIntegrator — Self-Test Suite")
    print("  Safe Formula: New Occupancy = Prev + Boarding - Alighting")
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

    integrator = OccupancyIntegrator(bus_id="KA-BUS-001", route_id="R101", bus_capacity=60)

    # 1. Normal boarding
    print("\n[TEST 1] Normal Boarding")
    r1 = integrator.update(boarding=8, alighting=0, previous_occupancy=20)
    check("New occupancy is 28 (20 + 8 - 0 = 28)", r1.new_occupancy == 28)
    check("Net change is +8", r1.net_change == 8)
    check("Occupancy percentage is 46.7%", r1.occupancy_pct == 46.7)
    check("Alert severity is Normal", r1.alert_severity == SEVERITY_NORMAL)

    # 2. Normal alighting
    print("\n[TEST 2] Normal Alighting")
    r2 = integrator.update(boarding=0, alighting=6, previous_occupancy=28)
    check("New occupancy is 22 (28 + 0 - 6 = 22)", r2.new_occupancy == 22)
    check("Net change is -6", r2.net_change == -6)
    check("Occupancy percentage is 36.7%", r2.occupancy_pct == 36.7)
    check("Alert severity is Normal", r2.alert_severity == SEVERITY_NORMAL)

    # 3. Simultaneous boarding and alighting
    print("\n[TEST 3] Simultaneous Boarding and Alighting")
    r3 = integrator.update(boarding=10, alighting=4, previous_occupancy=22)
    check("New occupancy is 28 (22 + 10 - 4 = 28)", r3.new_occupancy == 28)
    check("Net change is +6", r3.net_change == 6)
    check("Boarding is 10 and Alighting is 4", r3.boarding == 10 and r3.alighting == 4)

    # 4. Zero passenger movement
    print("\n[TEST 4] Zero Passenger Movement")
    r4 = integrator.update(boarding=0, alighting=0, previous_occupancy=28)
    check("New occupancy remains unchanged at 28", r4.new_occupancy == 28)
    check("Net change is 0", r4.net_change == 0)

    # 5. Occupancy reaching full capacity (100%)
    print("\n[TEST 5] Occupancy Reaching Full Capacity")
    r5 = integrator.update(boarding=32, alighting=0, previous_occupancy=28)
    check("New occupancy is exactly 60 (capacity)", r5.new_occupancy == 60)
    check("Occupancy percentage is 100.0%", r5.occupancy_pct == 100.0)
    check("Alert severity is Critical", r5.alert_severity == SEVERITY_CRITICAL)
    check("Is overcrowded is True", r5.is_overcrowded)

    # 6. Occupancy exceeding capacity (> 100%)
    print("\n[TEST 6] Occupancy Exceeding Capacity")
    r6 = integrator.update(boarding=10, alighting=0, previous_occupancy=55)
    check("Raw calculated is 65", r6.raw_calculated_occupancy == 65)
    check("Clamped occupancy does not exceed capacity 60", r6.new_occupancy == 60)
    check("is_capacity_exceeded flag is True", r6.is_capacity_exceeded)
    check("Alert severity is Critical", r6.alert_severity == SEVERITY_CRITICAL)
    check("Validation note generated for capacity overflow", any("Capacity exceeded" in n for n in r6.validation_notes))

    # 7. Occupancy becoming negative (< 0)
    print("\n[TEST 7] Occupancy Underflow (Negative Prevention)")
    r7 = integrator.update(boarding=0, alighting=15, previous_occupancy=5)
    check("Raw calculated is -10", r7.raw_calculated_occupancy == -10)
    check("Clamped occupancy does not go below 0", r7.new_occupancy == 0)
    check("is_underflow_detected flag is True", r7.is_underflow_detected)
    check("Validation note generated for underflow", any("underflow" in n.lower() for n in r7.validation_notes))

    # 8. Missing, None, or invalid input data
    print("\n[TEST 8] Missing or Invalid Input Data Handling")
    r8 = integrator.update(boarding=None, alighting="invalid", previous_occupancy=20)
    check("Handled None boarding safely (defaulted to 0)", r8.boarding == 0)
    check("Handled non-numeric alighting safely (defaulted to 0)", r8.alighting == 0)
    check("Occupancy preserved safely at 20", r8.new_occupancy == 20)

    # 9. Overcrowding warning threshold (85% to <100%)
    print("\n[TEST 9] Overcrowding Warning Threshold (85% - 99%)")
    r9 = integrator.update(boarding=52, alighting=0, previous_occupancy=0)
    # 52 / 60 = 86.7%
    check("Occupancy percentage is 86.7%", r9.occupancy_pct == 86.7)
    check("Alert severity is Warning", r9.alert_severity == SEVERITY_WARNING)
    check("is_overcrowded is True for Warning", r9.is_overcrowded)

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print(f"  RESULTS: {passed_checks}/{total_checks} checks passed, {total_checks - passed_checks} failed")
    if passed_checks == total_checks:
        print("  [OK] ALL OCCUPANCY INTEGRATOR TESTS PASSED")
    else:
        print("  [FAIL] SOME TESTS FAILED")
    print("=" * 64)

    return passed_checks == total_checks


if __name__ == "__main__":
    run_self_tests()

