"""
Indexed Dataset Query Service for MoveSync
Reads data/bus_occupancy.csv (186,000 records, 3,720 trips, 20 buses, 50 stops)
in read-only mode to power stop search, journey planning, saved trips,
and actual bus-wise upcoming stops with boarding/alighting/occupancy projections.
"""

import os
from typing import List, Dict, Any, Optional
import pandas as pd


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
            self._bus_snapshots[str(bus_id)] = {
                "bus_id": str(bus_id),
                "trip_id": int(row["trip_id"]),
                "route_id": str(row["route_id"]),
                "stop_id": str(row["stop_id"]),
                "stop_name": str(row["stop_name"]) if "stop_name" in row else str(row["stop_id"]),
                "stop_sequence": int(row["stop_sequence"]) if "stop_sequence" in row else 1,
                "current_occupancy": occ,
                "bus_capacity": cap,
                "occupancy_pct": round((occ / cap) * 100.0, 1) if cap > 0 else 0.0,
                "boarding": int(row["boarding"]),
                "alighting": int(row["alighting"]),
                "timestamp": str(row["timestamp"]),
                "data_provenance": "SYNTHETIC_DATASET_SNAPSHOT",
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
        # Keep latest trip per bus_id so each serving bus shows a clean, real trip option
        merged = merged.sort_values("trip_id", ascending=False).drop_duplicates(subset=["bus_id"]).head(limit)

        journeys = []
        for _, r in merged.iterrows():
            occ = int(r["current_occupancy_src"])
            cap = int(r["bus_capacity"])
            pct = round((occ / cap) * 100.0, 1) if cap > 0 else 0.0
            journeys.append({
                "bus_id": str(r["bus_id"]),
                "trip_id": int(r["trip_id"]),
                "route_id": str(r["route_id"]),
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
                "occupancy_pct": pct,
                "crowd_status": crowd_label(occ, cap),
                "intermediate_stops": intermediate,
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
        limit: int = 12,
    ) -> Dict[str, Any]:
        if self._df is None or self._df.empty:
            return {"bus_id": bus_id, "upcoming_stops": [], "less_crowded_alternatives": []}

        snap = self._bus_snapshots.get(bus_id)
        if not snap:
            return {"bus_id": bus_id, "upcoming_stops": [], "less_crowded_alternatives": []}

        t_id = trip_id if trip_id is not None else snap["trip_id"]
        c_seq = current_stop_seq if current_stop_seq is not None else snap["stop_sequence"]

        trip_df = self._df[(self._df["bus_id"] == bus_id) & (self._df["trip_id"] == t_id)].sort_values("stop_sequence")
        cur_row = trip_df[trip_df["stop_sequence"] == c_seq]
        cur_occ = int(cur_row.iloc[0]["current_occupancy"]) if not cur_row.empty else snap["current_occupancy"]
        cur_cap = int(cur_row.iloc[0]["bus_capacity"]) if not cur_row.empty else snap["bus_capacity"]
        cur_name = str(cur_row.iloc[0]["stop_name"]) if not cur_row.empty else snap["stop_name"]

        upcoming_df = trip_df[trip_df["stop_sequence"] > c_seq].head(limit)
        upcoming = []
        for idx, (_, row) in enumerate(upcoming_df.iterrows()):
            occ = int(row["current_occupancy"])
            cap = int(row["bus_capacity"])
            upcoming.append({
                "stop_id": str(row["stop_id"]),
                "stop_name": str(row["stop_name"]),
                "stop_sequence": int(row["stop_sequence"]),
                "expected_boarding": int(row["boarding"]),
                "expected_alighting": int(row["alighting"]),
                "expected_occupancy": occ,
                "bus_capacity": cap,
                "occupancy_pct": round((occ / cap) * 100.0, 1) if cap > 0 else 0.0,
                "crowd_status": crowd_label(occ, cap),
                "expected_time": str(row["timestamp"]),
                "is_next_stop": idx == 0,
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
            "current_stop_id": snap["stop_id"],
            "current_stop_name": cur_name,
            "current_stop_sequence": c_seq,
            "current_occupancy": cur_occ,
            "bus_capacity": cur_cap,
            "occupancy_pct": round((cur_occ / cur_cap) * 100.0, 1) if cur_cap > 0 else 0.0,
            "crowd_status": crowd_label(cur_occ, cur_cap),
            "data_provenance": "SYNTHETIC_DATASET_TRIP_PROJECTION",
            "upcoming_stops": upcoming,
            "less_crowded_alternatives": alternatives[:3],
        }
