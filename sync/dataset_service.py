"""
Indexed Dataset Query Service for MoveSync
Reads data/bus_occupancy.csv (186,000 records, 3,720 trips, 20 buses, 50 stops)
in read-only mode to power stop search, journey planning, saved trips,
and actual bus-wise upcoming stops with boarding/alighting/occupancy projections.
"""

import os
from typing import List, Dict, Any, Optional
import pandas as pd

from model import predict_future_occupancy


def crowd_label(occupancy: int, capacity: int) -> str:
    pct = (occupancy / capacity) * 100.0 if capacity > 0 else 0.0
    if pct >= 95.0:
        return "Full"
    if pct >= 75.0:
        return "High"
    if pct >= 45.0:
        return "Moderate"
    return "Low"


class DatasetQueryService:
    def __init__(self, csv_path: str = "data/movesync_kr_market_anekal_via_electronic_city.csv", coords_path: str = "data/route_coordinates.csv"):
        self.csv_path = csv_path
        self.coords_path = coords_path
        self._df: Optional[pd.DataFrame] = None
        self._stops: List[Dict[str, Any]] = []
        self._bus_snapshots: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.csv_path):
            return
        df = pd.read_csv(self.csv_path)
        self._df = df

        coord_lookup: Dict[str, Dict[str, float]] = {}
        if os.path.exists(self.coords_path):
            cdf = pd.read_csv(self.coords_path)
            for _, row in cdf.iterrows():
                coord_lookup[str(row["stop_name"]).strip().lower()] = {
                    "latitude": float(row["latitude"]),
                    "longitude": float(row["longitude"]),
                }

        if "stop_name" in df.columns and "stop_sequence" in df.columns:
            unique_stops = df[["route_id", "stop_id", "stop_name", "stop_sequence"]].drop_duplicates().sort_values("stop_sequence")
            seen_names = set()
            for _, row in unique_stops.iterrows():
                name = str(row["stop_name"]).strip()
                if name.lower() in seen_names:
                    continue
                seen_names.add(name.lower())
                coords = coord_lookup.get(name.lower())
                self._stops.append({
                    "stop_id": str(row["stop_id"]),
                    "stop_name": name,
                    "stop_sequence": int(row["stop_sequence"]),
                    "route_id": str(row["route_id"]),
                    "latitude": coords["latitude"] if coords else None,
                    "longitude": coords["longitude"] if coords else None,
                    "gps_available": coords is not None,
                    "data_provenance": "SURVEYED_GPS" if coords else "DATASET_STOP_SEQUENCE_NO_GPS",
                })

        # Assign each of the 20 buses a distinct active trip and varied stop_sequence
        # (so different buses sit at different stops like KR Market, Madiwala, Electronic City, etc.)
        buses = sorted(df["bus_id"].unique().tolist())
        for idx, bus_id in enumerate(buses):
            b_df = df[df["bus_id"] == bus_id]
            last_trip_id = int(b_df["trip_id"].max())
            trip_rows = b_df[b_df["trip_id"] == last_trip_id].sort_values("stop_sequence")
            # Pick a varied stop index (between 2 and 38) so every bus has real upcoming stops
            target_seq = min(40, max(2, ((idx * 3) % 36) + 2))
            match = trip_rows[trip_rows["stop_sequence"] == target_seq]
            row = match.iloc[0] if not match.empty else trip_rows.iloc[0]
            cap = int(row["bus_capacity"])
            occ = int(row["current_occupancy"])
            cur_seq = int(row["stop_sequence"]) if "stop_sequence" in row else 1
            next_rows = trip_rows[trip_rows["stop_sequence"] > cur_seq]
            next_row = next_rows.iloc[0] if not next_rows.empty else None
            self._bus_snapshots[str(bus_id)] = {
                "bus_id": str(bus_id),
                "trip_id": int(row["trip_id"]),
                "route_id": str(row["route_id"]),
                "route_name": "KR Market → Anekal",
                "stop_id": str(row["stop_id"]),
                "stop_name": str(row["stop_name"]) if "stop_name" in row else str(row["stop_id"]),
                "stop_sequence": cur_seq,
                "next_stop_id": str(next_row["stop_id"]) if next_row is not None else None,
                "next_stop_name": str(next_row["stop_name"]) if next_row is not None else None,
                "next_stop_sequence": int(next_row["stop_sequence"]) if next_row is not None else None,
                "current_occupancy": occ,
                "bus_capacity": cap,
                "available_seats": max(0, cap - occ),
                "occupancy_pct": round((occ / cap) * 100.0, 1) if cap > 0 else 0.0,
                "boarding": int(row["boarding"]),
                "alighting": int(row["alighting"]),
                "timestamp": str(row["timestamp"]),
                "data_provenance": "SYNTHETIC_DATASET_SNAPSHOT",
            }

    def get_active_route(self) -> Dict[str, Any]:
        return {
            "route_id": "KR_MARKET_ANEKAL_VIA_ECITY",
            "route_name": "KR Market → Anekal (via Electronic City)",
            "demand_profile": "HIGH_CORRIDOR_DEMAND",
            "base_cycle_time_mins": 110,
            "total_stops": len(self._stops),
            "stops": [
                {
                    "stop_id": s["stop_id"],
                    "stop_order": s["stop_sequence"],
                    "stop_name": s["stop_name"],
                    "latitude": s["latitude"],
                    "longitude": s["longitude"],
                    "gps_available": s["gps_available"],
                }
                for s in self._stops
            ],
            "data_provenance": "ACTIVE_50_STOP_DATASET",
        }

    def get_buses_for_stop(self, stop_query: str) -> Dict[str, Any]:
        stop = self._find_stop(stop_query)
        if not stop:
            return {"found": False, "stop": None, "count": 0, "buses": []}
        buses = []
        target_seq = int(stop["stop_sequence"])
        for bus_id in sorted(self._bus_snapshots.keys()):
            snap = self._bus_snapshots[bus_id]
            cap = int(snap["bus_capacity"])
            occ = int(snap["current_occupancy"])
            buses.append({
                "bus_id": bus_id,
                "trip_id": snap["trip_id"],
                "route_id": snap["route_id"],
                "route_name": snap["route_name"],
                "current_stop_id": snap["stop_id"],
                "current_stop_name": snap["stop_name"],
                "current_stop_sequence": snap["stop_sequence"],
                "next_stop_id": snap["next_stop_id"],
                "next_stop_name": snap["next_stop_name"],
                "current_occupancy": occ,
                "bus_capacity": cap,
                "available_seats": max(0, cap - occ),
                "occupancy_pct": snap["occupancy_pct"],
                "crowd_status": crowd_label(occ, cap),
                "upcoming_to_stop": int(snap["stop_sequence"]) <= target_seq,
                "data_provenance": "SYNTHETIC_DATASET_SNAPSHOT",
            })
        return {
            "found": True,
            "stop": stop,
            "count": len(buses),
            "buses": buses,
        }

    def get_all_stops(self) -> List[Dict[str, Any]]:
        return list(self._stops)

    def search_stops(self, query: str) -> List[Dict[str, Any]]:
        q = query.strip().lower()
        if not q:
            return list(self._stops)
        return [s for s in self._stops if q in s["stop_name"].lower() or q in s["stop_id"].lower()]

    def get_bus_snapshots(self) -> Dict[str, Dict[str, Any]]:
        return self._bus_snapshots

    def _find_stop(self, stop_query: str) -> Optional[Dict[str, Any]]:
        q = stop_query.strip().lower()
        for s in self._stops:
            if s["stop_name"].lower() == q or s["stop_id"].lower() == q:
                return s
        for s in self._stops:
            if q in s["stop_name"].lower():
                return s
        return None

    def search_journeys(self, source: str, destination: str, limit: int = 20) -> Dict[str, Any]:
        if self._df is None or self._df.empty:
            return {"valid": False, "message": "Dataset not loaded.", "journeys": []}

        src = self._find_stop(source)
        dst = self._find_stop(destination)
        if not src or not dst:
            return {"valid": False, "message": "No direct bus available: invalid starting or destination stop.", "journeys": []}

        src_seq = src["stop_sequence"]
        dst_seq = dst["stop_sequence"]
        if dst_seq <= src_seq:
            return {
                "valid": False,
                "message": f"No direct bus available from {src['stop_name']} to {dst['stop_name']} (destination must follow starting stop).",
                "journeys": [],
            }

        intermediate = [
            s["stop_name"] for s in self._stops if src_seq < s["stop_sequence"] < dst_seq
        ]

        # Match actual trip records serving BOTH src_seq and dst_seq
        df = self._df
        src_rows = df[df["stop_sequence"] == src_seq]
        dst_rows = df[df["stop_sequence"] == dst_seq]
        merged = pd.merge(
            src_rows[["trip_id", "bus_id", "route_id", "timestamp", "current_occupancy", "bus_capacity"]],
            dst_rows[["trip_id", "timestamp", "current_occupancy"]],
            on="trip_id",
            suffixes=("_src", "_dst"),
        )
        # Prefer each bus's active simulated trip if it serves both stops; otherwise latest trip per bus_id
        active_trip_by_bus = {
            b_id: int(snap["trip_id"]) for b_id, snap in self._bus_snapshots.items()
        }
        merged["is_active_trip"] = merged.apply(
            lambda r: int(r["trip_id"]) == active_trip_by_bus.get(str(r["bus_id"]), -1),
            axis=1,
        )
        merged = (
            merged.sort_values(["is_active_trip", "trip_id"], ascending=[False, False])
            .drop_duplicates(subset=["bus_id"])
            .head(limit)
        )

        journeys = []
        for _, r in merged.iterrows():
            occ = int(r["current_occupancy_src"])
            cap = int(r["bus_capacity"])
            pct = round((occ / cap) * 100.0, 1) if cap > 0 else 0.0
            journeys.append({
                "bus_id": str(r["bus_id"]),
                "trip_id": int(r["trip_id"]),
                "route_id": str(r["route_id"]),
                "route_name": f"{src['stop_name']} → {dst['stop_name']}",
                "corridor_name": "KR Market → Anekal",
                "boarding_stop": src["stop_name"],
                "boarding_stop_id": src["stop_id"],
                "boarding_sequence": src_seq,
                "destination_stop": dst["stop_name"],
                "destination_stop_id": dst["stop_id"],
                "destination_sequence": dst_seq,
                "boarding_time": str(r["timestamp_src"]),
                "destination_time": str(r["timestamp_dst"]),
                "current_occupancy": occ,
                "bus_capacity": cap,
                "available_seats": max(0, cap - occ),
                "occupancy_pct": pct,
                "crowd_status": crowd_label(occ, cap),
                "intermediate_stops": intermediate,
                "total_stops": dst_seq - src_seq + 1,
                "data_provenance": "SYNTHETIC_DATASET_TIMETABLE",
            })

        if not journeys:
            return {"valid": False, "message": "No direct bus found for the selected stops.", "journeys": []}

        return {
            "valid": True,
            "source_stop": src["stop_name"],
            "destination_stop": dst["stop_name"],
            "intermediate_stops": intermediate,
            "count": len(journeys),
            "journeys": journeys,
        }

    def get_bus_upcoming_stops(
        self,
        bus_id: str,
        trip_id: Optional[int] = None,
        current_stop_seq: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        if self._df is None or self._df.empty:
            return {
                "bus_id": bus_id,
                "predictions_available": False,
                "message": "Prediction not available: dataset not loaded.",
                "upcoming_stops": [],
                "less_crowded_alternatives": [],
            }

        snap = self._bus_snapshots.get(bus_id)
        if not snap:
            return {
                "bus_id": bus_id,
                "predictions_available": False,
                "message": f"Prediction not available: no active trip found for {bus_id}.",
                "upcoming_stops": [],
                "less_crowded_alternatives": [],
            }

        t_id = int(trip_id if trip_id is not None else snap["trip_id"])
        c_seq = int(current_stop_seq if current_stop_seq is not None else snap["stop_sequence"])

        trip_df = self._df[
            (self._df["bus_id"] == bus_id) & (self._df["trip_id"] == t_id)
        ].sort_values("stop_sequence")
        if trip_df.empty:
            return {
                "bus_id": bus_id,
                "trip_id": t_id,
                "predictions_available": False,
                "message": f"Prediction not available for {bus_id} trip {t_id}.",
                "upcoming_stops": [],
                "less_crowded_alternatives": [],
            }

        cur_row = trip_df[trip_df["stop_sequence"] == c_seq]
        cur_occ = int(cur_row.iloc[0]["current_occupancy"]) if not cur_row.empty else snap["current_occupancy"]
        cur_cap = int(cur_row.iloc[0]["bus_capacity"]) if not cur_row.empty else snap["bus_capacity"]
        cur_name = str(cur_row.iloc[0]["stop_name"]) if not cur_row.empty else snap["stop_name"]
        cur_stop_id = str(cur_row.iloc[0]["stop_id"]) if not cur_row.empty else snap["stop_id"]

        upcoming_df = trip_df[trip_df["stop_sequence"] > c_seq]
        if limit is not None and limit > 0:
            upcoming_df = upcoming_df.head(limit)

        # Predict future occupancy for each upcoming stop using the Random Forest model
        # Each row i in trip_df predicts future_occupancy at row i+1, so we feed the
        # preceding stop rows (stop_sequence >= c_seq up to the second-to-last upcoming stop).
        preds_by_seq: Dict[int, int] = {}
        prediction_available = False
        if not upcoming_df.empty:
            try:
                prev_rows = trip_df[trip_df["stop_sequence"] >= c_seq].iloc[: len(upcoming_df)]
                if len(prev_rows) == len(upcoming_df):
                    raw_preds = predict_future_occupancy(prev_rows)
                    for (_, u_row), pred_val in zip(upcoming_df.iterrows(), raw_preds):
                        u_seq = int(u_row["stop_sequence"])
                        u_cap = int(u_row["bus_capacity"])
                        clamped = max(0, min(u_cap, int(round(float(pred_val)))))
                        preds_by_seq[u_seq] = clamped
                    prediction_available = True
            except Exception:
                prediction_available = False

        upcoming = []
        for idx, (_, row) in enumerate(upcoming_df.iterrows()):
            u_seq = int(row["stop_sequence"])
            cap = int(row["bus_capacity"])
            pred_occ = preds_by_seq.get(u_seq)
            has_pred = pred_occ is not None
            occ_for_metrics = pred_occ if has_pred else 0
            avail_seats = max(0, cap - occ_for_metrics) if has_pred else 0
            pct = round((occ_for_metrics / cap) * 100.0, 1) if (has_pred and cap > 0) else 0.0
            upcoming.append({
                "stop_id": str(row["stop_id"]),
                "stop_name": str(row["stop_name"]),
                "stop_sequence": u_seq,
                "expected_boarding": int(row["boarding"]),
                "expected_alighting": int(row["alighting"]),
                "expected_occupancy": pred_occ if has_pred else 0,
                "available_seats": avail_seats,
                "bus_capacity": cap,
                "occupancy_pct": pct,
                "crowd_status": crowd_label(occ_for_metrics, cap) if has_pred else "Unavailable",
                "expected_time": str(row["timestamp"]),
                "is_next_stop": idx == 0,
                "prediction_available": has_pred,
                "prediction_source": "RANDOM_FOREST_ML" if has_pred else "UNAVAILABLE",
            })

        # Less crowded alternatives serving the same corridor
        alternatives = []
        for other_id, osnap in self._bus_snapshots.items():
            if other_id != bus_id and osnap["route_id"] == snap["route_id"]:
                alternatives.append({
                    "bus_id": other_id,
                    "route_id": osnap["route_id"],
                    "current_stop": osnap["stop_name"],
                    "current_occupancy": osnap["current_occupancy"],
                    "bus_capacity": osnap["bus_capacity"],
                    "occupancy_pct": osnap["occupancy_pct"],
                    "crowd_status": crowd_label(osnap["current_occupancy"], osnap["bus_capacity"]),
                })
        alternatives.sort(key=lambda x: x["occupancy_pct"])

        return {
            "bus_id": bus_id,
            "trip_id": t_id,
            "route_id": snap["route_id"],
            "current_stop_id": cur_stop_id,
            "current_stop_name": cur_name,
            "current_stop_sequence": c_seq,
            "current_occupancy": cur_occ,
            "bus_capacity": cur_cap,
            "available_seats": max(0, cur_cap - cur_occ),
            "occupancy_pct": round((cur_occ / cur_cap) * 100.0, 1) if cur_cap > 0 else 0.0,
            "crowd_status": crowd_label(cur_occ, cur_cap),
            "current_occupancy_source": "DATASET_SIMULATED",
            "expected_occupancy_source": "RANDOM_FOREST_ML",
            "actual_occupancy_available": False,
            "predictions_available": prediction_available and len(upcoming) > 0,
            "prediction_model": "RandomForestRegressor",
            "data_provenance": "DATASET_SIMULATED_CURRENT_AND_RF_ML_PREDICTION",
            "upcoming_stops": upcoming,
            "less_crowded_alternatives": alternatives[:3],
        }
