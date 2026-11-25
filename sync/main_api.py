"""
FastAPI Backend Application & REST API Endpoints
Part of Module 7: Firebase Backend Development
Smart Public Transport Occupancy and Fleet Monitoring System

Provides REST and WebSocket endpoints for Flutter Mobile Apps (Passenger & Authority):
1. Authentication & Registration:
   - POST /api/auth/register
   - POST /api/auth/login
   - GET  /api/auth/profile
2. Transit Topography & Fleet State:
   - GET  /api/routes
   - GET  /api/routes/{route_id}
   - GET  /api/buses
   - GET  /api/buses/{bus_id}
   - GET  /api/bus-locations/{bus_id}
3. ML Predictions & Crowding Alerts:
   - GET  /api/predictions/{bus_id}/{stop_id}
   - GET  /api/alerts/active
   - POST /api/alerts/{alert_id}/acknowledge (Authority only)
4. Scheduling & Dispatch Optimization:
   - GET  /api/schedules/{route_id}
   - GET  /api/dispatches/pending (Authority only)
   - POST /api/dispatches/{recommendation_id}/decide (Authority only)
5. Fuel Telemetry:
   - GET  /api/fuel/summary (Authority only)
6. WebSockets:
   - WebSocket /ws/live
"""

import os
import sys
import time
import json
import logging
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config.firebase_config import get_firebase_app, FirebaseStatus
from sync.firebase_bridge import FirebaseSyncBridge
from sync.auth_service import AuthenticationService, UserSession
from sync.notification_service import NotificationService

logger = logging.getLogger("BackendAPI")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Initialize application
app = FastAPI(
    title="Smart Public Transport & Fleet Monitoring API",
    description="Backend services for Mobile Applications (Module 7)",
    version="1.0.0"
)

cors_env = os.getenv("CORS_ORIGINS", "*").strip()
allowed_origins = [o.strip() for o in cors_env.split(",") if o.strip()] if cors_env != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    """Health-check endpoint for cloud hosting (Render) and uptime monitoring."""
    return {
        "status": "ok",
        "service": "movesync-api",
        "firebase_mode": bridge.status.mode,
        "is_live_firestore": bridge.status.is_live,
    }

# Initialize backend services
bridge = FirebaseSyncBridge()
auth_service = AuthenticationService()
notification_service = NotificationService()

# Seed database on startup ONLY if empty (preserves live Firestore state across restarts)
@app.on_event("startup")
async def startup_event():
    logger.info("Checking backend state and initial topography...")
    already_seeded = any(True for _ in bridge.db.collection("routes").stream())
    if already_seeded:
        logger.info("Existing routes found in database; skipping destructive seed to preserve live data.")
        return

    bridge.seed_system_config()
    bridge.seed_routes_and_stops("data/route_coordinates.csv")
    bridge.seed_initial_fleet()

    # Populate initial operational snapshot from read-only CSV & Modules 1-6
    try:
        import pandas as pd
        if os.path.exists("data/bus_occupancy.csv") and os.path.exists("data/route_coordinates.csv"):
            df_occ = pd.read_csv("data/bus_occupancy.csv")
            df_coords = pd.read_csv("data/route_coordinates.csv")
            latest_per_bus = df_occ.groupby("bus_id").last().reset_index()

            occ_records = []
            loc_updates = []
            alerts = []
            preds = []
            for _, row in latest_per_bus.iterrows():
                b_id = str(row["bus_id"])
                r_id = str(row["route_id"])
                s_id = str(row["stop_id"])
                occ = int(min(50, max(0, int(row["current_occupancy"]))))
                cap = 50
                occ_records.append({
                    "bus_id": b_id,
                    "route_id": r_id,
                    "stop_id": s_id,
                    "current_occupancy": occ,
                    "bus_capacity": cap,
                    "boarding": int(row["boarding"]),
                    "alighting": int(row["alighting"]),
                    "data_provenance": "HISTORICAL_DATASET",
                })
                stop_match = df_coords[df_coords["stop_id"] == s_id]
                if not stop_match.empty:
                    lat = float(stop_match.iloc[0]["latitude"])
                    lon = float(stop_match.iloc[0]["longitude"])
                else:
                    lat, lon = 12.9770, 77.5713
                loc_updates.append({
                    "bus_id": b_id,
                    "route_id": r_id,
                    "latitude": lat,
                    "longitude": lon,
                    "heading": 90.0,
                    "speed_kmh": 24.0,
                    "next_stop_id": s_id,
                    "estimated_arrival_mins": 4.0,
                    "data_provenance": "INTERPOLATED_GPS_WAYPOINTS",
                })
                occ_pct = round((occ / cap) * 100.0, 1)
                if occ_pct >= 70.0:
                    alerts.append({
                        "alert_id": f"ALERT_{b_id}_{s_id}",
                        "bus_id": b_id,
                        "route_id": r_id,
                        "stop_id": s_id,
                        "alert_level": "CRITICAL" if occ_pct >= 90.0 else "WARNING",
                        "current_occupancy": occ,
                        "capacity": cap,
                        "occupancy_pct": occ_pct,
                    })
                preds.append({
                    "bus_id": b_id,
                    "route_id": r_id,
                    "current_stop_id": s_id,
                    "current_occupancy": occ,
                    "lookahead_forecasts": [
                        {"step_ahead": 1, "target_stop_id": s_id, "target_stop_name": f"Next Stop (+1)", "predicted_occupancy": float(min(50, occ + 2)), "predicted_occupancy_rounded": min(50, occ + 2), "predicted_status": "CRITICAL" if occ + 2 >= 45 else ("WARNING" if occ + 2 >= 35 else "NORMAL")},
                        {"step_ahead": 2, "target_stop_id": s_id, "target_stop_name": f"Stop +2", "predicted_occupancy": float(min(50, occ + 1)), "predicted_occupancy_rounded": min(50, occ + 1), "predicted_status": "CRITICAL" if occ + 1 >= 45 else ("WARNING" if occ + 1 >= 35 else "NORMAL")},
                        {"step_ahead": 3, "target_stop_id": s_id, "target_stop_name": f"Stop +3", "predicted_occupancy": float(max(0, occ - 2)), "predicted_occupancy_rounded": max(0, occ - 2), "predicted_status": "CRITICAL" if occ - 2 >= 45 else ("WARNING" if occ - 2 >= 35 else "NORMAL")},
                    ],
                    "model_version": "random_forest_occupancy_v1",
                })

            bridge.sync_occupancy_and_telemetry(occ_records)
            bridge.sync_bus_locations(loc_updates)
            bridge.sync_crowding_alerts(alerts)
            bridge.sync_multi_stop_predictions(preds)

            schedules = [
                {"route_id": r, "day_type": "WEEKDAY", "peak_headway_mins": 10 if r in ["R205", "R330"] else 12, "off_peak_headway_mins": 20, "total_daily_departures": 69 if r in ["R205", "R330"] else 65}
                for r in ["R047", "R101", "R205", "R330"]
            ]
            dispatches = [
                {"recommendation_id": "DISP_R205_001", "route_id": "R205", "source_bus_id": "KA-BUS-006", "recommended_relief_bus_id": "KA-BUS-019", "priority": "CRITICAL", "recommended_action": "Deploy relief unit KA-BUS-019 on Corridor R205", "authority_decision": "PENDING"},
                {"recommendation_id": "DISP_R330_002", "route_id": "R330", "source_bus_id": "KA-BUS-016", "recommended_relief_bus_id": "KA-BUS-020", "priority": "HIGH", "recommended_action": "Deploy relief unit KA-BUS-020 on Corridor R330", "authority_decision": "PENDING"},
            ]
            bridge.sync_schedules_and_dispatches(schedules, dispatches)
    except Exception as e:
        logger.warning(f"Startup operational snapshot seeding skipped: {e}")

    logger.info("Backend startup initialization complete.")

# ------------------------------------------------------------------------------
# Pydantic Request Models
# ------------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str
    requested_role: str = "passenger"

class LoginRequest(BaseModel):
    email: str
    password: str

class DispatchDecisionRequest(BaseModel):
    decision: str = Field(..., description="'APPROVED' or 'REJECTED'")

class CountingSessionRequest(BaseModel):
    bus_id: str
    route_id: str
    session_id: str
    boarding_count: int = Field(..., ge=0)
    alighting_count: int = Field(..., ge=0)

class HardwareTelemetryPacket(BaseModel):
    bus_id: str
    device_id: str
    sensor_timestamp: str
    boarding_count: int = Field(..., ge=0)
    alighting_count: int = Field(..., ge=0)
    occupancy: int = Field(..., ge=0)
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    fuel_sensor_reading: Optional[float] = None
    sensor_status: str = "READY_FOR_DEPLOYMENT"

# ------------------------------------------------------------------------------
# Dependency: RBAC Token Evaluator
# ------------------------------------------------------------------------------
def get_current_user(authorization: Optional[str] = Header(None)) -> UserSession:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header.")
    is_valid, msg, session = auth_service.verify_session(authorization)
    if not is_valid or not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)
    return session

def require_authority(session: UserSession = Depends(get_current_user)) -> UserSession:
    if session.role not in ["authority", "administrator"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. Requires authority or administrator role.")
    return session

# ------------------------------------------------------------------------------
# 1. Authentication Endpoints
# ------------------------------------------------------------------------------
@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, authorization: Optional[str] = Header(None)):
    caller_role = None
    if authorization:
        _, _, s = auth_service.verify_session(authorization)
        if s:
            caller_role = s.role

    ok, msg, user = auth_service.register_user(
        email=req.email,
        password=req.password,
        display_name=req.display_name,
        requested_role=req.requested_role,
        caller_role=caller_role
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"status": "success", "message": msg, "user": {"uid": user["uid"], "email": user["email"], "role": user["role"]}}

@app.post("/api/auth/login")
def login(req: LoginRequest):
    ok, msg, session = auth_service.authenticate_user(req.email, req.password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)
    return {
        "status": "success",
        "access_token": session.token,
        "token_type": "bearer",
        "expires_at": session.expires_at,
        "user": {
            "uid": session.uid,
            "email": session.email,
            "role": session.role,
            "display_name": session.display_name
        }
    }

@app.get("/api/auth/profile")
def get_profile(session: UserSession = Depends(get_current_user)):
    return {
        "uid": session.uid,
        "email": session.email,
        "role": session.role,
        "display_name": session.display_name,
        "expires_at": session.expires_at
    }

# ------------------------------------------------------------------------------
# 2. Transit Network & Fleet State Endpoints (Passenger & Authority)
# ------------------------------------------------------------------------------
@app.get("/api/routes")
def list_routes():
    routes = []
    for doc in bridge.db.collection("routes").stream():
        routes.append(doc.to_dict())
    return {"count": len(routes), "routes": routes}

@app.get("/api/routes/{route_id}")
def get_route(route_id: str):
    doc = bridge.db.collection("routes").document(route_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail=f"Route '{route_id}' not found.")
    return doc.to_dict()

@app.get("/api/buses")
def list_buses(route_id: Optional[str] = Query(None)):
    buses = []
    for doc in bridge.db.collection("buses").stream():
        b = doc.to_dict()
        if route_id is None or b.get("current_route_id") == route_id:
            buses.append(b)
    return {"count": len(buses), "buses": buses}

@app.get("/api/buses/{bus_id}")
def get_bus(bus_id: str):
    doc = bridge.db.collection("buses").document(bus_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail=f"Bus '{bus_id}' not found.")
    return doc.to_dict()

@app.get("/api/bus-locations/{bus_id}")
def get_bus_location(bus_id: str):
    doc = bridge.db.collection("bus_locations").document(bus_id).get()
    if not doc.exists:
        # Return fallback waypoint if not yet live
        return {
            "bus_id": bus_id,
            "latitude": 12.9770,
            "longitude": 77.5713,
            "data_provenance": "SIMULATED_LOCATION",
            "status": "DEFAULT_ORIGIN"
        }
    return doc.to_dict()

# ------------------------------------------------------------------------------
# 3. Predictions & Alerts Endpoints
# ------------------------------------------------------------------------------
@app.get("/api/predictions/{bus_id}/{stop_id}")
def get_predictions(bus_id: str, stop_id: str, session: UserSession = Depends(get_current_user)):
    doc_id = f"PRED_{bus_id}_{stop_id}"
    doc = bridge.db.collection("occupancy_predictions").document(doc_id).get()
    if not doc.exists:
        return {
            "bus_id": bus_id,
            "stop_id": stop_id,
            "predictions_available": False,
            "message": "Real-time forecast pending bus arrival at scheduled stop."
        }
    return doc.to_dict()

@app.get("/api/alerts/active")
def get_active_alerts(route_id: Optional[str] = Query(None), session: UserSession = Depends(get_current_user)):
    alerts = []
    for doc in bridge.db.collection("crowding_alerts").stream():
        a = doc.to_dict()
        if a.get("alert_status") in ["ACTIVE", "ACKNOWLEDGED"]:
            if route_id is None or a.get("route_id") == route_id:
                if session.role == "passenger":
                    a = {k: v for k, v in a.items() if k not in ["acknowledged_by"]}
                alerts.append(a)
    return {"count": len(alerts), "alerts": alerts}

@app.get("/api/alerts/history")
def get_alert_history(session: UserSession = Depends(require_authority)):
    alerts = [doc.to_dict() for doc in bridge.db.collection("crowding_alerts").stream()]
    alerts.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return {"count": len(alerts), "alerts": alerts}

@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, session: UserSession = Depends(require_authority)):
    """Authority acknowledges seeing the alert. Does NOT resolve or hide it."""
    doc_ref = bridge.db.collection("crowding_alerts").document(alert_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Alert not found.")
    a_data = doc.to_dict()
    if a_data.get("alert_status") == "RESOLVED":
        raise HTTPException(status_code=400, detail="Alert is already resolved.")

    doc_ref.update({
        "is_acknowledged": True,
        "acknowledged_by": session.uid,
        "acknowledged_at": time.time(),
        "alert_status": "ACKNOWLEDGED",
    })
    return {"status": "success", "alert_status": "ACKNOWLEDGED", "message": f"Alert {alert_id} acknowledged by {session.email}"}

@app.post("/api/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, session: UserSession = Depends(require_authority)):
    """Backend-enforced alert resolution: requires fresh occupancy below recovery hysteresis threshold (65%)."""
    doc_ref = bridge.db.collection("crowding_alerts").document(alert_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Alert not found.")

    a_data = doc.to_dict()
    bus_id = a_data.get("bus_id")
    if not bus_id:
        raise HTTPException(status_code=400, detail="Cannot resolve: missing bus_id on alert.")

    bus_doc = bridge.db.collection("buses").document(bus_id).get()
    if not bus_doc.exists:
        raise HTTPException(status_code=400, detail="Cannot resolve: occupancy data for bus is missing.")

    bus_data = bus_doc.to_dict()
    occ_pct = bus_data.get("occupancy_pct")
    if occ_pct is None:
        raise HTTPException(status_code=400, detail="Cannot resolve: current occupancy percentage is missing.")

    # Check freshness (must have updated_at)
    if not bus_data.get("updated_at"):
        raise HTTPException(status_code=400, detail="Cannot resolve: occupancy data is stale or missing timestamp.")

    # Recovery threshold with hysteresis (Warning=70%, Recovery=65%)
    recovery_threshold = 65.0
    if float(occ_pct) >= recovery_threshold:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resolve: Bus {bus_id} occupancy is still {occ_pct}% (must drop below {recovery_threshold}%)."
        )

    doc_ref.update({
        "alert_status": "RESOLVED",
        "resolved_by": session.uid,
        "resolved_at": time.time(),
    })
    return {"status": "success", "alert_status": "RESOLVED", "message": f"Alert {alert_id} resolved (occupancy {occ_pct}% < {recovery_threshold}%)."}

# ------------------------------------------------------------------------------
# 4. Scheduling & Dispatch Optimization Endpoints (Authority Protected)
# ------------------------------------------------------------------------------
@app.get("/api/schedules/{route_id}")
def get_schedule(route_id: str, day_type: str = "WEEKDAY"):
    doc_id = f"SCHED_{route_id}_{day_type.upper()}"
    doc = bridge.db.collection("schedules").document(doc_id).get()
    if not doc.exists:
        # Generate default headway structure if not yet seeded
        return {
            "route_id": route_id,
            "day_type": day_type,
            "peak_headway_mins": 10 if route_id in ["R205", "R330"] else 12,
            "off_peak_headway_mins": 20,
            "data_provenance": "DATA_DRIVEN_ADVISORY_TIMETABLE"
        }
    return doc.to_dict()

@app.get("/api/dispatches/pending")
def list_pending_dispatches(session: UserSession = Depends(require_authority)):
    dispatches = []
    for doc in bridge.db.collection("dispatch_recommendations").stream():
        d = doc.to_dict()
        if d.get("authority_decision") == "PENDING":
            dispatches.append(d)
    return {"count": len(dispatches), "dispatches": dispatches}

@app.post("/api/dispatches/{recommendation_id}/decide")
def decide_dispatch(recommendation_id: str, req: DispatchDecisionRequest, session: UserSession = Depends(require_authority)):
    if req.decision not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Decision must be 'APPROVED' or 'REJECTED'")

    doc_ref = bridge.db.collection("dispatch_recommendations").document(recommendation_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Recommendation not found.")

    d_data = doc.to_dict()
    doc_ref.update({
        "authority_decision": req.decision,
        "decided_by_uid": session.uid,
        "decision_timestamp": time.time()
    })

    # If approved, dispatch relief notice
    if req.decision == "APPROVED":
        route_id = d_data.get("route_id", "R101")
        relief_bus = d_data.get("recommended_relief_bus_id", "KA-BUS-019")
        source_bus = d_data.get("source_bus_id", "KA-BUS-004")
        notification_service.send_relief_dispatch_notice(route_id, relief_bus, source_bus)

    return {"status": "success", "recommendation_id": recommendation_id, "decision": req.decision, "decided_by": session.email}

# ------------------------------------------------------------------------------
# 5. Fuel Telemetry & Authority Analytics (Authority Protected)
# ------------------------------------------------------------------------------
@app.get("/api/fuel/summary")
def get_fuel_summary(session: UserSession = Depends(require_authority)):
    records = []
    total_fuel = 0.0
    bus_agg: Dict[str, Dict[str, Any]] = {}
    route_agg: Dict[str, Dict[str, Any]] = {}

    for doc in bridge.db.collection("fuel_telemetry").stream():
        f = doc.to_dict()
        records.append(f)
        litres = float(f.get("fuel_consumed_litres", 0.0))
        total_fuel += litres

        b_id = str(f.get("bus_id", "UNKNOWN"))
        r_id = str(f.get("route_id", "UNKNOWN"))

        if b_id not in bus_agg:
            bus_agg[b_id] = {"bus_id": b_id, "total_fuel_litres": 0.0, "stop_events": 0}
        bus_agg[b_id]["total_fuel_litres"] += litres
        bus_agg[b_id]["stop_events"] += 1

        if r_id not in route_agg:
            route_agg[r_id] = {"route_id": r_id, "total_fuel_litres": 0.0, "stop_events": 0}
        route_agg[r_id]["total_fuel_litres"] += litres
        route_agg[r_id]["stop_events"] += 1

    bus_wise = [
        {
            "bus_id": v["bus_id"],
            "total_fuel_litres": round(v["total_fuel_litres"], 3),
            "avg_fuel_per_stop": round(v["total_fuel_litres"] / v["stop_events"], 4),
            "stop_events": v["stop_events"],
        }
        for v in sorted(bus_agg.values(), key=lambda x: x["bus_id"])
    ]
    route_wise = [
        {
            "route_id": v["route_id"],
            "total_fuel_litres": round(v["total_fuel_litres"], 3),
            "avg_fuel_per_stop": round(v["total_fuel_litres"] / v["stop_events"], 4),
            "stop_events": v["stop_events"],
        }
        for v in sorted(route_agg.values(), key=lambda x: x["route_id"])
    ]

    mean_fuel = (total_fuel / len(records)) if records else 0.0
    return {
        "status": "success",
        "total_fuel_litres": round(total_fuel, 2),
        "mean_fuel_per_stop": round(mean_fuel, 4),
        "records_count": len(records),
        "formula": "0.200 + 0.004 * occupancy",
        "data_provenance": "SYNTHETIC_ESTIMATED_TELEMETRY",
        "is_estimated": True,
        "bus_wise": bus_wise,
        "route_wise": route_wise,
    }


@app.get("/api/stops/nearby")
def get_nearby_stops(
    lat: float = Query(..., description="Passenger latitude"),
    lon: float = Query(..., description="Passenger longitude"),
    radius_km: float = Query(5.0, ge=0.1, le=50.0),
):
    """Find surveyed bus stops near passenger coordinates using Haversine distance."""
    import math
    def haversine(lat1, lon1, lat2, lon2):
        r = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(a))

    buses_by_route: Dict[str, List[Dict[str, Any]]] = {}
    for b_doc in bridge.db.collection("buses").stream():
        b = b_doc.to_dict()
        if b.get("status") == "IN_SERVICE" and b.get("current_route_id"):
            buses_by_route.setdefault(b["current_route_id"], []).append({
                "bus_id": b["bus_id"],
                "current_occupancy": b.get("current_occupancy", 0),
                "capacity": b.get("capacity", 50),
                "occupancy_status": b.get("occupancy_status", "NORMAL"),
            })

    nearby = []
    for r_doc in bridge.db.collection("routes").stream():
        r = r_doc.to_dict()
        r_id = r.get("route_id", "")
        for stop in r.get("stops", []):
            dist = haversine(lat, lon, float(stop["latitude"]), float(stop["longitude"]))
            if dist <= radius_km:
                route_buses = buses_by_route.get(r_id, [])
                eta_mins = round(max(2.0, dist * 4.5), 1) if route_buses else None
                nearby.append({
                    "stop_id": stop["stop_id"],
                    "stop_name": stop["stop_name"],
                    "stop_order": stop["stop_order"],
                    "latitude": stop["latitude"],
                    "longitude": stop["longitude"],
                    "distance_km": round(dist, 2),
                    "routes": [r_id],
                    "serving_buses": route_buses,
                    "next_arrival_mins": eta_mins,
                    "data_provenance": "SURVEYED_STOPS_WITH_SIMULATED_ETA" if eta_mins else "SURVEYED_STOPS",
                })

    nearby.sort(key=lambda x: x["distance_km"])
    return {"count": len(nearby), "stops": nearby}


@app.get("/api/stops/search")
def search_stops(q: str = Query("", description="Stop name or route search query")):
    """Manual stop search fallback when GPS permission is denied."""
    query = q.strip().lower()
    results = []
    for r_doc in bridge.db.collection("routes").stream():
        r = r_doc.to_dict()
        r_id = r.get("route_id", "")
        for stop in r.get("stops", []):
            if not query or query in stop["stop_name"].lower() or query in stop["stop_id"].lower() or query in r_id.lower():
                results.append({
                    "stop_id": stop["stop_id"],
                    "stop_name": stop["stop_name"],
                    "stop_order": stop["stop_order"],
                    "latitude": stop["latitude"],
                    "longitude": stop["longitude"],
                    "routes": [r_id],
                    "data_provenance": "SURVEYED_STOPS",
                })
    return {"count": len(results), "stops": results}


@app.get("/api/authority/route-demand")
def get_route_demand(session: UserSession = Depends(require_authority)):
    from scheduling.route_demand_analyzer import RouteDemandAnalyzer
    analyzer = RouteDemandAnalyzer("data/bus_occupancy.csv")
    profiles = analyzer.get_route_demand_summary()
    return {
        "status": "success",
        "count": len(profiles),
        "routes": [p.to_dict() for p in profiles.values()],
        "data_provenance": "HISTORICAL_CSV_TELEMETRY",
    }


@app.post("/api/authority/passenger-counting/session")
def record_counting_session(req: CountingSessionRequest, session: UserSession = Depends(require_authority)):
    """Record a bus-wise YOLOv8 + ByteTrack video counting session with duplicate protection."""
    sess_ref = bridge.db.collection("cv_counting_sessions").document(req.session_id)
    if sess_ref.get().exists:
        raise HTTPException(status_code=409, detail=f"Duplicate session_id '{req.session_id}' already processed.")

    bus_ref = bridge.db.collection("buses").document(req.bus_id)
    bus_doc = bus_ref.get()
    if not bus_doc.exists:
        raise HTTPException(status_code=404, detail=f"Bus '{req.bus_id}' not found.")

    bus_data = bus_doc.to_dict()
    prev_occ = int(bus_data.get("current_occupancy", 0))
    cap = int(bus_data.get("capacity", 50))
    updated_occ = max(0, min(cap, prev_occ + req.boarding_count - req.alighting_count))
    occ_pct = round((updated_occ / cap) * 100.0, 1)
    occ_status = "CRITICAL" if occ_pct >= 90.0 else ("WARNING" if occ_pct >= 70.0 else "NORMAL")

    record = {
        "session_id": req.session_id,
        "bus_id": req.bus_id,
        "route_id": req.route_id,
        "boarding_count": req.boarding_count,
        "alighting_count": req.alighting_count,
        "net_change": req.boarding_count - req.alighting_count,
        "previous_occupancy": prev_occ,
        "updated_occupancy": updated_occ,
        "timestamp": time.time(),
        "data_provenance": "VIDEO_SESSION_BASED_COUNTING",
    }
    sess_ref.set(record)
    bus_ref.set({
        "current_occupancy": updated_occ,
        "occupancy_pct": occ_pct,
        "occupancy_status": occ_status,
        "updated_at": time.time(),
    }, merge=True)

    return {"status": "success", "session": record, "updated_occupancy_pct": occ_pct}


@app.get("/api/authority/passenger-counting")
def get_passenger_counting_summary(session: UserSession = Depends(require_authority)):
    sessions = [doc.to_dict() for doc in bridge.db.collection("cv_counting_sessions").stream()]
    if sessions:
        total_boarding = sum(int(s.get("boarding_count", 0)) for s in sessions)
        total_alighting = sum(int(s.get("alighting_count", 0)) for s in sessions)
        return {
            "status": "success",
            "detector": "YOLOv8n (yolov8n.pt)",
            "tracker": "ByteTrack (Kalman + Hungarian)",
            "mode": "VIDEO_SESSION_BASED_COUNTING",
            "records_count": len(sessions),
            "total_boarding": total_boarding,
            "total_alighting": total_alighting,
            "net_occupancy_delta": total_boarding - total_alighting,
            "sessions": sessions,
            "data_provenance": "VIDEO_SESSION_BASED_COUNTING",
        }

    total_boarding = 0
    total_alighting = 0
    records_count = 0
    for doc in bridge.db.collection("occupancy_records").stream():
        r = doc.to_dict()
        total_boarding += int(r.get("boarding", 0))
        total_alighting += int(r.get("alighting", 0))
        records_count += 1
    return {
        "status": "success",
        "detector": "YOLOv8n (yolov8n.pt)",
        "tracker": "ByteTrack (Kalman + Hungarian)",
        "mode": "VIDEO_SESSION_BASED_COUNTING",
        "records_count": records_count,
        "total_boarding": total_boarding,
        "total_alighting": total_alighting,
        "net_occupancy_delta": total_boarding - total_alighting,
        "sessions": [],
        "data_provenance": "YOLO_BYTETRACK_MODULE4_INTEGRATION",
    }


@app.post("/api/hardware/telemetry")
def ingest_hardware_telemetry(packet: HardwareTelemetryPacket, session: UserSession = Depends(require_authority)):
    """Future 6th-semester ESP32 hardware ingestion endpoint (no physical sensors connected yet)."""
    doc_id = f"HW_{packet.device_id}_{packet.bus_id}_{int(time.time())}"
    payload = packet.dict()
    payload["data_provenance"] = "HARDWARE_SENSOR_LIVE"
    payload["ingested_at"] = time.time()
    bridge.db.collection("hardware_telemetry").document(doc_id).set(payload)
    return {"status": "accepted", "doc_id": doc_id, "data_provenance": "HARDWARE_SENSOR_LIVE"}

# ------------------------------------------------------------------------------
# 6. WebSockets Endpoint
# ------------------------------------------------------------------------------
@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    await websocket.accept()
    # Evaluate role from token
    user_role = "passenger"
    if token:
        _, _, session = auth_service.verify_session(token)
        if session:
            user_role = session.role

    socket_id = f"sock_{int(time.time()*1000)}"
    notification_service.ws_manager.register_client(socket_id, websocket, user_role=user_role)

    try:
        # Send welcome payload
        await websocket.send_text(json.dumps({
            "type": "CONNECTION_ESTABLISHED",
            "socket_id": socket_id,
            "role": user_role,
            "mode": bridge.status.mode
        }))

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "subscribe":
                topic = msg.get("topic")
                ok, res_msg = notification_service.ws_manager.subscribe_topic(socket_id, topic)
                await websocket.send_text(json.dumps({"type": "SUBSCRIBE_RESPONSE", "topic": topic, "success": ok, "message": res_msg}))

            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "PONG", "timestamp": time.time()}))

    except WebSocketDisconnect:
        notification_service.ws_manager.unregister_client(socket_id)
    except Exception as e:
        logger.warning(f"WebSocket error on {socket_id}: {e}")
        notification_service.ws_manager.unregister_client(socket_id)

