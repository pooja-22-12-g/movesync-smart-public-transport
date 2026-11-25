"""
overcrowding_alerts.py
======================
Module 2 — Overcrowding Alert System
Smart Public Transport & Emission Monitoring System
----------------------------------------------------
DATA SOURCE : data/bus_occupancy.csv  (historical dataset — NOT live alerts)
DEPENDS ON  : occupancy_monitor.py   (Module 1)
VERSION     : 1.0.0

DESIGN — Future Integration Points
------------------------------------
  [SLOT IR]     IR Sensor     → call trigger_sensor_alert() when pulse count spikes
  [SLOT CAM]    Camera count  → call trigger_camera_alert() when CV model fires
  [SLOT FB]     Firebase      → call push_alert_to_firebase() to cloud-sync alerts
  [SLOT GPS]    GPS module    → attach lat/lon to each Alert when available
  [SLOT NOTIF]  Notification  → call dispatch_notification() for SMS / push alerts

ALERT SEVERITY LEVELS
----------------------
  NORMAL   : occupancy_pct < 85%
  WARNING  : 85% <= occupancy_pct < 100%
  CRITICAL : occupancy_pct >= 100%

DEDUPLICATION RULE
-------------------
  Within the same (trip_id, bus_id), an alert is only raised when the severity
  CHANGES compared to the previous stop. This prevents flooding the alert log
  with dozens of identical entries for the same overcrowded bus on one trip.
  The first stop of each trip always generates one entry (baseline).
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from occupancy_monitor import load_data, compute_occupancy_pct

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS & CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

# Thresholds — change these numbers to reconfigure the entire alert system
THRESHOLD_WARNING  : float = 85.0   # >= this → WARNING
THRESHOLD_CRITICAL : float = 100.0  # >= this → CRITICAL

SEVERITY_NORMAL   = "Normal"
SEVERITY_WARNING  = "Warning"
SEVERITY_CRITICAL = "Critical"

ALL_SEVERITIES = [SEVERITY_NORMAL, SEVERITY_WARNING, SEVERITY_CRITICAL]

# Display colours per severity
ALERT_COLORS = {
    SEVERITY_NORMAL:   "#27ae60",   # green
    SEVERITY_WARNING:  "#f39c12",   # amber
    SEVERITY_CRITICAL: "#e74c3c",   # red
}

ALERT_BG_COLORS = {
    SEVERITY_NORMAL:   "#d4edda",
    SEVERITY_WARNING:  "#fff3cd",
    SEVERITY_CRITICAL: "#f8d7da",
}

ALERT_TEXT_COLORS = {
    SEVERITY_NORMAL:   "#155724",
    SEVERITY_WARNING:  "#856404",
    SEVERITY_CRITICAL: "#721c24",
}

ALERT_EMOJI = {
    SEVERITY_NORMAL:   "🟢",
    SEVERITY_WARNING:  "🟡",
    SEVERITY_CRITICAL: "🔴",
}

ALERT_ICONS = {
    SEVERITY_NORMAL:   "✅",
    SEVERITY_WARNING:  "⚠️",
    SEVERITY_CRITICAL: "🚨",
}

# Source tags
SOURCE_HISTORICAL = "Historical Dataset"
SOURCE_IR_SENSOR  = "IR Sensor"          # [SLOT IR]
SOURCE_CAMERA     = "Camera"             # [SLOT CAM]


# ──────────────────────────────────────────────────────────────────────────────
# ALERT DATACLASS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Alert:
    """
    Represents one alert event. Immutable once created.

    Fields
    ------
    alert_id        : unique UUID string for this alert
    timestamp       : when this alert was generated (from dataset timestamp)
    bus_id          : bus that triggered the alert
    route_id        : route the bus is on
    stop_id         : stop where the condition was detected
    trip_id         : trip identifier
    passengers      : current_occupancy at this stop
    capacity        : bus_capacity
    occupancy_pct   : calculated percentage
    severity        : SEVERITY_NORMAL / WARNING / CRITICAL
    source          : where the reading came from (historical / IR / camera)
    day_type        : weekday or weekend
    peak_hour       : 1 (peak) or 0 (off-peak)
    note            : optional human-readable note
    """
    alert_id      : str
    timestamp     : pd.Timestamp
    bus_id        : str
    route_id      : str
    stop_id       : str
    trip_id       : int
    passengers    : int
    capacity      : int
    occupancy_pct : float
    severity      : str
    source        : str = SOURCE_HISTORICAL
    day_type      : str = ""
    peak_hour     : int = 0
    note          : str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = str(self.timestamp)
        return d


# ──────────────────────────────────────────────────────────────────────────────
# CORE: SEVERITY CLASSIFIER
# ──────────────────────────────────────────────────────────────────────────────

def classify_severity(occupancy_pct: float) -> str:
    """
    Classify a single occupancy percentage into an alert severity level.

    Parameters
    ----------
    occupancy_pct : float  (0 – 100+)

    Returns
    -------
    str : one of SEVERITY_NORMAL, SEVERITY_WARNING, SEVERITY_CRITICAL
    """
    if occupancy_pct >= THRESHOLD_CRITICAL:
        return SEVERITY_CRITICAL
    elif occupancy_pct >= THRESHOLD_WARNING:
        return SEVERITY_WARNING
    else:
        return SEVERITY_NORMAL


# ──────────────────────────────────────────────────────────────────────────────
# CORE: ALERT GENERATION FROM DATAFRAME
# ──────────────────────────────────────────────────────────────────────────────

def generate_alerts(
    df: pd.DataFrame,
    source: str = SOURCE_HISTORICAL,
    include_normal: bool = True,
) -> list[Alert]:
    """
    Generate a deduplicated list of Alert objects from a DataFrame.

    DEDUPLICATION: Within each (trip_id, bus_id), an alert is emitted only when
    the severity CHANGES from the previous stop. The first stop always emits.
    This means a bus stuck at WARNING for 5 stops produces 1 WARNING alert,
    not 5.

    Parameters
    ----------
    df             : DataFrame with columns from bus_occupancy.csv
                     (occupancy_pct must already be computed — use compute_occupancy_pct)
    source         : tag identifying the data source (historical / IR / camera)
    include_normal : if False, only WARNING and CRITICAL alerts are returned
                     (useful for live dashboards that only want actionable alerts)

    Returns
    -------
    list[Alert] ordered by timestamp ascending
    """
    if "occupancy_pct" not in df.columns:
        df = compute_occupancy_pct(df)

    df = df.copy()
    df["severity"] = df["occupancy_pct"].apply(classify_severity)

    alerts: list[Alert] = []

    # Process trip by trip, bus by bus, in chronological order
    grouped = df.sort_values(["trip_id", "bus_id", "timestamp"]).groupby(
        ["trip_id", "bus_id"], sort=False
    )

    for (trip_id, bus_id), group in grouped:
        group = group.reset_index(drop=True)
        prev_severity: Optional[str] = None

        for _, row in group.iterrows():
            current_severity = row["severity"]

            # Emit only on severity change (or first stop of trip)
            if current_severity != prev_severity:
                if include_normal or current_severity != SEVERITY_NORMAL:
                    # Build note
                    note = _build_note(current_severity, prev_severity)

                    alerts.append(Alert(
                        alert_id      = str(uuid.uuid4()),
                        timestamp     = row["timestamp"],
                        bus_id        = bus_id,
                        route_id      = row["route_id"],
                        stop_id       = row["stop_id"],
                        trip_id       = int(trip_id),
                        passengers    = int(row["current_occupancy"]),
                        capacity      = int(row["bus_capacity"]),
                        occupancy_pct = round(float(row["occupancy_pct"]), 1),
                        severity      = current_severity,
                        source        = source,
                        day_type      = row.get("day_type", ""),
                        peak_hour     = int(row.get("peak_hour", 0)),
                        note          = note,
                    ))

            prev_severity = current_severity

    # Sort chronologically
    alerts.sort(key=lambda a: a.timestamp)
    return alerts


def _build_note(current: str, previous: Optional[str]) -> str:
    """Build a human-readable note describing the severity transition."""
    if previous is None:
        return f"Trip start — status: {current}."
    if current == SEVERITY_CRITICAL:
        return f"ESCALATED to CRITICAL from {previous}. Bus is full."
    if current == SEVERITY_WARNING:
        if previous == SEVERITY_CRITICAL:
            return f"Improved to WARNING from CRITICAL."
        return f"Escalated to WARNING from {previous}."
    if current == SEVERITY_NORMAL:
        return f"Returned to NORMAL from {previous}."
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# ALERT UTILITIES
# ──────────────────────────────────────────────────────────────────────────────

def alerts_to_dataframe(alerts: list[Alert]) -> pd.DataFrame:
    """Convert a list of Alert objects to a tidy DataFrame for display."""
    if not alerts:
        return pd.DataFrame(columns=[
            "alert_id", "timestamp", "bus_id", "route_id", "stop_id",
            "trip_id", "passengers", "capacity", "occupancy_pct",
            "severity", "source", "day_type", "peak_hour", "note",
        ])
    rows = [a.to_dict() for a in alerts]
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def filter_alerts(
    alerts: list[Alert],
    bus_ids:    list[str] | None = None,
    severities: list[str] | None = None,
    route_ids:  list[str] | None = None,
    day_types:  list[str] | None = None,
) -> list[Alert]:
    """
    Filter a list of Alert objects by one or more criteria.
    All parameters are optional (None = no filter applied).
    """
    result = alerts
    if bus_ids:
        result = [a for a in result if a.bus_id in bus_ids]
    if severities:
        result = [a for a in result if a.severity in severities]
    if route_ids:
        result = [a for a in result if a.route_id in route_ids]
    if day_types:
        result = [a for a in result if a.day_type in day_types]
    return result


def get_active_alerts(alerts: list[Alert]) -> list[Alert]:
    """
    Return the LATEST alert per (bus_id) — i.e. each bus's most recent status.
    This simulates what a 'live' alert panel would show.
    """
    latest: dict[str, Alert] = {}
    for alert in sorted(alerts, key=lambda a: a.timestamp):
        latest[alert.bus_id] = alert   # overwrite → keeps most recent
    return list(latest.values())


def get_alert_summary(alerts: list[Alert]) -> dict:
    """
    Return aggregate KPIs for the given alert list.
    """
    if not alerts:
        return {
            "total_alerts": 0,
            "critical_count": 0,
            "warning_count": 0,
            "normal_count": 0,
            "buses_affected_critical": 0,
            "buses_affected_warning": 0,
            "most_alerted_bus": "N/A",
            "most_alerted_route": "N/A",
        }

    df = alerts_to_dataframe(alerts)
    bus_alert_counts = df["bus_id"].value_counts()

    return {
        "total_alerts"            : len(alerts),
        "critical_count"          : int((df["severity"] == SEVERITY_CRITICAL).sum()),
        "warning_count"           : int((df["severity"] == SEVERITY_WARNING).sum()),
        "normal_count"            : int((df["severity"] == SEVERITY_NORMAL).sum()),
        "buses_affected_critical" : int(df[df["severity"] == SEVERITY_CRITICAL]["bus_id"].nunique()),
        "buses_affected_warning"  : int(df[df["severity"] == SEVERITY_WARNING]["bus_id"].nunique()),
        "most_alerted_bus"        : bus_alert_counts.idxmax() if not bus_alert_counts.empty else "N/A",
        "most_alerted_route"      : df["route_id"].value_counts().idxmax() if not df.empty else "N/A",
    }


# ──────────────────────────────────────────────────────────────────────────────
# CHARTS
# ──────────────────────────────────────────────────────────────────────────────

def build_alert_severity_chart(alerts: list[Alert]) -> go.Figure:
    """Horizontal stacked bar — alert counts by severity per bus."""
    if not alerts:
        fig = go.Figure()
        fig.add_annotation(text="No alerts to display", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="gray"))
        return fig

    df = alerts_to_dataframe(alerts)
    pivot = (
        df.groupby(["bus_id", "severity"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=ALL_SEVERITIES, fill_value=0)
    )

    fig = go.Figure()
    for sev in ALL_SEVERITIES:
        if sev in pivot.columns:
            fig.add_trace(go.Bar(
                name=f"{ALERT_EMOJI[sev]} {sev}",
                y=pivot.index.tolist(),
                x=pivot[sev].tolist(),
                orientation="h",
                marker_color=ALERT_COLORS[sev],
                hovertemplate=f"<b>%{{y}}</b><br>{sev}: %{{x}} alert(s)<extra></extra>",
            ))

    fig.update_layout(
        barmode="stack",
        title="🚨 Alert Count by Bus and Severity",
        xaxis_title="Number of Alert Events",
        yaxis_title="Bus ID",
        template="plotly_white",
        height=480,
        legend_title="Severity",
        margin=dict(l=20, r=30, t=55, b=40),
    )
    return fig


def build_alert_timeline_chart(alerts: list[Alert]) -> go.Figure:
    """Scatter plot of alerts over time, coloured by severity."""
    if not alerts:
        fig = go.Figure()
        fig.add_annotation(text="No alerts to display", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False)
        return fig

    df = alerts_to_dataframe(alerts)
    df = df.sort_values("timestamp")

    fig = go.Figure()
    for sev in [SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_NORMAL]:
        sub = df[df["severity"] == sev]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["timestamp"],
            y=sub["occupancy_pct"],
            mode="markers",
            name=f"{ALERT_EMOJI[sev]} {sev}",
            marker=dict(
                color=ALERT_COLORS[sev],
                size=9,
                line=dict(width=0.8, color="white"),
                symbol="circle",
            ),
            customdata=sub[["bus_id", "route_id", "stop_id", "passengers",
                             "capacity", "note"]].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
                "Stop: %{customdata[2]}<br>"
                "Occupancy: %{y:.1f}%  (%{customdata[3]}/%{customdata[4]})<br>"
                "Time: %{x}<br>"
                "<i>%{customdata[5]}</i><extra></extra>"
            ),
        ))

    fig.add_hline(y=85,  line_dash="dash", line_color="#f39c12",
                  annotation_text="Warning threshold (85%)",
                  annotation_font_color="#f39c12")
    fig.add_hline(y=100, line_dash="dash", line_color="#e74c3c",
                  annotation_text="Critical threshold (100%)",
                  annotation_font_color="#e74c3c")

    fig.update_layout(
        title="📅 Alert Timeline — Occupancy % Over Time",
        xaxis_title="Date / Time",
        yaxis_title="Occupancy (%)",
        yaxis=dict(range=[0, 115]),
        template="plotly_white",
        height=420,
        hovermode="closest",
        legend_title="Severity",
        margin=dict(l=20, r=30, t=55, b=40),
    )
    return fig


def build_alert_heatmap_by_route(alerts: list[Alert]) -> go.Figure:
    """Heatmap: route × hour-of-day, value = count of non-Normal alerts."""
    if not alerts:
        fig = go.Figure()
        fig.add_annotation(text="No alert data", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False)
        return fig

    df = alerts_to_dataframe(alerts)
    df = df[df["severity"] != SEVERITY_NORMAL].copy()

    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No Warning / Critical alerts in selection",
                           xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
    pivot = (
        df.groupby(["route_id", "hour"])
        .size()
        .unstack(fill_value=0)
    )

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"{h}:00" for h in pivot.columns],
        y=pivot.index.tolist(),
        colorscale=[[0, "#ffffff"], [0.5, "#f39c12"], [1.0, "#e74c3c"]],
        colorbar=dict(title="Alert Count"),
        hovertemplate=(
            "<b>Route:</b> %{y}<br>"
            "<b>Hour:</b> %{x}<br>"
            "<b>Alerts:</b> %{z}<extra></extra>"
        ),
    ))
    fig.update_layout(
        title="🗺️ Warning + Critical Alerts by Route and Hour",
        xaxis_title="Hour of Day",
        yaxis_title="Route",
        template="plotly_white",
        height=320,
        margin=dict(l=60, r=30, t=55, b=40),
    )
    return fig


def build_occupancy_gauge(bus_id: str, occupancy_pct: float, passengers: int, capacity: int) -> go.Figure:
    """Gauge chart for a single bus's current (latest) occupancy."""
    if occupancy_pct < THRESHOLD_WARNING:
        bar_color = ALERT_COLORS[SEVERITY_NORMAL]
    elif occupancy_pct < THRESHOLD_CRITICAL:
        bar_color = ALERT_COLORS[SEVERITY_WARNING]
    else:
        bar_color = ALERT_COLORS[SEVERITY_CRITICAL]

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=occupancy_pct,
        number=dict(suffix="%", font=dict(size=28)),
        delta=dict(reference=85, increasing=dict(color="#e74c3c"),
                   decreasing=dict(color="#27ae60")),
        gauge=dict(
            axis=dict(range=[0, 110], tickwidth=1),
            bar=dict(color=bar_color, thickness=0.28),
            steps=[
                dict(range=[0, 85],  color="#eafaf1"),
                dict(range=[85, 100], color="#fef9e7"),
                dict(range=[100, 110], color="#fdedec"),
            ],
            threshold=dict(
                line=dict(color="#e74c3c", width=4),
                thickness=0.8, value=100,
            ),
        ),
        title=dict(text=f"{bus_id}<br><sub>{passengers}/{capacity} passengers</sub>",
                   font=dict(size=14)),
    ))
    fig.update_layout(
        height=240,
        margin=dict(l=20, r=20, t=40, b=10),
        template="plotly_white",
    )
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# [SLOT IR] — IR SENSOR ALERT TRIGGER (STUB)
# ──────────────────────────────────────────────────────────────────────────────

def trigger_sensor_alert(
    bus_id: str,
    route_id: str,
    stop_id: str,
    trip_id: int,
    passengers: int,
    capacity: int,
    sensor_id: str = "IR-UNKNOWN",
) -> Alert | None:
    """
    FUTURE — IR Sensor Integration Point.

    Called when an IR sensor reports a passenger count that may breach a threshold.
    Compute occupancy_pct from the raw count, classify severity, and return an Alert.

    Currently returns None (stub only — hardware not yet connected).
    Replace the TODO block below with your sensor SDK calls.
    """
    # TODO: validate sensor_status != "FAULT" before proceeding
    # TODO: debounce rapid pulses (e.g., require stable count for >2 seconds)
    occupancy_pct = round((passengers / max(capacity, 1)) * 100, 1)
    severity = classify_severity(occupancy_pct)

    if severity == SEVERITY_NORMAL:
        return None  # Only alert on actionable events

    # Uncomment when IR hardware is ready:
    # return Alert(
    #     alert_id=str(uuid.uuid4()),
    #     timestamp=pd.Timestamp.now(),
    #     bus_id=bus_id, route_id=route_id, stop_id=stop_id, trip_id=trip_id,
    #     passengers=passengers, capacity=capacity,
    #     occupancy_pct=occupancy_pct, severity=severity,
    #     source=f"{SOURCE_IR_SENSOR} ({sensor_id})",
    #     note=f"IR sensor {sensor_id} triggered {severity} alert.",
    # )
    return None


# ──────────────────────────────────────────────────────────────────────────────
# [SLOT CAM] — CAMERA ALERT TRIGGER (STUB)
# ──────────────────────────────────────────────────────────────────────────────

def trigger_camera_alert(
    bus_id: str,
    route_id: str,
    stop_id: str,
    trip_id: int,
    detected_count: int,
    capacity: int,
    confidence: float = 1.0,
    camera_id: str = "CAM-UNKNOWN",
) -> Alert | None:
    """
    FUTURE — Camera / Computer Vision Integration Point.

    Called when the CV pipeline detects a crowd count above threshold.
    Only generates an alert if confidence >= 0.7 (configurable).

    Currently returns None (stub only — CV pipeline not yet connected).
    """
    if confidence < 0.70:
        return None  # Skip low-confidence detections

    occupancy_pct = round((detected_count / max(capacity, 1)) * 100, 1)
    severity = classify_severity(occupancy_pct)

    if severity == SEVERITY_NORMAL:
        return None

    # Uncomment when camera CV model is ready:
    # return Alert(
    #     alert_id=str(uuid.uuid4()),
    #     timestamp=pd.Timestamp.now(),
    #     bus_id=bus_id, route_id=route_id, stop_id=stop_id, trip_id=trip_id,
    #     passengers=detected_count, capacity=capacity,
    #     occupancy_pct=occupancy_pct, severity=severity,
    #     source=f"{SOURCE_CAMERA} ({camera_id}), conf={confidence:.0%}",
    #     note=f"Camera {camera_id} detected {detected_count} pax (conf={confidence:.0%}).",
    # )
    return None


# ──────────────────────────────────────────────────────────────────────────────
# [SLOT FB] — FIREBASE PUSH (STUB)
# ──────────────────────────────────────────────────────────────────────────────

def push_alert_to_firebase(alert: Alert) -> bool:
    """
    FUTURE — Push an Alert to Firebase Realtime Database.
    Replace the TODO block with firebase_admin SDK calls.
    Currently a no-op; returns False.
    """
    # TODO: import firebase_admin; db.reference(f"/alerts/{alert.alert_id}").set(alert.to_dict())
    return False


# ──────────────────────────────────────────────────────────────────────────────
# STANDALONE SELF-TEST
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, io
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print("=" * 60)
    print("  Overcrowding Alert System - Self-Test")
    print("  Data source: historical dataset (bus_occupancy.csv)")
    print("=" * 60)

    df_raw, warns = load_data()
    df_calc = compute_occupancy_pct(df_raw)

    print(f"\n[OK] Dataset loaded: {len(df_calc)} records.")

    # Generate all alerts (including Normal)
    all_alerts = generate_alerts(df_calc, include_normal=True)
    print(f"[OK] Total alert events generated (deduplicated): {len(all_alerts)}")

    # Count by severity
    for sev in ALL_SEVERITIES:
        count = sum(1 for a in all_alerts if a.severity == sev)
        print(f"     {sev:10s}: {count} events")

    # Actionable only
    actionable = [a for a in all_alerts if a.severity != SEVERITY_NORMAL]
    print(f"\n[INFO] Actionable alerts (Warning + Critical): {len(actionable)}")

    # Active (latest per bus)
    active = get_active_alerts(all_alerts)
    print(f"[INFO] Active alerts (latest per bus): {len(active)}")
    for a in sorted(active, key=lambda x: x.severity):
        print(f"       {a.bus_id:15s} | {a.route_id:5s} | {a.severity:8s} | "
              f"{a.occupancy_pct:5.1f}% | {a.passengers}/{a.capacity} pax")

    # Summary KPIs
    summary = get_alert_summary(all_alerts)
    print(f"\n[SUMMARY]")
    for k, v in summary.items():
        print(f"   {k:<30}: {v}")

    print("\n[OK] Self-test complete.")
    print("     Launch the dashboard with:")
    print("     python -m streamlit run app_occupancy.py")

