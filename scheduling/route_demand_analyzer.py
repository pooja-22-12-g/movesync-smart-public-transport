"""
scheduling/route_demand_analyzer.py
===================================
Module 6, Step 1: Route Demand Analysis and Scheduling Foundation
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
PURPOSE:
  - Analyze passenger demand patterns across transit routes from historical telemetry.
  - Calculate total passenger boarding demand, average occupancy, max occupancy.
  - Identify peak-demand vs low-demand periods (hour-wise and day-type comparisons).
  - Track route vulnerability to warning (>=85%) and critical (>=100%) overcrowding.
  - Provide route-level demand profiling decoupled from UI and real-time actuators.
  - Strictly preserves original CSV dataset (data/bus_occupancy.csv) and Modules 1–5.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np

CSV_PATH = os.path.join("data", "movesync_kr_market_anekal_via_electronic_city.csv")
VALID_ROUTES = ["KR_MARKET_ANEKAL_VIA_ECITY", "R047", "R101", "R205", "R330"]
DEFAULT_CAPACITY = 60
WARNING_OCCUPANCY = 51   # 85% of 60
CRITICAL_OCCUPANCY = 60  # 100% of 60


@dataclass
class RouteDemandProfile:
    """Aggregated passenger demand metrics for a specific transit route."""
    route_id: str
    total_records: int
    total_boarding_demand: int
    total_alighting: int
    net_passenger_flux: int
    average_occupancy: float
    max_occupancy: int
    average_capacity: float
    average_occupancy_pct: float
    warning_occurrences: int
    critical_occurrences: int
    warning_rate_pct: float
    critical_rate_pct: float
    peak_demand_period: str
    low_demand_period: str
    weekday_mean_occupancy: float
    weekend_mean_occupancy: float
    demand_tier: str  # 'HIGH_DEMAND', 'MODERATE_DEMAND', 'LOW_DEMAND'
    provenance: str = "HISTORICAL_CSV_TELEMETRY"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HourlyDemandProfile:
    """Aggregated hourly passenger flow across all routes or for a single route."""
    hour: int
    hour_label: str  # e.g. "08:00 - 09:00"
    total_boarding: int
    average_occupancy: float
    max_occupancy: int
    record_count: int
    warning_frequency_pct: float
    is_peak_hour: bool
    demand_level: str  # 'PEAK', 'SHOULDER', 'OFF_PEAK'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RouteDemandAnalyzer:
    """
    Performs comprehensive statistical demand analysis across transit routes and operating hours.
    Operates in read-only mode over data/bus_occupancy.csv or provided DataFrames.
    """

    def __init__(self, csv_path: str = CSV_PATH):
        self.csv_path = csv_path
        self._df: Optional[pd.DataFrame] = None

    def _load_data(self) -> pd.DataFrame:
        """Loads and pre-processes telemetry data without modifying the source file."""
        if self._df is not None:
            return self._df

        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"Dataset not found at {self.csv_path}")

        df = pd.read_csv(self.csv_path)
        # Parse timestamp
        df["timestamp_dt"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["hour"] = df["timestamp_dt"].dt.hour
        # Clean numerical fields safely
        for col in ["boarding", "alighting", "current_occupancy", "bus_capacity", "previous_occupancy", "peak_hour"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        self._df = df
        return df

    def get_route_demand_summary(self, route_id: Optional[str] = None) -> Dict[str, RouteDemandProfile]:
        """
        Calculates demand profiles for all routes in the dataset or a specific target route.
        """
        df = self._load_data()
        available_routes = sorted(df["route_id"].dropna().astype(str).unique().tolist())
        routes = [route_id] if route_id and route_id in available_routes else available_routes
        results: Dict[str, RouteDemandProfile] = {}

        for r in routes:
            r_df = df[df["route_id"] == r]
            if r_df.empty:
                continue

            total_records = len(r_df)
            tot_boarding = int(r_df["boarding"].sum())
            tot_alighting = int(r_df["alighting"].sum())
            mean_occ = round(float(r_df["current_occupancy"].mean()), 2)
            max_occ = int(r_df["current_occupancy"].max())
            mean_cap = round(float(r_df["bus_capacity"].mean()), 1)
            mean_occ_pct = round((mean_occ / mean_cap) * 100.0, 1) if mean_cap > 0 else 0.0

            warn_count = int((r_df["current_occupancy"] >= WARNING_OCCUPANCY).sum())
            crit_count = int((r_df["current_occupancy"] >= CRITICAL_OCCUPANCY).sum())
            warn_rate = round((warn_count / total_records) * 100.0, 2)
            crit_rate = round((crit_count / total_records) * 100.0, 2)

            # Weekday vs Weekend means
            wk_df = r_df[r_df["day_type"].str.lower() == "weekday"]
            we_df = r_df[r_df["day_type"].str.lower() == "weekend"]
            wk_mean = round(float(wk_df["current_occupancy"].mean()), 2) if not wk_df.empty else mean_occ
            we_mean = round(float(we_df["current_occupancy"].mean()), 2) if not we_df.empty else mean_occ

            # Hourly distribution to identify peak vs low periods
            hourly_means = r_df.groupby("hour")["current_occupancy"].mean()
            peak_h = int(hourly_means.idxmax()) if not hourly_means.empty else 9
            low_h = int(hourly_means.idxmin()) if not hourly_means.empty else 6

            peak_period = f"{peak_h:02d}:00 - {peak_h+1:02d}:00"
            low_period = f"{low_h:02d}:00 - {low_h+1:02d}:00"

            # Demand tier classification
            if crit_count >= 15 or warn_rate >= 7.0 or mean_occ >= 21.0:
                tier = "HIGH_DEMAND"
            elif warn_count >= 10 or mean_occ >= 18.0:
                tier = "MODERATE_DEMAND"
            else:
                tier = "LOW_DEMAND"

            results[r] = RouteDemandProfile(
                route_id=r,
                total_records=total_records,
                total_boarding_demand=tot_boarding,
                total_alighting=tot_alighting,
                net_passenger_flux=tot_boarding - tot_alighting,
                average_occupancy=mean_occ,
                max_occupancy=max_occ,
                average_capacity=mean_cap,
                average_occupancy_pct=mean_occ_pct,
                warning_occurrences=warn_count,
                critical_occurrences=crit_count,
                warning_rate_pct=warn_rate,
                critical_rate_pct=crit_rate,
                peak_demand_period=peak_period,
                low_demand_period=low_period,
                weekday_mean_occupancy=wk_mean,
                weekend_mean_occupancy=we_mean,
                demand_tier=tier,
            )

        return results

    def get_hourly_demand_breakdown(self, route_id: Optional[str] = None) -> List[HourlyDemandProfile]:
        """
        Generates hour-by-hour passenger flow, identifying peak vs shoulder vs off-peak hours.
        """
        df = self._load_data()
        data = df[df["route_id"] == route_id] if route_id and route_id in VALID_ROUTES else df

        hourly_profiles: List[HourlyDemandProfile] = []
        grouped = data.groupby("hour")

        for h, grp in grouped:
            hour_int = int(h)
            h_boarding = int(grp["boarding"].sum())
            h_mean_occ = round(float(grp["current_occupancy"].mean()), 2)
            h_max_occ = int(grp["current_occupancy"].max())
            rec_cnt = len(grp)
            warn_pct = round(float((grp["current_occupancy"] >= WARNING_OCCUPANCY).mean()) * 100.0, 1)

            # Classify peak hour: in dataset peak_hour is 1 during morning (07-10) and evening (17-20)
            is_peak = bool(grp["peak_hour"].mode().iloc[0] == 1) if not grp.empty else (hour_int in [7, 8, 9, 10, 17, 18, 19, 20])

            if is_peak or h_mean_occ >= 25.0:
                demand_lvl = "PEAK"
            elif h_mean_occ >= 15.0 or warn_pct > 0.0:
                demand_lvl = "SHOULDER"
            else:
                demand_lvl = "OFF_PEAK"

            hourly_profiles.append(HourlyDemandProfile(
                hour=hour_int,
                hour_label=f"{hour_int:02d}:00 - {hour_int+1:02d}:00",
                total_boarding=h_boarding,
                average_occupancy=h_mean_occ,
                max_occupancy=h_max_occ,
                record_count=rec_cnt,
                warning_frequency_pct=warn_pct,
                is_peak_hour=is_peak,
                demand_level=demand_lvl,
            ))

        return sorted(hourly_profiles, key=lambda x: x.hour)

    def get_weekday_vs_weekend_comparison(self) -> Dict[str, Dict[str, Any]]:
        """
        Compares passenger demand metrics between weekday and weekend operations per route.
        """
        df = self._load_data()
        comparison: Dict[str, Dict[str, Any]] = {}

        for r in VALID_ROUTES:
            r_df = df[df["route_id"] == r]
            wk = r_df[r_df["day_type"].str.lower() == "weekday"]
            we = r_df[r_df["day_type"].str.lower() == "weekend"]

            comparison[r] = {
                "route_id": r,
                "weekday": {
                    "records": len(wk),
                    "total_boarding": int(wk["boarding"].sum()) if not wk.empty else 0,
                    "mean_occupancy": round(float(wk["current_occupancy"].mean()), 2) if not wk.empty else 0.0,
                    "max_occupancy": int(wk["current_occupancy"].max()) if not wk.empty else 0,
                    "warning_count": int((wk["current_occupancy"] >= WARNING_OCCUPANCY).sum()) if not wk.empty else 0,
                    "critical_count": int((wk["current_occupancy"] >= CRITICAL_OCCUPANCY).sum()) if not wk.empty else 0,
                },
                "weekend": {
                    "records": len(we),
                    "total_boarding": int(we["boarding"].sum()) if not we.empty else 0,
                    "mean_occupancy": round(float(we["current_occupancy"].mean()), 2) if not we.empty else 0.0,
                    "max_occupancy": int(we["current_occupancy"].max()) if not we.empty else 0,
                    "warning_count": int((we["current_occupancy"] >= WARNING_OCCUPANCY).sum()) if not we.empty else 0,
                    "critical_count": int((we["current_occupancy"] >= CRITICAL_OCCUPANCY).sum()) if not we.empty else 0,
                },
                "weekend_to_weekday_ratio": round(
                    (float(we["current_occupancy"].mean()) / float(wk["current_occupancy"].mean())) if not wk.empty and wk["current_occupancy"].mean() > 0 else 0.0,
                    2
                ),
            }

        return comparison

