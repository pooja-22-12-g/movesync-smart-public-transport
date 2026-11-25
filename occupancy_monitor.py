"""
occupancy_monitor.py
====================
Occupancy Monitoring Module — Smart Public Transport & Emission Monitoring System
----------------------------------------------------------------------------------
DATA SOURCE : data/bus_occupancy.csv  (historical dataset — NOT live sensor data)
AUTHOR      : Smart Transport Project
VERSION     : 1.0.0

MODULE DESIGN — Future Integration Points
------------------------------------------
  [SLOT A]  IR Sensor feed  → replace / supplement boarding & alighting counts
  [SLOT B]  Camera counter  → replace / supplement boarding & alighting counts
  [SLOT C]  Firebase / RTDB → push real-time occupancy updates to the cloud
  [SLOT D]  GPS module      → attach lat/lon to each record for map display
  [SLOT E]  Emission module → receive occupancy_pct to compute per-passenger CO2
"""

import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "bus_occupancy.csv")

# Occupancy thresholds (percentage)
STATUS_NORMAL_BELOW  = 85.0   # < 85 %  → Normal
STATUS_WARNING_BELOW = 100.0  # 85–99 % → Warning
# == 100 %               → Full

STATUS_COLORS = {
    "Normal":  "#27ae60",   # green
    "Warning": "#f39c12",   # amber
    "Full":    "#e74c3c",   # red
}

STATUS_EMOJI = {
    "Normal":  "🟢",
    "Warning": "🟡",
    "Full":    "🔴",
}

# ──────────────────────────────────────────────────────────────────────────────
# 1. DATA LOADING & VALIDATION
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_COLUMNS = {
    "trip_id", "timestamp", "bus_id", "route_id", "stop_id",
    "boarding", "alighting", "current_occupancy", "bus_capacity",
    "previous_occupancy", "peak_hour", "day_type", "fuel_consumption",
    "future_occupancy",
}


def load_data(path: str = DATA_PATH) -> tuple[pd.DataFrame, list[str]]:
    """
    Load and validate bus_occupancy.csv.

    Returns
    -------
    df      : cleaned DataFrame (original CSV is never written to)
    warnings: list of non-fatal data quality notes
    """
    warnings: list[str] = []

    # ── File existence check ──────────────────────────────────────────────────
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Dataset not found at '{path}'.\n"
            "Please ensure 'bus_occupancy.csv' is inside the 'data/' folder."
        )

    # ── Read CSV ──────────────────────────────────────────────────────────────
    df = pd.read_csv(path)

    # ── Column check ─────────────────────────────────────────────────────────
    missing_cols = REQUIRED_COLUMNS - set(df.columns)
    if missing_cols:
        raise ValueError(f"CSV is missing required columns: {missing_cols}")

    # ── Convert timestamp (in-memory only — CSV not touched) ─────────────────
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    nat_count = df["timestamp"].isna().sum()
    if nat_count > 0:
        warnings.append(
            f"{nat_count} rows had unparseable timestamps and were kept "
            "with NaT values."
        )

    # ── Handle missing numeric values ─────────────────────────────────────────
    numeric_cols = [
        "boarding", "alighting", "current_occupancy",
        "bus_capacity", "previous_occupancy", "fuel_consumption",
        "future_occupancy",
    ]
    for col in numeric_cols:
        null_n = df[col].isna().sum()
        if null_n > 0:
            df[col] = df[col].fillna(0)
            warnings.append(f"Column '{col}': {null_n} missing values filled with 0.")

    # ── Guard: bus_capacity must never be 0 (prevents division-by-zero) ───────
    zero_cap = df["bus_capacity"] == 0
    if zero_cap.any():
        df.loc[zero_cap, "bus_capacity"] = 1          # safe fallback
        warnings.append(
            f"{zero_cap.sum()} rows had bus_capacity = 0; replaced with 1 "
            "to prevent division-by-zero."
        )

    # ── Clip occupancy to valid range [0, bus_capacity] ──────────────────────
    bad_occ = (df["current_occupancy"] < 0) | (df["current_occupancy"] > df["bus_capacity"])
    if bad_occ.any():
        df.loc[bad_occ, "current_occupancy"] = df.loc[bad_occ, "current_occupancy"].clip(
            lower=0, upper=df.loc[bad_occ, "bus_capacity"]
        )
        warnings.append(
            f"{bad_occ.sum()} rows had out-of-range current_occupancy; clipped."
        )

    return df, warnings


# ──────────────────────────────────────────────────────────────────────────────
# 2. OCCUPANCY CALCULATIONS
# ──────────────────────────────────────────────────────────────────────────────

def compute_occupancy_pct(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add occupancy_pct and occupancy_status columns to the dataframe.
    Does NOT modify the original CSV.
    """
    df = df.copy()
    df["occupancy_pct"] = (df["current_occupancy"] / df["bus_capacity"] * 100).round(2)

    df["occupancy_status"] = df["occupancy_pct"].apply(_classify_status)
    return df


def _classify_status(pct: float) -> str:
    """Classify a single occupancy percentage into a status string."""
    if pct >= STATUS_WARNING_BELOW:
        return "Full"
    elif pct >= STATUS_NORMAL_BELOW:
        return "Warning"
    else:
        return "Normal"


# ──────────────────────────────────────────────────────────────────────────────
# 3. BUS-LEVEL SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

def get_bus_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate occupancy statistics per bus_id.

    Returns a DataFrame with one row per bus containing:
      bus_id, route_id, total_trips, total_stops_recorded,
      avg_occupancy, max_occupancy, avg_occupancy_pct,
      pct_normal, pct_warning, pct_full
    """
    df = compute_occupancy_pct(df)

    agg = df.groupby("bus_id").agg(
        route_id        = ("route_id", lambda x: x.mode().iloc[0]),
        total_trips     = ("trip_id", "nunique"),
        total_stops     = ("stop_id", "count"),
        bus_capacity    = ("bus_capacity", "first"),
        avg_passengers  = ("current_occupancy", "mean"),
        max_passengers  = ("current_occupancy", "max"),
        avg_occ_pct     = ("occupancy_pct", "mean"),
        max_occ_pct     = ("occupancy_pct", "max"),
    ).reset_index()

    # Status breakdown percentages
    status_counts = (
        df.groupby(["bus_id", "occupancy_status"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=["Normal", "Warning", "Full"], fill_value=0)
    )
    status_pct = status_counts.div(status_counts.sum(axis=1), axis=0).mul(100).round(1)
    status_pct.columns = ["pct_normal", "pct_warning", "pct_full"]

    summary = agg.merge(status_pct, on="bus_id", how="left")
    summary["avg_passengers"] = summary["avg_passengers"].round(1)
    summary["avg_occ_pct"]    = summary["avg_occ_pct"].round(1)
    summary["max_occ_pct"]    = summary["max_occ_pct"].round(1)

    return summary


# ──────────────────────────────────────────────────────────────────────────────
# 4. FILTERING HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def filter_data(
    df: pd.DataFrame,
    bus_ids:    list[str] | None = None,
    route_ids:  list[str] | None = None,
    day_types:  list[str] | None = None,
    peak_only:  bool             = False,
) -> pd.DataFrame:
    """
    Filter the dataset by one or more criteria.
    All parameters are optional — passing None means 'no filter'.

    [SLOT D] GPS module can add a bounding-box filter here later.
    """
    mask = pd.Series(True, index=df.index)

    if bus_ids:
        mask &= df["bus_id"].isin(bus_ids)
    if route_ids:
        mask &= df["route_id"].isin(route_ids)
    if day_types:
        mask &= df["day_type"].isin(day_types)
    if peak_only:
        mask &= df["peak_hour"] == 1

    return df[mask].copy()


# ──────────────────────────────────────────────────────────────────────────────
# 5. OCCUPANCY TREND CHART  (Plotly)
# ──────────────────────────────────────────────────────────────────────────────

def build_trend_chart(
    df: pd.DataFrame,
    bus_id: str,
    trip_id: int | None = None,
) -> go.Figure:
    """
    Build an interactive Plotly line chart showing occupancy % over stops
    for a specific bus (and optionally a specific trip).

    [SLOT A/B] In future, IR / camera counts can feed live data into this chart.
    [SLOT C]   Firebase listener can refresh this chart in near-real-time.
    """
    df = compute_occupancy_pct(df)
    bus_data = df[df["bus_id"] == bus_id].copy()

    if bus_data.empty:
        fig = go.Figure()
        fig.add_annotation(
            text=f"No data found for bus '{bus_id}'",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=16, color="gray"),
        )
        return fig

    if trip_id is not None:
        bus_data = bus_data[bus_data["trip_id"] == trip_id]

    bus_data = bus_data.sort_values(["trip_id", "timestamp"])

    # Assign colour per status
    bus_data["marker_color"] = bus_data["occupancy_status"].map(STATUS_COLORS)

    fig = go.Figure()

    # One trace per trip for legend clarity
    for tid in bus_data["trip_id"].unique():
        trip_df = bus_data[bus_data["trip_id"] == tid].sort_values("timestamp")

        fig.add_trace(go.Scatter(
            x=trip_df["stop_id"],
            y=trip_df["occupancy_pct"],
            mode="lines+markers",
            name=f"Trip {tid}",
            marker=dict(
                color=trip_df["marker_color"],
                size=9,
                line=dict(width=1, color="white"),
            ),
            line=dict(width=2),
            customdata=trip_df[[
                "current_occupancy", "bus_capacity",
                "boarding", "alighting", "occupancy_status", "timestamp"
            ]].values,
            hovertemplate=(
                "<b>Stop:</b> %{x}<br>"
                "<b>Occupancy:</b> %{y:.1f}%<br>"
                "<b>Passengers:</b> %{customdata[0]} / %{customdata[1]}<br>"
                "<b>Boarding:</b> %{customdata[2]}  |  "
                "<b>Alighting:</b> %{customdata[3]}<br>"
                "<b>Status:</b> %{customdata[4]}<br>"
                "<b>Time:</b> %{customdata[5]}<extra></extra>"
            ),
        ))

    # Threshold lines
    fig.add_hline(
        y=85, line_dash="dash", line_color="#f39c12",
        annotation_text="Warning (85%)",
        annotation_position="top right",
        annotation_font_color="#f39c12",
    )
    fig.add_hline(
        y=100, line_dash="dash", line_color="#e74c3c",
        annotation_text="Full (100%)",
        annotation_position="top right",
        annotation_font_color="#e74c3c",
    )

    title_suffix = f" — Trip {trip_id}" if trip_id else " — All Trips"
    fig.update_layout(
        title=dict(
            text=f"🚌 Occupancy Trend · {bus_id}{title_suffix}",
            font=dict(size=16),
        ),
        xaxis_title="Stop ID",
        yaxis_title="Occupancy (%)",
        yaxis=dict(range=[0, 110]),
        legend_title="Trip",
        hovermode="x unified",
        template="plotly_white",
        height=440,
        margin=dict(l=50, r=30, t=60, b=60),
    )

    return fig


# ──────────────────────────────────────────────────────────────────────────────
# 6. ROUTE-LEVEL HEATMAP
# ──────────────────────────────────────────────────────────────────────────────

def build_route_heatmap(df: pd.DataFrame, route_id: str) -> go.Figure:
    """
    Build a stop × time-of-day heatmap of average occupancy % for one route.
    """
    df = compute_occupancy_pct(df)
    route_df = df[df["route_id"] == route_id].copy()

    if route_df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text=f"No data for route '{route_id}'",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        return fig

    route_df["hour"] = route_df["timestamp"].dt.hour.fillna(-1).astype(int)
    pivot = (
        route_df.groupby(["stop_id", "hour"])["occupancy_pct"]
        .mean()
        .unstack(fill_value=0)
        .round(1)
    )

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"{h}:00" for h in pivot.columns],
        y=pivot.index.tolist(),
        colorscale=[
            [0.0,  "#27ae60"],
            [0.85, "#f39c12"],
            [1.0,  "#e74c3c"],
        ],
        zmin=0, zmax=100,
        colorbar=dict(title="Occ. %"),
        hovertemplate=(
            "<b>Stop:</b> %{y}<br>"
            "<b>Hour:</b> %{x}<br>"
            "<b>Avg Occupancy:</b> %{z:.1f}%<extra></extra>"
        ),
    ))

    fig.update_layout(
        title=f"🗺️ Stop × Hour Occupancy Heatmap — Route {route_id}",
        xaxis_title="Hour of Day",
        yaxis_title="Stop",
        template="plotly_white",
        height=420,
        margin=dict(l=80, r=30, t=60, b=60),
    )
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# 7. STATUS DISTRIBUTION CHART
# ──────────────────────────────────────────────────────────────────────────────

def build_status_distribution_chart(df: pd.DataFrame) -> go.Figure:
    """Donut chart showing overall Normal / Warning / Full record counts."""
    df = compute_occupancy_pct(df)
    counts = df["occupancy_status"].value_counts().reindex(
        ["Normal", "Warning", "Full"], fill_value=0
    )

    fig = go.Figure(go.Pie(
        labels=counts.index.tolist(),
        values=counts.values.tolist(),
        hole=0.55,
        marker=dict(colors=[STATUS_COLORS[s] for s in counts.index]),
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>Records: %{value}<br>Share: %{percent}<extra></extra>",
    ))

    fig.update_layout(
        title="📊 Overall Occupancy Status Distribution",
        template="plotly_white",
        height=380,
        showlegend=True,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# 8. QUICK STATISTICS
# ──────────────────────────────────────────────────────────────────────────────

def get_fleet_kpis(df: pd.DataFrame) -> dict:
    """
    Return a dict of top-level KPIs for the entire loaded dataset.

    [SLOT C] Firebase can push these KPIs to a cloud dashboard.
    """
    df = compute_occupancy_pct(df)
    status_counts = df["occupancy_status"].value_counts()

    return {
        "total_records"       : len(df),
        "total_buses"         : df["bus_id"].nunique(),
        "total_routes"        : df["route_id"].nunique(),
        "total_trips"         : df["trip_id"].nunique(),
        "date_range_start"    : df["timestamp"].min(),
        "date_range_end"      : df["timestamp"].max(),
        "avg_occupancy_pct"   : round(df["occupancy_pct"].mean(), 1),
        "max_occupancy_pct"   : round(df["occupancy_pct"].max(), 1),
        "pct_normal"          : round(status_counts.get("Normal",  0) / len(df) * 100, 1),
        "pct_warning"         : round(status_counts.get("Warning", 0) / len(df) * 100, 1),
        "pct_full"            : round(status_counts.get("Full",    0) / len(df) * 100, 1),
        "full_capacity_events": int(status_counts.get("Full", 0)),
    }


# ──────────────────────────────────────────────────────────────────────────────
# [SLOT A]  IR SENSOR INTEGRATION STUB
# ──────────────────────────────────────────────────────────────────────────────

def ingest_ir_sensor_reading(
    bus_id: str,
    stop_id: str,
    direction: str,          # "IN" or "OUT"
    raw_count: int,
    sensor_status: str,      # "OK", "FAULT", "OFFLINE"
) -> dict | None:
    """
    FUTURE: Accept a real-time IR sensor pulse and return a boarding/alighting delta.
    Currently returns None (stub only — not yet connected to live hardware).
    Connect your IR sensor feed here when hardware is ready.
    """
    # TODO: Implement when IR sensor hardware/API is available
    return None


# ──────────────────────────────────────────────────────────────────────────────
# [SLOT B]  CAMERA COUNTER INTEGRATION STUB
# ──────────────────────────────────────────────────────────────────────────────

def ingest_camera_count(
    bus_id: str,
    stop_id: str,
    detected_boarding: int,
    detected_alighting: int,
    confidence_score: float,
) -> dict | None:
    """
    FUTURE: Accept a camera-detected passenger count and merge with occupancy state.
    Currently returns None (stub only — not yet connected to live vision pipeline).
    Connect your CV camera model output here when ready.
    """
    # TODO: Implement when camera model pipeline is ready
    return None


# ──────────────────────────────────────────────────────────────────────────────
# [SLOT C]  FIREBASE PUSH STUB
# ──────────────────────────────────────────────────────────────────────────────

def push_to_firebase(bus_id: str, occupancy_record: dict) -> bool:
    """
    FUTURE: Push a real-time occupancy record to Firebase Realtime Database.
    Currently a no-op stub. Replace with firebase_admin SDK calls when ready.
    """
    # TODO: import firebase_admin and implement push logic
    return False


# ──────────────────────────────────────────────────────────────────────────────
# STANDALONE TEST  (python occupancy_monitor.py)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    # Force UTF-8 output so emoji prints safely on Windows terminals
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    print("=" * 60)
    print("  Occupancy Monitor - Self-Test")
    print("  Data source: historical dataset (bus_occupancy.csv)")
    print("=" * 60)

    df_raw, warns = load_data()
    print(f"\n[OK] Loaded {len(df_raw)} records from CSV.")

    if warns:
        print("\n[WARN] Data quality notes:")
        for w in warns:
            print(f"   * {w}")
    else:
        print("[OK] No data quality issues detected.")

    df_calc = compute_occupancy_pct(df_raw)
    kpis = get_fleet_kpis(df_calc)

    print("\n[KPIs] Fleet-level statistics:")
    for k, v in kpis.items():
        print(f"   {k:<28}: {v}")

    summary = get_bus_summary(df_raw)
    print(f"\n[BUS SUMMARY] {len(summary)} buses:")
    print(summary[["bus_id", "route_id", "total_trips", "avg_occ_pct", "max_occ_pct"]].to_string(index=False))

    print("\n[OK] Self-test complete.")
    print("     Launch the Streamlit app with:")
    print("     streamlit run app_occupancy.py")
