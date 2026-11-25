"""
gps_tracking.py
===============
Module 3 — Live Bus Tracking & GPS Monitoring
Smart Public Transport Occupancy and Fleet Monitoring System
------------------------------------------------------------
DATA SOURCE : data/route_coordinates.csv   (route geography)
              Simulated GPS positions      (NOT real hardware data)
DEPENDS ON  : occupancy_monitor.py         (bus/route metadata)
VERSION     : 1.0.0

MODULE DESIGN — Future Integration Points
-------------------------------------------
  [SLOT GPS-HW]  Hardware GPS module  → replace simulate_gps_positions()
  [SLOT GPS-FB]  Firebase RTDB        → push live GPS readings to cloud
  [SLOT GPS-WS]  WebSocket feed       → stream positions to web clients
  [SLOT GPS-GF]  Geofence engine      → trigger alerts on boundary crossings

GPS TRACKING STATUS
--------------------
  RECENT      : GPS update within the last 2 minutes   → 🟢 Green
  DELAYED     : GPS update 2 – 5 minutes ago           → 🟠 Orange
  STALE       : GPS update older than 5 minutes         → 🔴 Red
  SIGNAL LOST : No GPS coordinates available            → ⚫ Grey
"""

from __future__ import annotations

import os
import math
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS & CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ROUTE_COORDS_PATH = os.path.join(DATA_DIR, "route_coordinates.csv")

# GPS freshness thresholds (seconds)
GPS_FRESH_LIMIT   = 120   # <= 2 min  → Recent
GPS_DELAYED_LIMIT = 300   # <= 5 min  → Delayed
                           # > 5 min   → Stale

GPS_STATUS_RECENT  = "Recent"
GPS_STATUS_DELAYED = "Delayed"
GPS_STATUS_STALE   = "Stale"
GPS_STATUS_LOST    = "Signal Lost"

ALL_GPS_STATUSES = [GPS_STATUS_RECENT, GPS_STATUS_DELAYED,
                    GPS_STATUS_STALE, GPS_STATUS_LOST]

GPS_STATUS_COLORS = {
    GPS_STATUS_RECENT:  "#27ae60",   # green
    GPS_STATUS_DELAYED: "#f39c12",   # orange
    GPS_STATUS_STALE:   "#e74c3c",   # red
    GPS_STATUS_LOST:    "#95a5a6",   # grey
}

GPS_STATUS_EMOJI = {
    GPS_STATUS_RECENT:  "🟢",
    GPS_STATUS_DELAYED: "🟠",
    GPS_STATUS_STALE:   "🔴",
    GPS_STATUS_LOST:    "⚫",
}

# Source tags
SOURCE_SIMULATED = "Simulated GPS"
SOURCE_HARDWARE  = "Hardware GPS"       # [SLOT GPS-HW]

# Bangalore bounding box (for validation)
BANGALORE_LAT_RANGE = (12.75, 13.15)
BANGALORE_LON_RANGE = (77.40, 77.85)

# Route line colours for the map
ROUTE_COLORS = {
    "R101": "#1565c0",   # blue
    "R205": "#6a1b9a",   # purple
    "R330": "#00838f",   # teal
    "R047": "#e65100",   # deep orange
}

# Primary route assignment for each bus (mode route from occupancy data).
# In a live system this would come from a dispatch/scheduling database.
BUS_ROUTE_ASSIGNMENTS: dict[str, str] = {
    "KA-BUS-001": "R205",  "KA-BUS-002": "R047",
    "KA-BUS-003": "R101",  "KA-BUS-004": "R101",
    "KA-BUS-005": "R047",  "KA-BUS-006": "R205",
    "KA-BUS-007": "R047",  "KA-BUS-008": "R047",
    "KA-BUS-009": "R047",  "KA-BUS-010": "R047",
    "KA-BUS-011": "R205",  "KA-BUS-012": "R101",
    "KA-BUS-013": "R330",  "KA-BUS-014": "R047",
    "KA-BUS-015": "R047",  "KA-BUS-016": "R330",
    "KA-BUS-017": "R101",  "KA-BUS-018": "R205",
    "KA-BUS-019": "R330",  "KA-BUS-020": "R101",
}

# Buses that will be simulated as stale / delayed / signal-lost
# to demonstrate GPS status classification in the demo.
_SIM_DELAYED_BUSES = {"KA-BUS-004", "KA-BUS-019"}
_SIM_STALE_BUSES   = {"KA-BUS-008", "KA-BUS-016"}
_SIM_LOST_BUSES    = {"KA-BUS-012"}


# ──────────────────────────────────────────────────────────────────────────────
# GPS READING DATACLASS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class GPSReading:
    """
    One GPS position reading for a single bus.

    Fields
    ------
    bus_id        : unique bus identifier
    route_id      : route currently being served
    latitude      : WGS-84 latitude  (None if signal lost)
    longitude     : WGS-84 longitude (None if signal lost)
    speed_kmh     : ground speed in km/h
    heading_deg   : compass heading 0-360 (0 = North)
    timestamp     : when this reading was captured
    gps_status    : Recent / Delayed / Stale / Signal Lost
    nearest_stop  : closest stop ID on the route
    source        : "Simulated GPS" or "Hardware GPS"
    """
    bus_id       : str
    route_id     : str
    latitude     : Optional[float]
    longitude    : Optional[float]
    speed_kmh    : float
    heading_deg  : float
    timestamp    : datetime
    gps_status   : str
    nearest_stop : str
    source       : str = SOURCE_SIMULATED

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = str(self.timestamp)
        return d


# ──────────────────────────────────────────────────────────────────────────────
# 1.  ROUTE COORDINATE LOADING
# ──────────────────────────────────────────────────────────────────────────────

def load_route_coordinates(path: str = ROUTE_COORDS_PATH) -> pd.DataFrame:
    """
    Load and validate route_coordinates.csv.

    Returns a DataFrame with columns:
      route_id, stop_id, stop_name, latitude, longitude, stop_order
    sorted by (route_id, stop_order).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Route coordinates file not found at '{path}'.\n"
            "Please ensure 'route_coordinates.csv' is inside the 'data/' folder."
        )

    df = pd.read_csv(path)

    required = {"route_id", "stop_id", "stop_name", "latitude", "longitude", "stop_order"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"route_coordinates.csv missing columns: {missing}")

    # Validate coordinate ranges
    bad_lat = ~df["latitude"].between(*BANGALORE_LAT_RANGE)
    bad_lon = ~df["longitude"].between(*BANGALORE_LON_RANGE)
    if bad_lat.any() or bad_lon.any():
        raise ValueError(
            f"{(bad_lat | bad_lon).sum()} waypoints have coordinates outside "
            f"the expected Bangalore bounds."
        )

    return df.sort_values(["route_id", "stop_order"]).reset_index(drop=True)


def get_route_waypoints(route_coords: pd.DataFrame) -> dict[str, list[tuple[float, float, str]]]:
    """
    Convert the route coordinates DataFrame into a dict:
      { route_id: [(lat, lon, stop_id), ...] }
    ordered by stop_order.
    """
    waypoints: dict[str, list[tuple[float, float, str]]] = {}
    for route_id, grp in route_coords.groupby("route_id"):
        grp = grp.sort_values("stop_order")
        waypoints[route_id] = [
            (row.latitude, row.longitude, row.stop_id)
            for row in grp.itertuples()
        ]
    return waypoints


# ──────────────────────────────────────────────────────────────────────────────
# 2.  GPS STATUS CLASSIFICATION
# ──────────────────────────────────────────────────────────────────────────────

def classify_gps_status(
    reading_time: datetime,
    reference_time: datetime | None = None,
) -> str:
    """
    Classify a GPS reading timestamp into a freshness status.

    Parameters
    ----------
    reading_time   : when the GPS reading was captured
    reference_time : "now" — defaults to datetime.now() if None

    Returns
    -------
    str : one of GPS_STATUS_RECENT, GPS_STATUS_DELAYED, GPS_STATUS_STALE
    """
    if reference_time is None:
        reference_time = datetime.now()

    age_seconds = (reference_time - reading_time).total_seconds()

    if age_seconds <= GPS_FRESH_LIMIT:
        return GPS_STATUS_RECENT
    elif age_seconds <= GPS_DELAYED_LIMIT:
        return GPS_STATUS_DELAYED
    else:
        return GPS_STATUS_STALE


# ──────────────────────────────────────────────────────────────────────────────
# 3.  POSITION INTERPOLATION HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute compass bearing (0-360°) from point 1 to point 2."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    d_lon = lon2 - lon1
    x = math.sin(d_lon) * math.cos(lat2)
    y = (math.cos(lat1) * math.sin(lat2) -
         math.sin(lat1) * math.cos(lat2) * math.cos(d_lon))
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def _interpolate_along_route(
    waypoints: list[tuple[float, float, str]],
    progress: float,
) -> tuple[float, float, float, str]:
    """
    Given a list of route waypoints and a progress value (0.0 → 1.0),
    return (latitude, longitude, heading_deg, nearest_stop_id).

    progress=0.0 → first stop, progress=1.0 → last stop.
    The bus position is linearly interpolated between adjacent stops.
    """
    n = len(waypoints)
    if n < 2:
        lat, lon, sid = waypoints[0]
        return lat, lon, 0.0, sid

    # Clamp progress
    progress = max(0.0, min(1.0, progress))

    # Which segment are we on?
    total_segments = n - 1
    exact_segment = progress * total_segments
    seg_idx = min(int(exact_segment), total_segments - 1)
    seg_frac = exact_segment - seg_idx

    lat1, lon1, sid1 = waypoints[seg_idx]
    lat2, lon2, sid2 = waypoints[min(seg_idx + 1, n - 1)]

    # Linear interpolation
    lat = lat1 + (lat2 - lat1) * seg_frac
    lon = lon1 + (lon2 - lon1) * seg_frac

    # Heading
    hdg = _bearing(lat1, lon1, lat2, lon2) if (lat1 != lat2 or lon1 != lon2) else 0.0

    # Nearest stop
    nearest = sid1 if seg_frac < 0.5 else sid2

    return round(lat, 6), round(lon, 6), round(hdg, 1), nearest


# ──────────────────────────────────────────────────────────────────────────────
# 4.  GPS SIMULATION ENGINE
# ──────────────────────────────────────────────────────────────────────────────

def simulate_gps_positions(
    reference_time: datetime | None = None,
    route_coords: pd.DataFrame | None = None,
    include_anomalies: bool = True,
) -> list[GPSReading]:
    """
    Generate simulated GPS positions for all 20 buses.

    SIMULATION — NOT REAL HARDWARE DATA.

    Each bus is placed at a deterministic position along its assigned route.
    The position changes over time (every ~2 minutes) to simulate movement.

    Parameters
    ----------
    reference_time    : treat this as "now" (default: datetime.now())
    route_coords      : pre-loaded route coordinates DataFrame (auto-loads if None)
    include_anomalies : if True, some buses will be delayed/stale/lost for demo

    Returns
    -------
    list[GPSReading] for all 20 buses, sorted by bus_id
    """
    if reference_time is None:
        reference_time = datetime.now()

    if route_coords is None:
        route_coords = load_route_coordinates()

    waypoints = get_route_waypoints(route_coords)
    readings: list[GPSReading] = []

    # Time seed: changes every 2 minutes for smooth simulated movement
    time_seed = int(reference_time.timestamp()) // 120

    for bus_id in sorted(BUS_ROUTE_ASSIGNMENTS.keys()):
        route_id = BUS_ROUTE_ASSIGNMENTS[bus_id]
        rw = waypoints.get(route_id)
        if not rw:
            continue

        # Deterministic but varying progress per bus
        bus_hash = int(hashlib.md5(bus_id.encode()).hexdigest()[:8], 16)
        raw_progress = ((bus_hash + time_seed * 7) % 1000) / 1000.0

        # Simulate speed (20-50 km/h) based on bus hash
        speed = 20.0 + (bus_hash % 31)

        # ── Handle anomaly buses ──────────────────────────────────────────
        if include_anomalies and bus_id in _SIM_LOST_BUSES:
            # Signal Lost — no coordinates
            readings.append(GPSReading(
                bus_id       = bus_id,
                route_id     = route_id,
                latitude     = None,
                longitude    = None,
                speed_kmh    = 0.0,
                heading_deg  = 0.0,
                timestamp    = reference_time - timedelta(minutes=12),
                gps_status   = GPS_STATUS_LOST,
                nearest_stop = "Unknown",
                source       = SOURCE_SIMULATED,
            ))
            continue

        # Interpolate position along route
        lat, lon, heading, nearest_stop = _interpolate_along_route(rw, raw_progress)

        # Small random jitter (±0.0003° ≈ ±33 m) for realism
        np.random.seed((bus_hash + time_seed) % (2**32 - 1))
        lat += np.random.uniform(-0.0003, 0.0003)
        lon += np.random.uniform(-0.0003, 0.0003)
        lat = round(lat, 6)
        lon = round(lon, 6)

        # Determine timestamp offset for this bus
        if include_anomalies and bus_id in _SIM_DELAYED_BUSES:
            ts_offset = timedelta(seconds=150 + (bus_hash % 120))   # 2.5 – 4.5 min ago
        elif include_anomalies and bus_id in _SIM_STALE_BUSES:
            ts_offset = timedelta(seconds=360 + (bus_hash % 240))   # 6 – 10 min ago
        else:
            ts_offset = timedelta(seconds=bus_hash % 60)            # 0 – 59 sec ago

        reading_time = reference_time - ts_offset
        gps_status = classify_gps_status(reading_time, reference_time)

        readings.append(GPSReading(
            bus_id       = bus_id,
            route_id     = route_id,
            latitude     = lat,
            longitude    = lon,
            speed_kmh    = round(speed + np.random.uniform(-5, 5), 1),
            heading_deg  = round(heading, 1),
            timestamp    = reading_time,
            gps_status   = gps_status,
            nearest_stop = nearest_stop,
            source       = SOURCE_SIMULATED,
        ))

    readings.sort(key=lambda r: r.bus_id)
    return readings


# ──────────────────────────────────────────────────────────────────────────────
# 5.  FILTERING & UTILITIES
# ──────────────────────────────────────────────────────────────────────────────

def filter_gps_readings(
    readings: list[GPSReading],
    bus_ids:   list[str] | None = None,
    route_ids: list[str] | None = None,
    statuses:  list[str] | None = None,
) -> list[GPSReading]:
    """Filter GPS readings by bus, route, or status.  None = no filter."""
    result = readings
    if bus_ids:
        result = [r for r in result if r.bus_id in bus_ids]
    if route_ids:
        result = [r for r in result if r.route_id in route_ids]
    if statuses:
        result = [r for r in result if r.gps_status in statuses]
    return result


def readings_to_dataframe(readings: list[GPSReading]) -> pd.DataFrame:
    """Convert a list of GPSReading objects to a tidy DataFrame."""
    if not readings:
        return pd.DataFrame(columns=[
            "bus_id", "route_id", "latitude", "longitude",
            "speed_kmh", "heading_deg", "timestamp",
            "gps_status", "nearest_stop", "source",
        ])
    rows = [r.to_dict() for r in readings]
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def get_gps_summary(readings: list[GPSReading]) -> dict:
    """Return aggregate statistics for the current GPS snapshot."""
    total = len(readings)
    by_status = {}
    for s in ALL_GPS_STATUSES:
        by_status[s] = sum(1 for r in readings if r.gps_status == s)

    routes_active = sorted({r.route_id for r in readings})
    avg_speed_vals = [r.speed_kmh for r in readings if r.speed_kmh > 0 and r.latitude is not None]
    avg_speed = round(sum(avg_speed_vals) / len(avg_speed_vals), 1) if avg_speed_vals else 0.0

    return {
        "total_buses":    total,
        "recent_count":   by_status.get(GPS_STATUS_RECENT, 0),
        "delayed_count":  by_status.get(GPS_STATUS_DELAYED, 0),
        "stale_count":    by_status.get(GPS_STATUS_STALE, 0),
        "lost_count":     by_status.get(GPS_STATUS_LOST, 0),
        "routes_active":  routes_active,
        "avg_speed_kmh":  avg_speed,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 6.  MAP BUILDING  (Plotly Scattermap — no API key required)
# ──────────────────────────────────────────────────────────────────────────────

def build_gps_map(
    readings: list[GPSReading],
    route_coords: pd.DataFrame | None = None,
    show_routes: bool = True,
    show_stops: bool = True,
) -> go.Figure:
    """
    Build an interactive Plotly map showing bus positions and route paths.

    Uses open-street-map tiles (no Mapbox token needed).
    """
    if route_coords is None:
        route_coords = load_route_coordinates()

    fig = go.Figure()

    # ── Route path lines ──────────────────────────────────────────────────
    if show_routes:
        for route_id, grp in route_coords.groupby("route_id"):
            grp = grp.sort_values("stop_order")
            fig.add_trace(go.Scattermap(
                lat=grp["latitude"].tolist(),
                lon=grp["longitude"].tolist(),
                mode="lines",
                line=dict(width=3, color=ROUTE_COLORS.get(route_id, "#888")),
                name=f"Route {route_id}",
                hoverinfo="name",
                showlegend=True,
            ))

    # ── Stop markers ──────────────────────────────────────────────────────
    if show_stops:
        fig.add_trace(go.Scattermap(
            lat=route_coords["latitude"].tolist(),
            lon=route_coords["longitude"].tolist(),
            mode="markers",
            marker=dict(size=7, color="#555555", opacity=0.6),
            name="Stops",
            text=route_coords.apply(
                lambda r: f"{r.stop_id}: {r.stop_name}", axis=1
            ).tolist(),
            hovertemplate="%{text}<extra></extra>",
            showlegend=True,
        ))

    # ── Bus position markers ──────────────────────────────────────────────
    valid_readings = [r for r in readings if r.latitude is not None]
    lost_readings  = [r for r in readings if r.latitude is None]

    if valid_readings:
        fig.add_trace(go.Scattermap(
            lat=[r.latitude for r in valid_readings],
            lon=[r.longitude for r in valid_readings],
            mode="markers+text",
            marker=dict(
                size=16,
                color=[GPS_STATUS_COLORS[r.gps_status] for r in valid_readings],
                symbol="bus",
                allowoverlap=True,
            ),
            text=[r.bus_id.replace("KA-BUS-", "B") for r in valid_readings],
            textposition="top center",
            textfont=dict(size=9, color="#333"),
            name="Buses",
            customdata=[
                [r.bus_id, r.route_id, f"{r.speed_kmh:.0f}",
                 r.gps_status, r.nearest_stop,
                 str(r.timestamp)[:19]]
                for r in valid_readings
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Route: %{customdata[1]}<br>"
                "Speed: %{customdata[2]} km/h<br>"
                "Status: %{customdata[3]}<br>"
                "Near: %{customdata[4]}<br>"
                "Updated: %{customdata[5]}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

    # ── Centre the map ────────────────────────────────────────────────────
    all_lats = [r.latitude for r in valid_readings] if valid_readings else [12.97]
    all_lons = [r.longitude for r in valid_readings] if valid_readings else [77.59]
    centre_lat = sum(all_lats) / len(all_lats)
    centre_lon = sum(all_lons) / len(all_lons)

    fig.update_layout(
        map=dict(
            style="open-street-map",
            center=dict(lat=centre_lat, lon=centre_lon),
            zoom=11.3,
        ),
        title=dict(
            text="🛰️ Live Bus Tracking Map  ·  SIMULATED GPS DATA",
            font=dict(size=15),
        ),
        height=560,
        margin=dict(l=0, r=0, t=45, b=0),
        legend=dict(
            orientation="h", yanchor="top", y=0.99,
            xanchor="left", x=0.01,
            bgcolor="rgba(255,255,255,0.8)",
            font=dict(size=10),
        ),
    )

    # ── Annotation for lost buses ─────────────────────────────────────────
    if lost_readings:
        bus_list = ", ".join(r.bus_id for r in lost_readings)
        fig.add_annotation(
            text=f"⚫ Signal Lost: {bus_list}",
            xref="paper", yref="paper", x=0.99, y=0.02,
            showarrow=False,
            font=dict(size=11, color="#e74c3c"),
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#e74c3c", borderwidth=1, borderpad=5,
            xanchor="right",
        )

    return fig


def build_gps_status_chart(readings: list[GPSReading]) -> go.Figure:
    """Donut chart showing GPS status distribution."""
    counts = {s: 0 for s in ALL_GPS_STATUSES}
    for r in readings:
        counts[r.gps_status] = counts.get(r.gps_status, 0) + 1

    labels = [s for s in ALL_GPS_STATUSES if counts[s] > 0]
    values = [counts[s] for s in labels]
    colors = [GPS_STATUS_COLORS[s] for s in labels]

    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.55,
        marker=dict(colors=colors),
        textinfo="label+value",
        hovertemplate="<b>%{label}</b><br>Buses: %{value}<extra></extra>",
    ))
    fig.update_layout(
        title="📡 GPS Status Distribution",
        template="plotly_white",
        height=320,
        showlegend=True,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# 7.  [SLOT GPS-HW]  HARDWARE GPS INTEGRATION (STUB)
# ──────────────────────────────────────────────────────────────────────────────

def ingest_hardware_gps(
    bus_id: str,
    latitude: float,
    longitude: float,
    speed_kmh: float,
    heading_deg: float,
    gps_module_id: str = "GPS-UNKNOWN",
) -> GPSReading | None:
    """
    FUTURE — Accept a reading from a real GPS hardware module.

    Replace the TODO block below with your GPS SDK / serial parsing code.
    Currently returns None (stub only — hardware not yet connected).

    Parameters
    ----------
    bus_id       : which bus sent this reading
    latitude     : WGS-84 latitude from hardware
    longitude    : WGS-84 longitude from hardware
    speed_kmh    : ground speed from GPS chip
    heading_deg  : course-over-ground from GPS chip
    gps_module_id: identifier for the GPS hardware unit
    """
    # TODO: validate NMEA sentence / UBX packet
    # TODO: check fix quality (HDOP, satellite count)
    # TODO: apply Kalman filter for smoothing
    # return GPSReading(
    #     bus_id=bus_id, route_id=lookup_current_route(bus_id),
    #     latitude=latitude, longitude=longitude,
    #     speed_kmh=speed_kmh, heading_deg=heading_deg,
    #     timestamp=datetime.now(), gps_status=GPS_STATUS_RECENT,
    #     nearest_stop=find_nearest_stop(latitude, longitude),
    #     source=f"{SOURCE_HARDWARE} ({gps_module_id})",
    # )
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 8.  [SLOT GPS-FB]  FIREBASE PUSH (STUB)
# ──────────────────────────────────────────────────────────────────────────────

def push_gps_to_firebase(reading: GPSReading) -> bool:
    """
    FUTURE — Push a GPS reading to Firebase Realtime Database.
    Replace with firebase_admin SDK calls when ready.
    Currently a no-op; returns False.
    """
    # TODO: db.reference(f"/gps/{reading.bus_id}").set(reading.to_dict())
    return False


# ──────────────────────────────────────────────────────────────────────────────
# STANDALONE SELF-TEST  (python gps_tracking.py)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import io

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    print("=" * 64)
    print("  GPS Tracking Module — Self-Test")
    print("  Data source: SIMULATED GPS data (NOT real hardware)")
    print("=" * 64)

    _counts = {"passed": 0, "failed": 0, "total": 0}

    def check(label: str, condition: bool, detail: str = ""):
        _counts["total"] += 1
        if condition:
            _counts["passed"] += 1
            print(f"  [PASS] {label}" + (f"  ({detail})" if detail else ""))
        else:
            _counts["failed"] += 1
            print(f"  [FAIL] {label}" + (f"  ({detail})" if detail else ""))

    # ── TEST 1: Route Coordinates Loading ─────────────────────────────────
    print("\n[TEST 1] Route Coordinates Loading")
    try:
        rc = load_route_coordinates()
        check("File loaded successfully", True, f"{len(rc)} waypoints")
        check("4 routes present", rc["route_id"].nunique() == 4,
              f"found {rc['route_id'].nunique()}")
        check("11 stops per route",
              all(rc.groupby("route_id").size() == 11),
              str(rc.groupby("route_id").size().tolist()))
    except Exception as e:
        check("File loaded", False, str(e))
        rc = pd.DataFrame()

    # ── TEST 2: Valid Latitude & Longitude ────────────────────────────────
    print("\n[TEST 2] Valid Latitude & Longitude")
    if not rc.empty:
        lat_ok = rc["latitude"].between(*BANGALORE_LAT_RANGE).all()
        lon_ok = rc["longitude"].between(*BANGALORE_LON_RANGE).all()
        check("All latitudes in Bangalore range (12.75–13.15°N)", lat_ok,
              f"min={rc['latitude'].min():.4f}, max={rc['latitude'].max():.4f}")
        check("All longitudes in Bangalore range (77.40–77.85°E)", lon_ok,
              f"min={rc['longitude'].min():.4f}, max={rc['longitude'].max():.4f}")
        check("No NaN coordinates",
              not rc[["latitude", "longitude"]].isna().any().any())
    else:
        check("Skipped — no route data", False)

    # ── TEST 3: GPS Position Simulation ───────────────────────────────────
    print("\n[TEST 3] GPS Position Simulation")
    ref_time = datetime(2026, 10, 15, 9, 30, 0)
    readings = simulate_gps_positions(reference_time=ref_time, route_coords=rc)
    check("Generated readings for 20 buses", len(readings) == 20,
          f"got {len(readings)}")

    valid_pos = [r for r in readings if r.latitude is not None]
    lats_ok = all(BANGALORE_LAT_RANGE[0] <= r.latitude <= BANGALORE_LAT_RANGE[1]
                  for r in valid_pos)
    lons_ok = all(BANGALORE_LON_RANGE[0] <= r.longitude <= BANGALORE_LON_RANGE[1]
                  for r in valid_pos)
    check("All position latitudes within valid range", lats_ok)
    check("All position longitudes within valid range", lons_ok)
    check("All speeds non-negative",
          all(r.speed_kmh >= 0 for r in readings))

    # ── TEST 4: Bus-Route Association ─────────────────────────────────────
    print("\n[TEST 4] Bus-Route Association")
    bus_ids_expected = set(BUS_ROUTE_ASSIGNMENTS.keys())
    bus_ids_got = {r.bus_id for r in readings}
    check("All 20 bus IDs present", bus_ids_expected == bus_ids_got)
    route_ids_got = {r.route_id for r in readings}
    check("Routes match expected set",
          route_ids_got == {"R101", "R205", "R330", "R047"},
          str(sorted(route_ids_got)))
    for r in readings:
        expected_route = BUS_ROUTE_ASSIGNMENTS[r.bus_id]
        if r.route_id != expected_route:
            check(f"{r.bus_id} on correct route", False,
                  f"expected {expected_route}, got {r.route_id}")
            break
    else:
        check("All buses on their assigned routes", True)

    # ── TEST 5: GPS Status Classification ─────────────────────────────────
    print("\n[TEST 5] GPS Status Classification")
    summary = get_gps_summary(readings)
    check("Recent status buses detected",
          summary["recent_count"] > 0,
          f"{summary['recent_count']} buses")
    check("Delayed status buses detected",
          summary["delayed_count"] > 0,
          f"{summary['delayed_count']} buses")
    check("Stale status buses detected",
          summary["stale_count"] > 0,
          f"{summary['stale_count']} buses")
    check("Signal Lost buses detected",
          summary["lost_count"] > 0,
          f"{summary['lost_count']} buses")

    # Direct classification tests
    check("classify: 30s ago → Recent",
          classify_gps_status(ref_time - timedelta(seconds=30), ref_time) == GPS_STATUS_RECENT)
    check("classify: 180s ago → Delayed",
          classify_gps_status(ref_time - timedelta(seconds=180), ref_time) == GPS_STATUS_DELAYED)
    check("classify: 600s ago → Stale",
          classify_gps_status(ref_time - timedelta(seconds=600), ref_time) == GPS_STATUS_STALE)

    # ── TEST 6: Missing GPS Data Handling ─────────────────────────────────
    print("\n[TEST 6] Missing GPS Data Handling")
    lost = [r for r in readings if r.gps_status == GPS_STATUS_LOST]
    check("Signal-lost bus has latitude=None",
          all(r.latitude is None for r in lost))
    check("Signal-lost bus has longitude=None",
          all(r.longitude is None for r in lost))
    check("Signal-lost bus still in readings list",
          len(lost) == len(_SIM_LOST_BUSES),
          f"{len(lost)} lost buses")
    check("Signal-lost bus has speed=0",
          all(r.speed_kmh == 0.0 for r in lost))

    # ── TEST 7: Filtering ─────────────────────────────────────────────────
    print("\n[TEST 7] Filtering")
    f_bus = filter_gps_readings(readings, bus_ids=["KA-BUS-001", "KA-BUS-002"])
    check("Filter by bus_id works",
          len(f_bus) == 2 and {r.bus_id for r in f_bus} == {"KA-BUS-001", "KA-BUS-002"})
    f_route = filter_gps_readings(readings, route_ids=["R330"])
    check("Filter by route_id works",
          all(r.route_id == "R330" for r in f_route))
    f_status = filter_gps_readings(readings, statuses=[GPS_STATUS_RECENT])
    check("Filter by status works",
          all(r.gps_status == GPS_STATUS_RECENT for r in f_status))

    # ── TEST 8: Map Data Preparation ──────────────────────────────────────
    print("\n[TEST 8] Map Data Preparation")
    try:
        fig = build_gps_map(readings, route_coords=rc)
        check("Map figure generated", fig is not None)
        check("Map has traces (routes + stops + buses)",
              len(fig.data) >= 3, f"{len(fig.data)} traces")
        check("Map uses open-street-map tiles",
              fig.layout.map.style == "open-street-map")
    except Exception as e:
        check("Map generation", False, str(e))

    # ── TEST 9: DataFrame Conversion ──────────────────────────────────────
    print("\n[TEST 9] DataFrame Conversion")
    df = readings_to_dataframe(readings)
    check("DataFrame has 20 rows", len(df) == 20, f"got {len(df)}")
    expected_cols = {"bus_id", "route_id", "latitude", "longitude",
                     "speed_kmh", "heading_deg", "timestamp",
                     "gps_status", "nearest_stop", "source"}
    check("All expected columns present",
          expected_cols.issubset(set(df.columns)),
          str(sorted(df.columns)))

    # ── TEST 10: Status Chart ─────────────────────────────────────────────
    print("\n[TEST 10] Status Chart")
    try:
        chart = build_gps_status_chart(readings)
        check("Status chart generated", chart is not None)
    except Exception as e:
        check("Status chart", False, str(e))

    # ── SUMMARY ───────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    passed = _counts["passed"]
    failed = _counts["failed"]
    total  = _counts["total"]

    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")

    if failed == 0:
        print("  ✅ ALL TESTS PASSED")
    else:
        print(f"  ❌ {failed} TEST(S) FAILED")

    print()
    print("  GPS Summary:")
    for k, v in summary.items():
        print(f"    {k:<20}: {v}")

    print()
    print("  Bus Positions (sample):")
    print(f"  {'Bus ID':<15} {'Route':<6} {'Lat':>10} {'Lon':>10} "
          f"{'Speed':>6} {'Status':<12} {'Near Stop'}")
    print("  " + "-" * 80)
    for r in readings[:5]:
        lat_s = f"{r.latitude:.4f}" if r.latitude else "   N/A"
        lon_s = f"{r.longitude:.4f}" if r.longitude else "   N/A"
        print(f"  {r.bus_id:<15} {r.route_id:<6} {lat_s:>10} {lon_s:>10} "
              f"{r.speed_kmh:>5.1f} {r.gps_status:<12} {r.nearest_stop}")
    print(f"  ... ({len(readings) - 5} more)")

    print()
    print("=" * 64)
    print("  [OK] Self-test complete.")
    print("       Launch the dashboard with:")
    print("       python -m streamlit run app_occupancy.py")
    print("=" * 64)

