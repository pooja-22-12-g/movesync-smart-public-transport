"""
Firebase Database Seeding & Synchronization Engine
Part of Module 7: Firebase Backend Development
Smart Public Transport Occupancy and Fleet Monitoring System

Capabilities:
1. Connects to Firestore via config.firebase_config (Mock or Live mode).
2. Seeds static transit topography from data/route_coordinates.csv (4 routes, 44 stops).
3. Seeds initial 20 fleet vehicles (KA-BUS-001 to KA-BUS-020) and global thresholds.
4. Synchronizes live telemetry and operational state from Modules 1-6:
   - Module 1: Current Occupancy & Status
   - Module 2: Overcrowding Alerts
   - Module 3: Bus Spatial Positions
   - Module 5: Multi-Stop Random Forest Predictions
   - Module 6: Dynamic Timetable Schedules & Dispatch Interventions
   - Fuel Telemetry (0.200 + 0.004 * occupancy, labeled SYNTHETIC_ESTIMATED_TELEMETRY).
5. Enforces strict provenance tagging and in-flight payload validation.
6. Preserves original CSV data (data/bus_occupancy.csv) in 100% read-only mode.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np

# Import Firebase Configuration from Step 2
from config.firebase_config import get_firebase_app, MockFirestoreClient, FirebaseStatus

# Configure logger
logger = logging.getLogger("FirebaseSyncBridge")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Operational Constants
VALID_ROUTES = ["KR_MARKET_ANEKAL_VIA_ECITY", "R047", "R101", "R205", "R330"]
STANDARD_CAPACITY = 60
WARNING_THRESHOLD_PCT = 70.0
CRITICAL_THRESHOLD_PCT = 90.0

class FirebaseSyncBridge:
    def __init__(self, credentials_path: Optional[str] = None):
        self.db, self.status = get_firebase_app(credentials_path)
        logger.info(f"FirebaseSyncBridge initialized in {self.status.mode} mode.")
        self._sync_stats = {
            "routes_seeded": 0,
            "buses_seeded": 0,
            "config_seeded": False,
            "occupancy_synced": 0,
            "locations_synced": 0,
            "alerts_synced": 0,
            "predictions_synced": 0,
            "schedules_synced": 0,
            "dispatches_synced": 0,
            "fuel_records_synced": 0,
            "validation_errors": 0,
        }

    # --------------------------------------------------------------------------
    # 1. VALIDATION LAYER (Required because Admin SDK bypasses Security Rules)
    # --------------------------------------------------------------------------
    def validate_bus_state(self, data: Dict[str, Any]) -> bool:
        """Validate bus document before write."""
        required = ["bus_id", "capacity", "current_occupancy", "occupancy_pct", "occupancy_status", "status"]
        if not all(k in data for k in required):
            logger.warning(f"Validation failed: missing keys in bus payload: {data.keys()}")
            self._sync_stats["validation_errors"] += 1
            return False
        if not (0 <= data["current_occupancy"] <= data["capacity"]):
            logger.warning(f"Validation failed: occupancy out of range: {data['current_occupancy']}/{data['capacity']}")
            self._sync_stats["validation_errors"] += 1
            return False
        return True

    def validate_location(self, data: Dict[str, Any]) -> bool:
        """Validate geographic coordinates within Bangalore envelope."""
        required = ["bus_id", "latitude", "longitude", "data_provenance"]
        if not all(k in data for k in required):
            self._sync_stats["validation_errors"] += 1
            return False
        lat, lon = data["latitude"], data["longitude"]
        if not (12.70 <= lat <= 13.25 and 77.30 <= lon <= 77.90):
            logger.warning(f"Validation failed: coordinates outside bounding envelope ({lat}, {lon})")
            self._sync_stats["validation_errors"] += 1
            return False
        return True

    # --------------------------------------------------------------------------
    # 2. DATABASE SEEDING
    # --------------------------------------------------------------------------
    def seed_system_config(self) -> bool:
        """Seed global system configuration and configurable thresholds."""
        try:
            config_data = {
                "config_id": "crowding_thresholds",
                "standard_bus_capacity": STANDARD_CAPACITY,
                "warning_threshold_pct": WARNING_THRESHOLD_PCT,
                "warning_passenger_count": int(STANDARD_CAPACITY * (WARNING_THRESHOLD_PCT / 100)),
                "critical_threshold_pct": CRITICAL_THRESHOLD_PCT,
                "critical_passenger_count": int(STANDARD_CAPACITY * (CRITICAL_THRESHOLD_PCT / 100)),
                "anti_bunching_min_headway_mins": 5,
                "wait_ceiling_max_headway_mins": 30,
                "recovery_target_pct": 85.0,
                "data_provenance": "SYSTEM_SPECIFICATION",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.db.collection("system_config").document("crowding_thresholds").set(config_data)
            self._sync_stats["config_seeded"] = True
            logger.info("Successfully seeded system configuration and thresholds.")
            return True
        except Exception as e:
            logger.error(f"Failed to seed system configuration: {e}")
            return False

    def seed_routes_and_stops(self, csv_coords_path: str = "data/route_coordinates.csv", dataset_path: str = "data/movesync_kr_market_anekal_via_electronic_city.csv") -> int:
        """Seed routes and stops from the active dataset, attaching verified GPS coordinates only where available."""
        coord_lookup: Dict[str, Dict[str, float]] = {}
        if os.path.exists(csv_coords_path):
            df_coords = pd.read_csv(csv_coords_path)
            for _, crow in df_coords.iterrows():
                coord_lookup[str(crow["stop_name"]).strip().lower()] = {
                    "latitude": float(crow["latitude"]),
                    "longitude": float(crow["longitude"]),
                }

        if os.path.exists(dataset_path):
            df_occ = pd.read_csv(dataset_path, usecols=lambda c: c in ["route_id", "stop_id", "stop_name", "stop_sequence"])
            if "stop_name" in df_occ.columns and "stop_sequence" in df_occ.columns:
                count = 0
                for route_id, group in df_occ.groupby("route_id"):
                    unique_stops = group[["stop_id", "stop_name", "stop_sequence"]].drop_duplicates().sort_values("stop_sequence")
                    stops_list = []
                    for _, row in unique_stops.iterrows():
                        s_name = str(row["stop_name"]).strip()
                        coords = coord_lookup.get(s_name.lower())
                        stops_list.append({
                            "stop_id": str(row["stop_id"]),
                            "stop_order": int(row["stop_sequence"]),
                            "stop_name": s_name,
                            "latitude": coords["latitude"] if coords else None,
                            "longitude": coords["longitude"] if coords else None,
                            "gps_available": coords is not None,
                            "data_provenance": "SURVEYED_GPS" if coords else "DATASET_STOP_SEQUENCE_NO_GPS",
                        })
                    route_doc = {
                        "route_id": str(route_id),
                        "route_name": f"{stops_list[0]['stop_name']} → {stops_list[-1]['stop_name']}",
                        "demand_profile": "HIGH_DEMAND",
                        "base_cycle_time_mins": 95,
                        "total_stops": len(stops_list),
                        "stops": stops_list,
                        "data_provenance": "DATASET_ROUTE_SEQUENCE",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    self.db.collection("routes").document(str(route_id)).set(route_doc)
                    count += 1
                self._sync_stats["routes_seeded"] = count
                logger.info(f"Successfully seeded {count} route(s) from {dataset_path}.")
                return count

        if not os.path.exists(csv_coords_path):
            logger.error(f"Route coordinates file not found at {csv_coords_path}")
            return 0
        return 0

    def seed_initial_fleet(self) -> int:
        """Seed 20 fleet vehicles (KA-BUS-001 to KA-BUS-020)."""
        buses = []
        for i in range(1, 21):
            bus_id = f"KA-BUS-{i:03d}"
            route = "KR_MARKET_ANEKAL_VIA_ECITY" if i <= 18 else None
            status = "IN_SERVICE" if route else "STANDBY_DEPOT"
            bus_doc = {
                "bus_id": bus_id,
                "plate_number": f"KA-01-F-{1000 + i}",
                "capacity": STANDARD_CAPACITY,
                "warning_threshold": int(STANDARD_CAPACITY * (WARNING_THRESHOLD_PCT / 100)),
                "critical_threshold": int(STANDARD_CAPACITY * (CRITICAL_THRESHOLD_PCT / 100)),
                "current_route_id": route,
                "current_trip_id": None,
                "status": status,
                "current_occupancy": 0,
                "occupancy_pct": 0.0,
                "occupancy_status": "NORMAL",
                "last_stop_id": "S01" if route else "DEPOT_CENTRAL",
                "last_stop_name": "KR Market (Kalasipalya)" if route else "Central Depot",
                "is_relief_bus": i in [19, 20],
                "data_provenance": "FLEET_REGISTRY_SEED",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            if self.validate_bus_state(bus_doc):
                self.db.collection("buses").document(bus_id).set(bus_doc)
                buses.append(bus_doc)

        self._sync_stats["buses_seeded"] = len(buses)
        logger.info(f"Successfully seeded {len(buses)} fleet vehicles.")
        return len(buses)

    # --------------------------------------------------------------------------
    # 3. SYNCHRONIZATION WITH MODULES 1-6 OUTPUTS
    # --------------------------------------------------------------------------
    def sync_occupancy_and_telemetry(self, occupancy_records: List[Dict[str, Any]]) -> int:
        """
        Synchronize stop-level occupancy arrivals and update current bus documents.
        Supports both historical dataset replays and live CV counting outputs.
        """
        synced = 0
        for rec in occupancy_records:
            bus_id = rec.get("bus_id")
            route_id = rec.get("route_id")
            occ = int(rec.get("current_occupancy", 0))
            cap = int(rec.get("bus_capacity", STANDARD_CAPACITY))
            occ_pct = round((occ / cap) * 100.0, 1)

            status = "CRITICAL" if occ >= 45 else ("WARNING" if occ >= 35 else "NORMAL")
            prov = rec.get("data_provenance", "HISTORICAL_DATASET")

            # 1. Update vehicle state document in /buses
            bus_update = {
                "bus_id": bus_id,
                "capacity": cap,
                "current_occupancy": occ,
                "occupancy_pct": occ_pct,
                "occupancy_status": status,
                "current_route_id": route_id,
                "last_stop_id": rec.get("stop_id"),
                "status": "IN_SERVICE",
                "data_provenance": prov,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            if self.validate_bus_state(bus_update):
                self.db.collection("buses").document(bus_id).set(bus_update, merge=True)

            # 2. Save individual telemetry record in /occupancy_records
            doc_id = f"REC_{bus_id}_{rec.get('stop_id')}_{int(datetime.now(timezone.utc).timestamp())}_{synced}"
            telemetry_doc = dict(rec)
            telemetry_doc.update({
                "occupancy_pct": occ_pct,
                "occupancy_status": status,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            self.db.collection("occupancy_records").document(doc_id).set(telemetry_doc)

            # 3. Synchronize fuel telemetry record (SYNTHETIC_ESTIMATED_TELEMETRY)
            fuel_doc_id = f"FUEL_{bus_id}_{rec.get('stop_id')}_{int(datetime.now(timezone.utc).timestamp())}_{synced}"
            fuel_amount = round(0.200 + 0.004 * occ, 3)
            fuel_doc = {
                "telemetry_id": fuel_doc_id,
                "bus_id": bus_id,
                "route_id": route_id,
                "stop_id": rec.get("stop_id"),
                "current_occupancy": occ,
                "fuel_consumed_litres": fuel_amount,
                "formula_basis": "0.200 + 0.004 * occupancy",
                "data_provenance": "SYNTHETIC_ESTIMATED_TELEMETRY",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.db.collection("fuel_telemetry").document(fuel_doc_id).set(fuel_doc)
            self._sync_stats["fuel_records_synced"] += 1

            synced += 1

        self._sync_stats["occupancy_synced"] += synced
        return synced

    def sync_bus_locations(self, location_updates: List[Dict[str, Any]]) -> int:
        """
        Synchronize vehicle spatial positions into /bus_locations.
        Overwrites document per bus_id for efficient streaming.
        """
        synced = 0
        for loc in location_updates:
            bus_id = loc.get("bus_id")
            if not bus_id:
                continue
            loc_doc = dict(loc)
            loc_doc["timestamp"] = datetime.now(timezone.utc).isoformat()
            if self.validate_location(loc_doc):
                self.db.collection("bus_locations").document(bus_id).set(loc_doc)
                synced += 1

        self._sync_stats["locations_synced"] += synced
        return synced

    def sync_crowding_alerts(self, alerts: List[Dict[str, Any]]) -> int:
        """Synchronize active crowding alerts into /crowding_alerts."""
        synced = 0
        for alert in alerts:
            alert_id = alert.get("alert_id") or f"ALERT_{alert.get('bus_id')}_{int(datetime.now(timezone.utc).timestamp())}_{synced}"
            doc = dict(alert)
            doc["alert_id"] = alert_id
            doc.setdefault("is_acknowledged", False)
            doc.setdefault("acknowledged_by", None)
            doc.setdefault("alert_status", "ACTIVE")
            doc.setdefault("data_provenance", "RULE_ENGINE_DERIVED")
            doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())

            self.db.collection("crowding_alerts").document(alert_id).set(doc)
            synced += 1

        self._sync_stats["alerts_synced"] += synced
        return synced

    def sync_multi_stop_predictions(self, prediction_payloads: List[Dict[str, Any]]) -> int:
        """
        Synchronize Random Forest 1-, 2-, 3-stop ahead predictions from Module 5.
        """
        synced = 0
        for pred in prediction_payloads:
            bus_id = pred.get("bus_id")
            stop_id = pred.get("current_stop_id")
            doc_id = f"PRED_{bus_id}_{stop_id}"

            pred_doc = dict(pred)
            pred_doc["data_provenance"] = "ML_INFERENCE_ESTIMATE"
            pred_doc["generated_at"] = datetime.now(timezone.utc).isoformat()

            self.db.collection("occupancy_predictions").document(doc_id).set(pred_doc)
            synced += 1

        self._sync_stats["predictions_synced"] += synced
        return synced

    def sync_schedules_and_dispatches(self, schedules: List[Dict[str, Any]], dispatches: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Synchronize dynamic headway timetables and dispatch interventions from Module 6.
        """
        s_count = 0
        for sched in schedules:
            doc_id = f"SCHED_{sched.get('route_id')}_{sched.get('day_type', 'WEEKDAY').upper()}"
            sched_doc = dict(sched)
            sched_doc["data_provenance"] = "DATA_DRIVEN_ADVISORY_TIMETABLE"
            sched_doc["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.db.collection("schedules").document(doc_id).set(sched_doc)
            s_count += 1

        d_count = 0
        for disp in dispatches:
            doc_id = disp.get("recommendation_id") or f"DISP_{disp.get('route_id')}_{int(datetime.now(timezone.utc).timestamp())}_{d_count}"
            disp_doc = dict(disp)
            disp_doc["recommendation_id"] = doc_id
            disp_doc["data_provenance"] = "ADVISORY_DISPATCH_ENGINE"
            disp_doc.setdefault("authority_decision", "PENDING")
            disp_doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            self.db.collection("dispatch_recommendations").document(doc_id).set(disp_doc)
            d_count += 1

        self._sync_stats["schedules_synced"] += s_count
        self._sync_stats["dispatches_synced"] += d_count
        return s_count, d_count

    def get_stats(self) -> Dict[str, Any]:
        """Return operational synchronization metrics."""
        return {
            "mode": self.status.mode,
            "is_live": self.status.is_live,
            **self._sync_stats
        }

