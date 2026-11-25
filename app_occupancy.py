"""
app_occupancy.py
================
Streamlit Dashboard — Smart Public Transport Occupancy and Fleet Monitoring System
----------------------------------------------------------------------------------
DATA SOURCE : data/bus_occupancy.csv  (HISTORICAL DATASET — NOT live data)
              data/route_coordinates.csv (Simulated GPS route waypoints)
              data/cv_sessions/       (Camera / YOLO video counting sessions)
Modules     : Module 1 — Occupancy Monitoring
              Module 2 — Overcrowding Alert System
              Module 3 — GPS Tracking & Monitoring
              Module 4 — Passenger Counting (YOLO & ByteTrack)
              Module 5 — Occupancy Prediction & Crowding Forecast
Run with    : python -m streamlit run app_occupancy.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ── Module imports ────────────────────────────────────────────────────────────
from occupancy_monitor import (
    load_data,
    compute_occupancy_pct,
    get_bus_summary,
    get_fleet_kpis,
    filter_data,
    build_trend_chart,
    build_route_heatmap,
    build_status_distribution_chart,
    STATUS_COLORS,
    STATUS_EMOJI,
)
from overcrowding_alerts import (
    generate_alerts,
    filter_alerts,
    get_active_alerts,
    get_alert_summary,
    alerts_to_dataframe,
    build_alert_severity_chart,
    build_alert_timeline_chart,
    build_alert_heatmap_by_route,
    build_occupancy_gauge,
    ALERT_COLORS,
    ALERT_BG_COLORS,
    ALERT_TEXT_COLORS,
    ALERT_EMOJI,
    ALERT_ICONS,
    SEVERITY_NORMAL,
    SEVERITY_WARNING,
    SEVERITY_CRITICAL,
    ALL_SEVERITIES,
    THRESHOLD_WARNING,
    THRESHOLD_CRITICAL,
)

from gps_tracking import (
    load_route_coordinates,
    simulate_gps_positions,
    filter_gps_readings,
    readings_to_dataframe,
    get_gps_summary,
    build_gps_map,
    build_gps_status_chart,
    classify_gps_status,
    GPS_STATUS_COLORS,
    GPS_STATUS_EMOJI,
    ALL_GPS_STATUSES,
    GPS_STATUS_RECENT,
    GPS_STATUS_DELAYED,
    GPS_STATUS_STALE,
    GPS_STATUS_LOST,
    SOURCE_SIMULATED,
)
from passenger_counting import (
    YOLOPersonDetector,
    PersonDetection,
    ByteTrackTracker,
    TrackedPerson,
    EntryExitCounter,
    VirtualLine,
    LineOrientation,
    DirectionConfig,
    CountingSummary,
    OccupancyIntegrator,
    OccupancyUpdateResult,
    THRESHOLD_WARNING as PC_THRESHOLD_WARNING,
    THRESHOLD_CRITICAL as PC_THRESHOLD_CRITICAL,
    SEVERITY_NORMAL as PC_SEVERITY_NORMAL,
    SEVERITY_WARNING as PC_SEVERITY_WARNING,
    SEVERITY_CRITICAL as PC_SEVERITY_CRITICAL,
)
from occupancy_prediction import (
    FutureOccupancyPredictor,
    MultiStopOccupancyPredictor,
    HistoricalStopProfile,
    CrowdingForecaster,
    CrowdingForecastResult,
    EarlyWarningNotice,
    PredictionResult,
    MultiStopPredictionResult,
    StopPredictionDetail,
)
from scheduling import (
    RouteDemandAnalyzer,
    RouteDemandProfile,
    HourlyDemandProfile,
    HeadwayOptimizer,
    PeriodHeadwayRecommendation,
    DepartureSlot,
    RouteOptimizedTimetable,
    DispatchAdvisor,
    DispatchPriority,
    InterventionStatus,
    FleetDepotState,
    DispatchInterventionRecommendation,
    VALID_ROUTES as SCHED_VALID_ROUTES,
)

# ──────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Smart Transport Dashboard",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# SHARED CSS
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* ── Banner ── */
    .banner {
        background: linear-gradient(135deg, #1a237e 0%, #1565c0 60%, #0288d1 100%);
        padding: 16px 26px; border-radius: 12px;
        margin-bottom: 18px; color: white;
    }
    .banner h1 { margin: 0; font-size: 1.6rem; font-weight: 700; }
    .banner p  { margin: 3px 0 0 0; font-size: 0.88rem; opacity: 0.88; }

    /* ── Data badge ── */
    .data-badge {
        display: inline-block; background: #fff3cd;
        border: 1px solid #ffc107; color: #856404;
        border-radius: 6px; padding: 5px 13px;
        font-size: 0.80rem; font-weight: 600; margin-bottom: 16px;
    }

    /* ── KPI card ── */
    .kpi-card {
        background: #f8f9fa; border: 1px solid #dee2e6;
        border-radius: 10px; padding: 13px 16px; text-align: center;
    }
    .kpi-label { font-size: 0.74rem; color: #6c757d; font-weight: 600;
                 text-transform: uppercase; letter-spacing: 0.04em; }
    .kpi-value { font-size: 1.9rem; font-weight: 800; color: #1a237e;
                 line-height: 1.1; margin: 3px 0 1px 0; }
    .kpi-sub   { font-size: 0.72rem; color: #adb5bd; }

    /* KPI variants */
    .kpi-critical .kpi-value { color: #c62828; }
    .kpi-warning  .kpi-value { color: #e65100; }
    .kpi-ok       .kpi-value { color: #2e7d32; }

    /* ── Status pills ── */
    .pill-normal   { background:#d4edda; color:#155724; border-radius:20px;
                     padding:3px 12px; font-size:0.80rem; font-weight:700; }
    .pill-warning  { background:#fff3cd; color:#856404; border-radius:20px;
                     padding:3px 12px; font-size:0.80rem; font-weight:700; }
    .pill-critical { background:#f8d7da; color:#721c24; border-radius:20px;
                     padding:3px 12px; font-size:0.80rem; font-weight:700; }
    .pill-full     { background:#f8d7da; color:#721c24; border-radius:20px;
                     padding:3px 12px; font-size:0.80rem; font-weight:700; }

    /* ── Alert card ── */
    .alert-card {
        border-radius: 9px; padding: 12px 16px;
        margin-bottom: 10px; border-left: 5px solid;
    }
    .alert-card-critical { border-color: #e74c3c; background: #fdf3f3; }
    .alert-card-warning  { border-color: #f39c12; background: #fffbf0; }
    .alert-card-normal   { border-color: #27ae60; background: #f3fdf6; }
    .alert-bus    { font-weight: 700; font-size: 1.0rem; }
    .alert-detail { font-size: 0.82rem; color: #555; margin-top: 3px; }
    .alert-note   { font-size: 0.78rem; color: #888; font-style: italic;
                    margin-top: 4px; }

    /* ── Section title ── */
    .section-title {
        font-size: 1.02rem; font-weight: 700; color: #1a237e;
        border-left: 4px solid #1565c0; padding-left: 10px;
        margin: 20px 0 11px 0;
    }

    /* ── Threshold badge ── */
    .threshold-badge {
        display: inline-block; border-radius: 5px;
        padding: 3px 10px; font-size: 0.78rem; font-weight: 600;
        margin-right: 6px;
    }

    /* ── GPS status pill ── */
    .gps-pill {
        display: inline-block; border-radius: 20px;
        padding: 3px 12px; font-size: 0.80rem; font-weight: 700;
        margin-right: 6px;
    }

    /* ── GPS detail card ── */
    .gps-detail-card {
        background: #f8f9fa; border: 1px solid #dee2e6;
        border-radius: 10px; padding: 14px 18px;
    }
    .gps-detail-label { font-size: 0.74rem; color: #6c757d; font-weight: 600;
                        text-transform: uppercase; letter-spacing: 0.04em; }
    .gps-detail-value { font-size: 1.1rem; font-weight: 700; color: #1a237e;
                       margin: 2px 0 4px 0; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# DATA LOAD  (cached — CSV read once per session, never written to)
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="📂 Loading dataset…")
def cached_load():
    return load_data()


try:
    df_raw, load_warnings = cached_load()
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()
except ValueError as e:
    st.error(f"Dataset validation failed: {e}")
    st.stop()

df_full = compute_occupancy_pct(df_raw)   # in-memory enrichment; CSV untouched

# Pre-generate alert list once (cached via st.cache_data indirection)
@st.cache_data(show_spinner="🔔 Generating alert history…")
def cached_alerts(_df):
    return generate_alerts(_df, include_normal=True)

all_alerts = cached_alerts(df_full)


# ──────────────────────────────────────────────────────────────────────────────
# SHARED SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🚌 Smart Transport")
    st.caption("Monitoring Dashboard")
    st.divider()

    st.markdown("### 🔧 Global Filters")
    st.caption("Applied to both modules")

    all_routes = sorted(df_full["route_id"].unique())
    all_buses  = sorted(df_full["bus_id"].unique())
    all_days   = sorted(df_full["day_type"].unique())

    sel_routes = st.multiselect("Route(s)", all_routes, default=all_routes)
    sel_buses  = st.multiselect("Bus ID(s)", all_buses,  default=all_buses)
    sel_days   = st.multiselect("Day Type",  all_days,   default=all_days)
    peak_only  = st.toggle("Peak Hours Only", value=False)

    st.markdown("### 📅 Date Range")
    min_ts = df_full["timestamp"].min().date()
    max_ts = df_full["timestamp"].max().date()
    date_range = st.date_input(
        "Select Range", value=(min_ts, max_ts),
        min_value=min_ts, max_value=max_ts,
    )

    st.divider()
    st.markdown("### 🔔 Alert Thresholds")
    st.markdown(
        f'<span class="threshold-badge" style="background:#d4edda;color:#155724;">'
        f'🟢 Normal &lt; {THRESHOLD_WARNING:.0f}%</span><br>'
        f'<span class="threshold-badge" style="background:#fff3cd;color:#856404;">'
        f'🟡 Warning ≥ {THRESHOLD_WARNING:.0f}%</span><br>'
        f'<span class="threshold-badge" style="background:#f8d7da;color:#721c24;">'
        f'🔴 Critical ≥ {THRESHOLD_CRITICAL:.0f}%</span>',
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown("### ℹ️ Module Status")
    st.info(
        "**Active Modules:**\n"
        "- ✅ Module 1: Occupancy Monitoring\n"
        "- ✅ Module 2: Overcrowding Alerts\n"
        "- ✅ Module 3: Live Bus Tracking (GPS)\n"
        "- ✅ Module 4: Passenger Counter (YOLO + ByteTrack)\n"
        "- ✅ Module 5: Prediction & Crowding Forecast\n\n"
        "**Future Sensor Integration Slots:**\n"
        "- 🔴 IR Sensor feed\n"
        "- 📷 Live CCTV RTSP stream\n"
        "- ☁️ Firebase Realtime DB\n"
        "- 🛰️ Hardware GPS Module"
    )


# ──────────────────────────────────────────────────────────────────────────────
# APPLY GLOBAL FILTERS
# ──────────────────────────────────────────────────────────────────────────────

df = filter_data(
    df_full,
    bus_ids   = sel_buses  or None,
    route_ids = sel_routes or None,
    day_types = sel_days   or None,
    peak_only = peak_only,
)

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    s_date, e_date = date_range
    df = df[
        (df["timestamp"].dt.date >= s_date) &
        (df["timestamp"].dt.date <= e_date)
    ]

if df.empty:
    st.warning("⚠️ No records match the current filters. Adjust the sidebar filters.")
    st.stop()

# Filter alerts to match sidebar selection
filtered_alerts = filter_alerts(
    all_alerts,
    bus_ids   = sel_buses  or None,
    route_ids = sel_routes or None,
    day_types = sel_days   or None,
)
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    s_date, e_date = date_range
    filtered_alerts = [
        a for a in filtered_alerts
        if s_date <= a.timestamp.date() <= e_date
    ]


# ──────────────────────────────────────────────────────────────────────────────
# GLOBAL HEADER
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="banner">
    <h1>🚌 Smart Public Transport Occupancy and Fleet Monitoring System</h1>
    <p>Module 1: Occupancy Monitoring &nbsp;|&nbsp; Module 2: Overcrowding Alert System &nbsp;|&nbsp; Module 3: GPS Tracking &nbsp;|&nbsp; Module 4: Passenger Counting &nbsp;|&nbsp; Module 5: Occupancy Prediction</p>
</div>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="data-badge">📂 DATA SOURCE: Historical Dataset + Simulated GPS '
    '— NOT live sensor readings</div>',
    unsafe_allow_html=True,
)

if load_warnings:
    with st.expander("⚠️ Data Quality Notes", expanded=False):
        for w in load_warnings:
            st.warning(w)


# ──────────────────────────────────────────────────────────────────────────────
# MODULE TABS
# ──────────────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊  Module 1 — Occupancy Monitoring",
    "🚨  Module 2 — Overcrowding Alerts",
    "🛰️  Module 3 — Live Bus Tracking",
    "📷  Module 4 — Passenger Counting",
    "🔮  Module 5 — Prediction & Crowding Forecast",
    "⚡  Module 6 — Scheduling & Fleet Optimization",
])


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — OCCUPANCY MONITORING  (unchanged from original module)
# ══════════════════════════════════════════════════════════════════════════════

with tab1:

    # ── KPI Row ───────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📊 Fleet Overview</div>', unsafe_allow_html=True)
    kpis = get_fleet_kpis(df)

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    def kpi_card(col, label, value, sub="", variant=""):
        col.markdown(f"""
        <div class="kpi-card {variant}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

    kpi_card(k1, "Total Records",   kpis["total_records"],        "stop events")
    kpi_card(k2, "Buses Active",    kpis["total_buses"],          "unique buses")
    kpi_card(k3, "Routes Covered",  kpis["total_routes"],         "routes")
    kpi_card(k4, "Trips Recorded",  kpis["total_trips"],          "trips")
    kpi_card(k5, "Avg Occupancy",   f"{kpis['avg_occupancy_pct']}%", "fleet avg")
    kpi_card(k6, "Full Capacity",   kpis["full_capacity_events"], "100% events")

    st.markdown("<br>", unsafe_allow_html=True)
    b1, b2, b3, b4 = st.columns([2, 1, 1, 1])
    b1.markdown("**Status Breakdown** (filtered records):")
    b2.markdown(f'<span class="pill-normal">🟢 Normal: {kpis["pct_normal"]}%</span>',   unsafe_allow_html=True)
    b3.markdown(f'<span class="pill-warning">🟡 Warning: {kpis["pct_warning"]}%</span>', unsafe_allow_html=True)
    b4.markdown(f'<span class="pill-full">🔴 Full: {kpis["pct_full"]}%</span>',          unsafe_allow_html=True)
    st.markdown("---")

    # ── Stop-level table ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📋 Stop-Level Occupancy Records</div>', unsafe_allow_html=True)
    st.caption("⚠️ Historical dataset data — not live sensor readings")

    display_cols = [
        "bus_id","route_id","stop_id","timestamp","current_occupancy",
        "bus_capacity","occupancy_pct","boarding","alighting",
        "peak_hour","day_type","occupancy_status",
    ]
    df_display = df[display_cols].copy()
    df_display["timestamp"]       = df_display["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    df_display["peak_hour"]       = df_display["peak_hour"].map({1:"✅ Peak",0:"Off-Peak"})
    df_display["occupancy_status"]= df_display["occupancy_status"].apply(
        lambda s: f"{STATUS_EMOJI.get(s,'') } {s}"
    )
    df_display = df_display.rename(columns={
        "bus_id":"Bus ID","route_id":"Route","stop_id":"Stop",
        "timestamp":"Timestamp","current_occupancy":"Passengers",
        "bus_capacity":"Capacity","occupancy_pct":"Occ. %",
        "boarding":"Boarded","alighting":"Alighted",
        "peak_hour":"Time Type","day_type":"Day","occupancy_status":"Status",
    })
    rows_show = st.slider("Rows to display", 10, min(500, len(df_display)), 50, step=10, key="t1_rows")
    st.dataframe(
        df_display.head(rows_show), use_container_width=True, hide_index=True,
        column_config={
            "Occ. %": st.column_config.ProgressColumn("Occ. %", min_value=0, max_value=100, format="%.1f%%"),
            "Passengers": st.column_config.NumberColumn("Passengers", format="%d 👤"),
        },
    )
    st.markdown("---")

    # ── Bus summary ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">🚌 Individual Bus Summary</div>', unsafe_allow_html=True)
    st.caption("⚠️ Historical dataset data")
    summary = get_bus_summary(df)
    summary_display = summary.rename(columns={
        "bus_id":"Bus ID","route_id":"Route","total_trips":"Trips",
        "total_stops":"Stop Events","bus_capacity":"Capacity",
        "avg_passengers":"Avg Passengers","max_passengers":"Max Passengers",
        "avg_occ_pct":"Avg Occ. %","max_occ_pct":"Max Occ. %",
        "pct_normal":"% Normal","pct_warning":"% Warning","pct_full":"% Full",
    })
    st.dataframe(
        summary_display, use_container_width=True, hide_index=True,
        column_config={
            "Avg Occ. %": st.column_config.ProgressColumn("Avg Occ. %", min_value=0, max_value=100, format="%.1f%%"),
            "Max Occ. %": st.column_config.ProgressColumn("Max Occ. %", min_value=0, max_value=100, format="%.1f%%"),
        },
    )
    st.markdown("---")

    # ── Trend chart ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📈 Occupancy Trend Chart</div>', unsafe_allow_html=True)
    st.caption("Hover over points for full details  |  ⚠️ Historical data")

    tc1, tc2 = st.columns([2, 1])
    avail_buses = sorted(df["bus_id"].unique())
    sel_trend_bus = tc1.selectbox("Bus", avail_buses, key="t1_trend_bus")
    bus_trips = sorted(df[df["bus_id"] == sel_trend_bus]["trip_id"].unique())
    trip_opts = ["All Trips"] + [f"Trip {t}" for t in bus_trips]
    sel_trip_lbl = tc2.selectbox("Trip", trip_opts, key="t1_trend_trip")
    sel_trip_id  = None if sel_trip_lbl == "All Trips" else int(sel_trip_lbl.split()[-1])
    st.plotly_chart(build_trend_chart(df, sel_trend_bus, trip_id=sel_trip_id), use_container_width=True)
    st.markdown("---")

    # ── Distribution + Heatmap ────────────────────────────────────────────────
    st.markdown('<div class="section-title">🗺️ Status Distribution & Route Heatmap</div>', unsafe_allow_html=True)
    st.caption("⚠️ Historical dataset data")

    cl, cr = st.columns([1, 1.6])
    with cl:
        st.plotly_chart(build_status_distribution_chart(df), use_container_width=True)
    with cr:
        avail_routes = sorted(df["route_id"].unique())
        sel_heat_route = st.selectbox("Route for Heatmap", avail_routes, key="t1_heat_route")
        st.plotly_chart(build_route_heatmap(df, sel_heat_route), use_container_width=True)
    st.markdown("---")

    # ── Peak vs Off-Peak ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title">⏰ Peak vs Off-Peak Comparison</div>', unsafe_allow_html=True)
    peak_comp = (
        df.groupby(["day_type","peak_hour"])["occupancy_pct"].mean().reset_index()
    )
    peak_comp["label"] = peak_comp["day_type"] + " · " + peak_comp["peak_hour"].map({1:"Peak",0:"Off-Peak"})
    peak_comp = peak_comp.sort_values("occupancy_pct", ascending=True)
    bar_colors = ["#1565c0" if "Peak" in l else "#90caf9" for l in peak_comp["label"]]
    peak_fig = go.Figure(go.Bar(
        x=peak_comp["occupancy_pct"].round(1), y=peak_comp["label"],
        orientation="h", marker_color=bar_colors,
        text=[f"{v:.1f}%" for v in peak_comp["occupancy_pct"]], textposition="outside",
        hovertemplate="<b>%{y}</b><br>Avg Occupancy: %{x:.1f}%<extra></extra>",
    ))
    peak_fig.add_vline(x=85, line_dash="dash", line_color="#f39c12",
                       annotation_text="Warning 85%", annotation_font_color="#f39c12")
    peak_fig.update_layout(
        title="Average Occupancy % by Day Type and Time",
        xaxis_title="Avg Occupancy (%)", xaxis=dict(range=[0,115]),
        yaxis_title="", template="plotly_white", height=270, showlegend=False,
        margin=dict(l=10, r=50, t=50, b=40),
    )
    st.plotly_chart(peak_fig, use_container_width=True)

    # ── Raw inspector ─────────────────────────────────────────────────────────
    with st.expander("🔍 Raw Record Inspector", expanded=False):
        ri1, ri2 = st.columns(2)
        insp_bus  = ri1.selectbox("Bus",  avail_buses, key="t1_insp_bus")
        insp_trips= sorted(df[df["bus_id"]==insp_bus]["trip_id"].unique())
        insp_trip = ri2.selectbox("Trip", insp_trips,  key="t1_insp_trip")
        raw_view  = df[(df["bus_id"]==insp_bus) & (df["trip_id"]==insp_trip)].sort_values("timestamp")
        raw_view  = raw_view[display_cols].copy()
        raw_view["timestamp"] = raw_view["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
        raw_view["occupancy_status"] = raw_view["occupancy_status"].apply(
            lambda s: f"{STATUS_EMOJI.get(s,'')} {s}"
        )
        st.dataframe(raw_view, use_container_width=True, hide_index=True)

    # ── Basic Fuel Usage Summary ─────────────────────────────────────────────
    if "fuel_consumption" in df.columns:
        with st.expander("⛽ Fuel Consumption Summary", expanded=False):
            st.caption("Historical fuel telemetry recorded from operational telemetry (`fuel_consumption` in litres)")
            tot_fuel = round(float(df["fuel_consumption"].sum()), 2)
            mean_fuel_stop = round(float(df["fuel_consumption"].mean()), 3)
            
            fc1, fc2, fc3 = st.columns(3)
            fc1.metric("Total Fuel Consumed", f"{tot_fuel:,.2f} L", "across filtered trips")
            fc2.metric("Mean Fuel per Stop Event", f"{mean_fuel_stop:.3f} L", "per stop arrival")
            fc3.metric("Fleet Vehicles Tracked", f"{df['bus_id'].nunique()} buses", "with fuel telemetry")

            fuel_tab_bus, fuel_tab_route = st.tabs(["🚌 Bus-Wise Consumption", "🗺️ Route-Wise Consumption"])

            with fuel_tab_bus:
                st.markdown("**Bus-Wise Fuel Consumption Breakdown**")
                bus_fuel = (
                    df.groupby("bus_id")["fuel_consumption"]
                    .agg(Total_Fuel_L="sum", Mean_Fuel_per_Stop="mean", Stops_Recorded="count")
                    .reset_index()
                )
                bus_fuel["Total_Fuel_L"] = bus_fuel["Total_Fuel_L"].round(2)
                bus_fuel["Mean_Fuel_per_Stop"] = bus_fuel["Mean_Fuel_per_Stop"].round(3)
                bus_fuel.columns = ["Bus ID", "Total Fuel (L)", "Avg Fuel / Stop (L)", "Stop Events"]
                st.dataframe(bus_fuel, hide_index=True, use_container_width=True)

            with fuel_tab_route:
                st.markdown("**Route-Wise Fuel Consumption Breakdown**")
                route_fuel = (
                    df.groupby("route_id")["fuel_consumption"]
                    .agg(Total_Fuel_L="sum", Mean_Fuel_per_Stop="mean", Stops_Recorded="count")
                    .reset_index()
                )
                route_fuel["Total_Fuel_L"] = route_fuel["Total_Fuel_L"].round(2)
                route_fuel["Mean_Fuel_per_Stop"] = route_fuel["Mean_Fuel_per_Stop"].round(3)
                route_fuel.columns = ["Route ID", "Total Fuel (L)", "Avg Fuel / Stop (L)", "Stop Events"]
                st.dataframe(route_fuel, hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — OVERCROWDING ALERT SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

with tab2:

    st.markdown("""
    <div class="data-badge" style="background:#fdecea;border-color:#e74c3c;color:#922b21;">
        ⚠️ DEMONSTRATION MODE — Alerts generated from historical dataset, NOT live sensor readings
    </div>
    """, unsafe_allow_html=True)

    # ── Sub-filters (alerts-only) ─────────────────────────────────────────────
    st.markdown('<div class="section-title">🔔 Alert Filters</div>', unsafe_allow_html=True)

    af1, af2, af3 = st.columns(3)
    sel_sev = af1.multiselect(
        "Severity", ALL_SEVERITIES, default=[SEVERITY_WARNING, SEVERITY_CRITICAL],
        help="Filter displayed alerts by severity level",
        key="t2_sev",
    )
    sel_alert_buses = af2.multiselect(
        "Bus ID(s) (alerts)", sorted({a.bus_id for a in filtered_alerts}),
        default=[], key="t2_alert_bus",
        help="Leave blank to show all buses",
    )
    show_normal_in_panel = af3.toggle(
        "Include Normal status in active panel", value=False, key="t2_show_normal"
    )

    # Apply alert-specific filters
    view_alerts = filter_alerts(
        filtered_alerts,
        bus_ids    = sel_alert_buses or None,
        severities = sel_sev or None,
    )

    # ── Alert KPI Row ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">🚨 Alert Summary</div>', unsafe_allow_html=True)

    asummary = get_alert_summary(filtered_alerts)   # full (unfiltered by sev) for overview
    a1, a2, a3, a4, a5, a6 = st.columns(6)

    def alert_kpi(col, label, value, sub, variant=""):
        col.markdown(f"""
        <div class="kpi-card {variant}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

    alert_kpi(a1, "Total Events",     asummary["total_alerts"],            "deduplicated")
    alert_kpi(a2, "Critical Events",  asummary["critical_count"],          "100% full",    "kpi-critical")
    alert_kpi(a3, "Warning Events",   asummary["warning_count"],           "85–99%",       "kpi-warning")
    alert_kpi(a4, "Normal Events",    asummary["normal_count"],            "< 85%",        "kpi-ok")
    alert_kpi(a5, "Buses w/ Critical",asummary["buses_affected_critical"], "buses",        "kpi-critical")
    alert_kpi(a6, "Buses w/ Warning", asummary["buses_affected_warning"],  "buses",        "kpi-warning")

    st.markdown("<br>", unsafe_allow_html=True)
    mc1, mc2 = st.columns(2)
    mc1.info(f"🏆 Most Alerted Bus: **{asummary['most_alerted_bus']}**")
    mc2.info(f"🗺️ Most Alerted Route: **{asummary['most_alerted_route']}**")
    st.markdown("---")

    # ── Active Alert Panel ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">🔴 Active Alert Panel (Latest Status per Bus)</div>', unsafe_allow_html=True)
    st.caption("Shows the most recent alert event for each bus — ⚠️ historical data demonstration")

    active_alerts = get_active_alerts(filtered_alerts)
    if not show_normal_in_panel:
        active_alerts = [a for a in active_alerts if a.severity != SEVERITY_NORMAL]

    if not active_alerts:
        st.success("✅ No active Warning or Critical alerts for the current filter selection.")
    else:
        # Sort: Critical first, then Warning, then Normal
        sev_order = {SEVERITY_CRITICAL: 0, SEVERITY_WARNING: 1, SEVERITY_NORMAL: 2}
        active_alerts = sorted(active_alerts, key=lambda a: sev_order.get(a.severity, 3))

        # Display as cards in a 2-column grid
        cols = st.columns(2)
        for i, alert in enumerate(active_alerts):
            with cols[i % 2]:
                sev    = alert.severity
                bg     = ALERT_BG_COLORS[sev]
                txt    = ALERT_TEXT_COLORS[sev]
                border = ALERT_COLORS[sev]
                icon   = ALERT_ICONS[sev]
                emoji  = ALERT_EMOJI[sev]
                occ_bar = min(int(alert.occupancy_pct), 100)

                st.markdown(f"""
                <div class="alert-card alert-card-{sev.lower()}" style="border-left-color:{border};">
                    <div class="alert-bus">{icon} {alert.bus_id}
                        <span style="float:right; background:{bg}; color:{txt};
                              border-radius:12px; padding:2px 10px; font-size:0.78rem; font-weight:700;">
                            {emoji} {sev}
                        </span>
                    </div>
                    <div class="alert-detail">
                        Route: <b>{alert.route_id}</b> &nbsp;|&nbsp;
                        Stop: <b>{alert.stop_id}</b> &nbsp;|&nbsp;
                        Trip: <b>{alert.trip_id}</b>
                    </div>
                    <div class="alert-detail">
                        Passengers: <b>{alert.passengers}/{alert.capacity}</b>
                        &nbsp;|&nbsp; Occupancy: <b>{alert.occupancy_pct:.1f}%</b>
                        &nbsp;|&nbsp; {alert.day_type.title()}
                        {"&nbsp;· Peak" if alert.peak_hour else ""}
                    </div>
                    <div class="alert-detail">
                        🕐 {str(alert.timestamp)[:16]}
                    </div>
                    <div class="alert-note">💬 {alert.note}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Gauge Meters (Critical buses) ─────────────────────────────────────────
    critical_active = [a for a in active_alerts if a.severity == SEVERITY_CRITICAL]
    if critical_active:
        st.markdown('<div class="section-title">🌡️ Occupancy Gauges — Critical Buses</div>', unsafe_allow_html=True)
        st.caption("Latest recorded occupancy for buses currently at 100% capacity")
        gcols = st.columns(min(len(critical_active), 4))
        for i, alert in enumerate(critical_active[:4]):
            with gcols[i]:
                st.plotly_chart(
                    build_occupancy_gauge(alert.bus_id, alert.occupancy_pct,
                                         alert.passengers, alert.capacity),
                    use_container_width=True,
                )
        st.markdown("---")

    # ── Alert History Table ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📜 Alert History Log</div>', unsafe_allow_html=True)
    st.caption(f"Showing {len(view_alerts)} deduplicated alert events for the current filter  |  ⚠️ Historical data")

    if view_alerts:
        alert_df = alerts_to_dataframe(view_alerts)
        alert_df_display = alert_df[[
            "timestamp","bus_id","route_id","stop_id","trip_id",
            "passengers","capacity","occupancy_pct","severity","day_type","peak_hour","note","source",
        ]].copy()
        alert_df_display["timestamp"]  = alert_df_display["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
        alert_df_display["peak_hour"]  = alert_df_display["peak_hour"].map({1:"✅ Peak",0:"Off-Peak"})
        alert_df_display["severity"]   = alert_df_display["severity"].apply(
            lambda s: f"{ALERT_EMOJI.get(s,'')} {s}"
        )
        alert_df_display = alert_df_display.rename(columns={
            "timestamp":"Time","bus_id":"Bus","route_id":"Route","stop_id":"Stop",
            "trip_id":"Trip","passengers":"Pax","capacity":"Cap",
            "occupancy_pct":"Occ. %","severity":"Severity","day_type":"Day",
            "peak_hour":"Time Type","note":"Note","source":"Source",
        })
        alert_rows = st.slider(
            "Rows to display", 10, min(500, len(alert_df_display)), 50, step=10, key="t2_rows"
        )
        st.dataframe(
            alert_df_display.sort_values("Time", ascending=False).head(alert_rows),
            use_container_width=True, hide_index=True,
            column_config={
                "Occ. %": st.column_config.ProgressColumn(
                    "Occ. %", min_value=0, max_value=110, format="%.1f%%"
                ),
            },
        )
    else:
        st.info("No alert events match the current filters.")

    st.markdown("---")

    # ── Charts ─────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📊 Alert Analytics</div>', unsafe_allow_html=True)

    ch1, ch2 = st.columns([1.1, 1])
    with ch1:
        st.plotly_chart(
            build_alert_severity_chart(view_alerts if view_alerts else filtered_alerts),
            use_container_width=True,
        )
    with ch2:
        st.plotly_chart(
            build_alert_heatmap_by_route(filtered_alerts),
            use_container_width=True,
        )

    st.plotly_chart(
        build_alert_timeline_chart(view_alerts if view_alerts else filtered_alerts),
        use_container_width=True,
    )

    # ── Deduplication Explained ────────────────────────────────────────────────
    with st.expander("ℹ️ How Alert Deduplication Works", expanded=False):
        st.markdown("""
        **Rule:** Within each *(Trip ID, Bus ID)* journey, an alert is generated only when
        the occupancy **severity changes** compared to the previous stop.

        **Example:** If `KA-BUS-011` is at Warning for stops S04, S05, S06, S07 on Trip 42:
        - ✅ ONE Warning alert is generated at S04 (first occurrence of that severity)
        - ❌ NO duplicate alerts at S05, S06, S07 (same severity — suppressed)
        - 🔴 If it hits Critical at S08 → ONE new Critical alert is generated

        **Why this matters:** Without deduplication, a bus stuck at 100% capacity for
        8 consecutive stops would flood the dashboard with 8 identical Critical alerts.
        With deduplication, it produces exactly 1 Critical alert per escalation event.

        **Transition notes** are automatically generated to describe each change:
        - *"Trip start — status: Normal."*
        - *"ESCALATED to CRITICAL from Warning. Bus is full."*
        - *"Returned to NORMAL from Critical."*
        """)

    # ── Integration Slots ─────────────────────────────────────────────────────
    with st.expander("🔌 Future Integration Slots (Ready in overcrowding_alerts.py)", expanded=False):
        st.markdown("""
        | Slot | Purpose | Function in `overcrowding_alerts.py` |
        |------|---------|--------------------------------------|
        | `[SLOT IR]` | IR Sensor triggers | `trigger_sensor_alert()` |
        | `[SLOT CAM]` | Camera CV model triggers | `trigger_camera_alert()` |
        | `[SLOT FB]` | Firebase Realtime DB push | `push_alert_to_firebase()` |
        | `[SLOT GPS]` | Attach GPS coordinates to alerts | Inside `generate_alerts()` |
        | `[SLOT NOTIF]` | SMS / push notification dispatch | `dispatch_notification()` (add when ready) |

        All stubs are already present in `overcrowding_alerts.py` with
        clear `# TODO:` comments marking exactly where to connect each system.
        """)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 3 — LIVE BUS TRACKING (GPS)
# ══════════════════════════════════════════════════════════════════════════════

with tab3:

    # ── Simulation notice ────────────────────────────────────────────────
    st.markdown("""
    <div class="data-badge" style="background:#e3f2fd;border-color:#1565c0;color:#0d47a1;">
        🛰️ SIMULATED GPS DATA — NOT CONNECTED TO REAL HARDWARE
    </div>
    """, unsafe_allow_html=True)

    # ── Load route coordinates (static, cached) ──────────────────────────
    @st.cache_data(show_spinner=False)
    def cached_route_coords():
        return load_route_coordinates()

    route_coords_df = cached_route_coords()

    # ── Generate simulated GPS readings ──────────────────────────────────
    rc1, rc2 = st.columns([4, 1])
    rc1.caption("Positions update every ~2 minutes  |  🛰️ Simulated GPS — not real hardware")
    if rc2.button("🔄 Refresh GPS Positions", key="t3_refresh", use_container_width=True):
        st.rerun()

    all_gps = simulate_gps_positions(route_coords=route_coords_df)

    # ── GPS-specific filters ─────────────────────────────────────────────
    st.markdown('<div class="section-title">🔧 GPS Filters</div>', unsafe_allow_html=True)

    gf1, gf2, gf3 = st.columns(3)
    gps_all_routes = sorted({r.route_id for r in all_gps})
    gps_all_buses  = sorted({r.bus_id for r in all_gps})

    sel_gps_routes  = gf1.multiselect("Route(s)", gps_all_routes, default=gps_all_routes, key="t3_routes")
    sel_gps_buses   = gf2.multiselect("Bus ID(s)", gps_all_buses,  default=gps_all_buses,  key="t3_buses")
    sel_gps_status  = gf3.multiselect("GPS Status", ALL_GPS_STATUSES, default=ALL_GPS_STATUSES, key="t3_status")

    gps_filtered = filter_gps_readings(
        all_gps,
        bus_ids   = sel_gps_buses  or None,
        route_ids = sel_gps_routes or None,
        statuses  = sel_gps_status  or None,
    )

    if not gps_filtered:
        st.warning("⚠️ No buses match the current GPS filters. Adjust the filters above.")
    else:

        # ── GPS status legend ────────────────────────────────────────────
        st.markdown(
            '<span class="gps-pill" style="background:#d4edda;color:#155724;">'
            '🟢 Recent (≤ 2 min)</span>'
            '<span class="gps-pill" style="background:#fff3cd;color:#856404;">'
            '🟠 Delayed (2–5 min)</span>'
            '<span class="gps-pill" style="background:#f8d7da;color:#721c24;">'
            '🔴 Stale (&gt; 5 min)</span>'
            '<span class="gps-pill" style="background:#e9ecef;color:#495057;">'
            '⚫ Signal Lost</span>',
            unsafe_allow_html=True,
        )

        # ── KPI summary ──────────────────────────────────────────────────
        st.markdown('<div class="section-title">📊 GPS Fleet Summary</div>', unsafe_allow_html=True)
        gsummary = get_gps_summary(gps_filtered)

        g1, g2, g3, g4, g5, g6 = st.columns(6)

        def gps_kpi(col, label, value, sub="", variant=""):
            col.markdown(f"""
            <div class="kpi-card {variant}">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)

        gps_kpi(g1, "Buses Tracked",  gsummary["total_buses"],   "filtered")
        gps_kpi(g2, "Recent",         gsummary["recent_count"],  "🟢 ≤ 2 min",  "kpi-ok")
        gps_kpi(g3, "Delayed",        gsummary["delayed_count"], "🟠 2–5 min", "kpi-warning")
        gps_kpi(g4, "Stale",          gsummary["stale_count"],   "🔴 > 5 min", "kpi-critical")
        gps_kpi(g5, "Signal Lost",    gsummary["lost_count"],    "⚫ no GPS")
        gps_kpi(g6, "Avg Speed",      f"{gsummary['avg_speed_kmh']}", "km/h")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("---")

        # ── Interactive map ───────────────────────────────────────────────
        st.markdown('<div class="section-title">🗺️ Live Bus Tracking Map</div>', unsafe_allow_html=True)
        st.caption("🛰️ Simulated GPS data — marker colour indicates GPS freshness")
        st.plotly_chart(
            build_gps_map(gps_filtered, route_coords=route_coords_df),
            use_container_width=True,
        )
        st.markdown("---")

        # ── Bus GPS details table ────────────────────────────────────────
        st.markdown('<div class="section-title">📋 Bus GPS Details</div>', unsafe_allow_html=True)
        st.caption("All buses shown — including those with signal loss (coordinates show N/A)")

        gps_df = readings_to_dataframe(gps_filtered)
        gps_df_display = gps_df.copy()
        gps_df_display["timestamp"] = gps_df_display["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        gps_df_display["latitude"] = gps_df_display["latitude"].apply(
            lambda x: f"{x:.6f}" if pd.notna(x) else "N/A"
        )
        gps_df_display["longitude"] = gps_df_display["longitude"].apply(
            lambda x: f"{x:.6f}" if pd.notna(x) else "N/A"
        )
        gps_df_display["gps_status"] = gps_df_display["gps_status"].apply(
            lambda s: f"{GPS_STATUS_EMOJI.get(s, '')} {s}"
        )
        gps_df_display = gps_df_display.rename(columns={
            "bus_id": "Bus ID", "route_id": "Route", "latitude": "Latitude",
            "longitude": "Longitude", "speed_kmh": "Speed (km/h)",
            "heading_deg": "Heading (°)", "timestamp": "Last Updated",
            "gps_status": "GPS Status", "nearest_stop": "Nearest Stop",
            "source": "Source",
        })
        st.dataframe(gps_df_display, use_container_width=True, hide_index=True)
        st.markdown("---")

        # ── Selected bus detail view ─────────────────────────────────────
        st.markdown('<div class="section-title">🔍 Bus Detail View</div>', unsafe_allow_html=True)

        detail_buses = sorted({r.bus_id for r in gps_filtered})
        sel_detail_bus = st.selectbox(
            "Select a bus to view details", detail_buses, key="t3_detail_bus"
        )
        selected = next(r for r in gps_filtered if r.bus_id == sel_detail_bus)

        lat_str = f"{selected.latitude:.6f}" if selected.latitude is not None else "N/A"
        lon_str = f"{selected.longitude:.6f}" if selected.longitude is not None else "N/A"
        status_emoji = GPS_STATUS_EMOJI.get(selected.gps_status, "")
        status_color = GPS_STATUS_COLORS.get(selected.gps_status, "#333")

        dc1, dc2, dc3 = st.columns(3)
        dc1.markdown(f"""
        <div class="gps-detail-card">
            <div class="gps-detail-label">Bus ID</div>
            <div class="gps-detail-value">{selected.bus_id}</div>
            <div class="gps-detail-label" style="margin-top:8px;">Route ID</div>
            <div class="gps-detail-value">{selected.route_id}</div>
        </div>""", unsafe_allow_html=True)

        dc2.markdown(f"""
        <div class="gps-detail-card">
            <div class="gps-detail-label">Speed</div>
            <div class="gps-detail-value">{selected.speed_kmh:.1f} km/h</div>
            <div class="gps-detail-label" style="margin-top:8px;">Heading</div>
            <div class="gps-detail-value">{selected.heading_deg:.0f}°</div>
        </div>""", unsafe_allow_html=True)

        dc3.markdown(f"""
        <div class="gps-detail-card">
            <div class="gps-detail-label">GPS Status</div>
            <div class="gps-detail-value" style="color:{status_color};">
                {status_emoji} {selected.gps_status}
            </div>
            <div class="gps-detail-label" style="margin-top:8px;">Last Updated</div>
            <div class="gps-detail-value">{str(selected.timestamp)[:19]}</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        dc4, dc5 = st.columns(2)
        dc4.markdown(f"""
        <div class="gps-detail-card">
            <div class="gps-detail-label">Current Location</div>
            <div class="gps-detail-value" style="font-size:0.95rem;">
                Lat: {lat_str}<br>Lon: {lon_str}
            </div>
        </div>""", unsafe_allow_html=True)

        dc5.markdown(f"""
        <div class="gps-detail-card">
            <div class="gps-detail-label">Nearest Stop</div>
            <div class="gps-detail-value">{selected.nearest_stop}</div>
            <div class="gps-detail-label" style="margin-top:8px;">Data Source</div>
            <div class="gps-detail-value" style="font-size:0.85rem;">{selected.source}</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # ── Future hardware readiness ────────────────────────────────────
        with st.expander("🔌 Future Hardware Integration", expanded=False):
            st.markdown("""
            **Current:** Simulated GPS positions generated deterministically along
            predefined route paths. GPS data input is kept separate from tracking
            logic and dashboard display.

            **Designed for replacement with real hardware:**
            | Slot | Purpose | Function in `gps_tracking.py` |
            |------|---------|-------------------------------|
            | `[SLOT GPS-HW]` | Hardware GPS module | `ingest_hardware_gps()` |
            | `[SLOT GPS-FB]` | Firebase RTDB push | `push_gps_to_firebase()` |
            | `[SLOT GPS-WS]` | WebSocket streaming | (future) |
            | `[SLOT GPS-GF]` | Geofence engine | (future) |

            The simulation can be replaced with a real GPS receiver by feeding
            readings through `ingest_hardware_gps()` — no dashboard changes needed.
            """)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 4 — PASSENGER COUNTING (YOLO & BYTETRACK)
# ══════════════════════════════════════════════════════════════════════════════

with tab4:

    st.markdown("""
    <div class="data-badge" style="background:#f3e5f5;border-color:#7b1fa2;color:#4a148c;">
        📷 MODULE 4 — Computer Vision Passenger Counting (YOLOv8 + ByteTrack)
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">⚙️ Video Session & Configuration</div>', unsafe_allow_html=True)

    vc1, vc2, vc3 = st.columns(3)
    sel_pc_bus = vc1.selectbox("Bus ID for Video Session", all_buses, index=0, key="pc_bus_id")
    sel_pc_capacity = vc2.number_input("Bus Seating Capacity", min_value=10, max_value=120, value=60, step=5, key="pc_capacity")
    sel_initial_occ = vc3.number_input("Starting Occupancy", min_value=0, max_value=int(sel_pc_capacity), value=20, step=1, key="pc_initial_occ")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("##### 📏 Virtual Counting Gate Settings")
    lg1, lg2, lg3 = st.columns(3)

    line_orient_choice = lg1.selectbox(
        "Gate Orientation",
        ["Horizontal (Top / Bottom Crossing)", "Vertical (Left / Right Crossing)"],
        key="pc_line_orient",
    )
    line_pos_pct = lg2.slider(
        "Gate Position (% of Frame)",
        min_value=10,
        max_value=90,
        value=50,
        step=5,
        format="%d%%",
        key="pc_line_pos",
    )

    if "Horizontal" in line_orient_choice:
        dir_options = {
            "Top to Bottom is BOARDING (Downward = Enter, Upward = Exit)": DirectionConfig.TOP_TO_BOTTOM_IS_BOARDING,
            "Bottom to Top is BOARDING (Upward = Enter, Downward = Exit)": DirectionConfig.BOTTOM_TO_TOP_IS_BOARDING,
        }
        active_orient = LineOrientation.HORIZONTAL
    else:
        dir_options = {
            "Left to Right is BOARDING (Rightward = Enter, Leftward = Exit)": DirectionConfig.LEFT_TO_RIGHT_IS_BOARDING,
            "Right to Left is BOARDING (Leftward = Enter, Rightward = Exit)": DirectionConfig.RIGHT_TO_LEFT_IS_BOARDING,
        }
        active_orient = LineOrientation.VERTICAL

    dir_label = lg3.selectbox("Crossing Direction Semantics", list(dir_options.keys()), key="pc_dir_choice")
    active_dir_config = dir_options[dir_label]

    st.markdown("---")

    # ── Video Source Upload or Sample Selection ─────────────────────────────
    st.markdown('<div class="section-title">🎬 Video Input Source</div>', unsafe_allow_html=True)

    import os
    import tempfile
    import cv2
    import numpy as np

    sample_dir = os.path.join(".", "sample_videos")
    available_samples = []
    if os.path.exists(sample_dir):
        available_samples = [f for f in os.listdir(sample_dir) if f.lower().endswith((".mp4", ".avi", ".mov", ".mkv"))]

    input_mode = st.radio(
        "Choose video source:",
        ["Upload Video File (MP4, AVI)", "Select from sample_videos/ folder"],
        horizontal=True,
        key="pc_input_mode",
    )

    video_path_to_process = None
    source_display_name = ""

    if input_mode == "Upload Video File (MP4, AVI)":
        uploaded_file = st.file_uploader("Upload Bus Entry/Exit Video", type=["mp4", "avi", "mov", "mkv"], key="pc_uploader")
        if uploaded_file is not None:
            tfile = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{uploaded_file.name}")
            tfile.write(uploaded_file.read())
            tfile.flush()
            tfile.close()
            video_path_to_process = tfile.name
            source_display_name = uploaded_file.name
    else:
        if available_samples:
            selected_sample = st.selectbox("Select a sample video:", available_samples, key="pc_sample_select")
            video_path_to_process = os.path.join(sample_dir, selected_sample)
            source_display_name = selected_sample
        else:
            st.info("ℹ️ No video files currently found in `sample_videos/`. Upload a video above or drop an `.mp4`/`.avi` into `sample_videos/`.")

    st.markdown("---")

    # ── Video Processing & Live Metrics ─────────────────────────────────────
    if video_path_to_process is not None:
        st.markdown(f"**Selected Video:** `{source_display_name}`")

        max_frames_to_run = st.slider(
            "Max frames to process (preview mode)",
            min_value=30,
            max_value=600,
            value=180,
            step=30,
            key="pc_max_frames",
            help="Limits processing duration for fast interactive feedback.",
        )

        run_btn = st.button("🚀 Process Video with YOLOv8 & ByteTrack", key="pc_run_btn", type="primary")

        if run_btn:
            v_line = VirtualLine(
                orientation=active_orient,
                position_pct=line_pos_pct / 100.0,
                direction_config=active_dir_config,
                buffer_zone_px=5,
            )

            counter = EntryExitCounter(v_line)
            integrator = OccupancyIntegrator(
                bus_id=sel_pc_bus,
                bus_capacity=int(sel_pc_capacity),
            )
            integrator.set_initial_occupancy(int(sel_initial_occ))

            # Initialize tracker
            with st.spinner("Initializing YOLOv8n & ByteTrack tracker..."):
                try:
                    tracker = ByteTrackTracker(model_path="yolov8n.pt")
                except Exception as e:
                    st.error(f"Failed to initialize YOLO model: {e}")
                    tracker = None

            if tracker is not None:
                cap = cv2.VideoCapture(video_path_to_process)
                if not cap.isOpened():
                    st.error("Error: Could not open video file. Verify codec/format.")
                else:
                    total_cap_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

                    progress_bar = st.progress(0, text="Processing frames...")
                    video_placeholder = st.empty()
                    metrics_placeholder = st.empty()

                    frame_idx = 0
                    last_summary = None
                    last_occ_res = None

                    while cap.isOpened() and frame_idx < max_frames_to_run:
                        ret, frame = cap.read()
                        if not ret or frame is None:
                            break

                        frame_idx += 1
                        timestamp_sec = frame_idx / fps

                        # Run ByteTrack
                        tracks = tracker.update(frame)

                        # Update EntryExitCounter
                        summary = counter.update(
                            current_tracks=tracks,
                            frame_width=frame.shape[1],
                            frame_height=frame.shape[0],
                            frame_idx=frame_idx,
                            timestamp_sec=timestamp_sec,
                        )
                        last_summary = summary

                        # Update Occupancy
                        occ_res = integrator.update(
                            boarding=counter.boarding_count,
                            alighting=counter.alighting_count,
                            previous_occupancy=int(sel_initial_occ),
                        )
                        last_occ_res = occ_res

                        # Render annotated frame with tracks & gate
                        annotated_frame = tracker.draw_tracks(frame, tracks, draw_trajectories=True)
                        annotated_frame = counter.draw_overlay(annotated_frame, tracks, show_trajectories=False)

                        # Convert BGR to RGB for Streamlit display
                        rgb_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
                        video_placeholder.image(rgb_frame, channels="RGB", use_container_width=True)

                        # Render live metrics
                        status_color = "#2e7d32" if occ_res.alert_severity == "Normal" else ("#e65100" if occ_res.alert_severity == "Warning" else "#c62828")
                        metrics_placeholder.markdown(f"""
                        <div style="display:flex; justify-content:space-between; background:#f8f9fa; padding:12px 18px; border-radius:10px; border:1px solid #dee2e6; margin-top:8px;">
                            <div style="text-align:center;">
                                <div style="font-size:0.75rem; color:#6c757d; font-weight:700;">FRAME DETECTIONS</div>
                                <div style="font-size:1.4rem; font-weight:800; color:#1a237e;">{summary.current_frame_detections} 👤</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="font-size:0.75rem; color:#6c757d; font-weight:700;">UNIQUE TRACKED</div>
                                <div style="font-size:1.4rem; font-weight:800; color:#0288d1;">{summary.unique_tracked_ids}</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="font-size:0.75rem; color:#6c757d; font-weight:700;">TOTAL BOARDED</div>
                                <div style="font-size:1.4rem; font-weight:800; color:#2e7d32;">+{summary.total_boarding}</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="font-size:0.75rem; color:#6c757d; font-weight:700;">TOTAL ALIGHTED</div>
                                <div style="font-size:1.4rem; font-weight:800; color:#c62828;">-{summary.total_alighting}</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="font-size:0.75rem; color:#6c757d; font-weight:700;">NET CHANGE</div>
                                <div style="font-size:1.4rem; font-weight:800; color:#1565c0;">{summary.net_change:+d}</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="font-size:0.75rem; color:#6c757d; font-weight:700;">UPDATED OCCUPANCY</div>
                                <div style="font-size:1.4rem; font-weight:800; color:{status_color};">{occ_res.new_occupancy} / {occ_res.bus_capacity} ({occ_res.occupancy_pct}%)</div>
                            </div>
                            <div style="text-align:center;">
                                <div style="font-size:0.75rem; color:#6c757d; font-weight:700;">STATUS</div>
                                <div style="font-size:1.2rem; font-weight:800; color:{status_color};">{occ_res.alert_severity.upper()}</div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                        progress_bar.progress(min(1.0, frame_idx / max_frames_to_run), text=f"Processed {frame_idx}/{max_frames_to_run} frames")

                    cap.release()
                    st.success(f"✅ Video processing finished: {frame_idx} frames evaluated successfully.")

                    if last_occ_res is not None and last_occ_res.is_capacity_exceeded:
                        st.error(f"🚨 OVERCROWDING ALERT: Bus {sel_pc_bus} reached maximum capacity ({last_occ_res.raw_calculated_occupancy} passengers calculated).")
                    elif last_occ_res is not None and last_occ_res.alert_severity == "Warning":
                        st.warning(f"⚠️ HIGH OCCUPANCY WARNING: Bus {sel_pc_bus} is at {last_occ_res.occupancy_pct}% capacity.")
    else:
        st.info("👆 Upload an MP4 or AVI video above to test the passenger counting pipeline.")

        # Synthetic Demonstration Simulator
        with st.expander("🧪 Test with Built-in Synthetic Crossing Simulator (No Video Needed)", expanded=True):
            st.markdown("""
            Since real bus CCTV videos may not always be available, use this interactive simulator
            to test line crossing, duplicate-count prevention, and occupancy updates instantly.
            """)

            sim_c1, sim_c2, sim_c3 = st.columns(3)
            sim_board = sim_c1.number_input("Simulate Passengers Boarding (+)", min_value=0, max_value=50, value=6, step=1, key="sim_board")
            sim_alight = sim_c2.number_input("Simulate Passengers Alighting (-)", min_value=0, max_value=50, value=2, step=1, key="sim_alight")
            sim_prev = sim_c3.number_input("Simulated Starting Occupancy", min_value=0, max_value=int(sel_pc_capacity), value=int(sel_initial_occ), step=1, key="sim_prev")

            if st.button("⚡ Calculate Simulated Occupancy", key="sim_calc_btn"):
                integrator_sim = OccupancyIntegrator(bus_id=sel_pc_bus, bus_capacity=int(sel_pc_capacity))
                sim_res = integrator_sim.update(
                    boarding=sim_board,
                    alighting=sim_alight,
                    previous_occupancy=sim_prev,
                )

                st.markdown(f"### Calculation Result for {sel_pc_bus}")
                sc1, sc2, sc3, sc4 = st.columns(4)

                status_color = "#2e7d32" if sim_res.alert_severity == "Normal" else ("#e65100" if sim_res.alert_severity == "Warning" else "#c62828")
                sc1.metric("Previous Occupancy", f"{sim_res.previous_occupancy} pax")
                sc2.metric("Net Change", f"{sim_res.net_change:+d} pax", f"+{sim_res.boarding} / -{sim_res.alighting}")
                sc3.metric("New Occupancy", f"{sim_res.new_occupancy} / {sim_res.bus_capacity}", f"{sim_res.occupancy_pct}%")
                sc4.metric("Alert Status", sim_res.alert_severity)

                if sim_res.is_capacity_exceeded:
                    st.error(f"🚨 CRITICAL WARNING: Bus capacity exceeded! Calculated {sim_res.raw_calculated_occupancy} > {sim_res.bus_capacity} capacity.")
                elif sim_res.alert_severity == "Warning":
                    st.warning(f"⚠️ OVERCROWDING WARNING: Occupancy at {sim_res.occupancy_pct}% (Threshold: {PC_THRESHOLD_WARNING}%).")
                else:
                    st.success(f"🟢 Normal operating conditions ({sim_res.occupancy_pct}% occupancy).")

                if sim_res.validation_notes:
                    for note in sim_res.validation_notes:
                        st.info(f"ℹ️ {note}")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 5 — OCCUPANCY PREDICTION & CROWDING FORECAST (MODULE 5)
# ══════════════════════════════════════════════════════════════════════════════

with tab5:

    st.markdown("""
    <div class="data-badge" style="background:#e8eaf6;border-color:#3f51b5;color:#1a237e;">
        🔮 MODULE 5 — Future Occupancy Prediction & Early Warning Forecast (Random Forest Regressor)
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">⚙️ Bus Selection & Forecast Parameters</div>', unsafe_allow_html=True)

    fc1, fc2, fc3, fc4 = st.columns(4)

    # Bus selector
    pred_bus_id = fc1.selectbox("Select Bus ID", all_buses, index=0, key="t5_bus_id")

    # Determine assigned route from historical telemetry
    bus_route_match = df_full[df_full["bus_id"] == pred_bus_id]["route_id"].mode()
    default_route_idx = 0
    if not bus_route_match.empty and bus_route_match.iloc[0] in all_routes:
        default_route_idx = all_routes.index(bus_route_match.iloc[0])

    pred_route_id = fc2.selectbox("Select Route ID", all_routes, index=default_route_idx, key="t5_route_id")

    # Bus capacity input
    pred_capacity = fc3.number_input("Bus Capacity", min_value=15, max_value=120, value=60, step=5, key="t5_capacity")

    # Latest historical occupancy lookup as smart default
    latest_bus_rec = df_full[df_full["bus_id"] == pred_bus_id].sort_values("timestamp").iloc[-1] if not df_full[df_full["bus_id"] == pred_bus_id].empty else None
    default_occ_val = int(latest_bus_rec["current_occupancy"]) if latest_bus_rec is not None else 20

    pred_curr_occ = fc4.number_input(
        "Current Bus Occupancy",
        min_value=0,
        max_value=int(pred_capacity),
        value=min(int(pred_capacity), default_occ_val),
        step=1,
        key="t5_curr_occ",
    )

    # Available stops for this route
    route_ordered_stops = HistoricalStopProfile.get_upcoming_stops_for_route(pred_route_id)
    if not route_ordered_stops:
        route_ordered_stops = sorted(df_full[df_full["route_id"] == pred_route_id]["stop_id"].unique())

    sc1, sc2 = st.columns([2, 1])
    sel_start_stop = sc1.selectbox(
        "Current / Starting Stop Location",
        route_ordered_stops,
        index=0,
        key="t5_start_stop",
    )
    stops_horizon_count = sc2.slider(
        "Forecast Horizon (Stops Ahead)",
        min_value=2,
        max_value=len(route_ordered_stops),
        value=min(6, len(route_ordered_stops)),
        step=1,
        key="t5_horizon_slider",
    )

    # Compute upcoming stop slice
    start_stop_idx = route_ordered_stops.index(sel_start_stop) if sel_start_stop in route_ordered_stops else 0
    eval_stops = route_ordered_stops[start_stop_idx : start_stop_idx + stops_horizon_count]

    st.markdown("---")

    # ── Execute Forecast Engine ──────────────────────────────────────────────
    forecaster = CrowdingForecaster()
    forecast_result = forecaster.forecast_upcoming_occupancy(
        bus_id=pred_bus_id,
        current_occupancy=int(pred_curr_occ),
        bus_capacity=int(pred_capacity),
        route_id=pred_route_id,
        upcoming_stops=eval_stops,
    )

    # ── Status & KPI Summary ─────────────────────────────────────────────────
    st.markdown('<div class="section-title">📊 Occupancy Status & Warning Horizon</div>', unsafe_allow_html=True)

    status_var = "kpi-ok" if forecast_result.forecast_condition == "Normal" else ("kpi-warning" if forecast_result.forecast_condition == "Warning" else "kpi-critical")

    k1, k2, k3, k4, k5 = st.columns(5)
    def pred_kpi(col, label, value, sub="", variant=""):
        col.markdown(f"""
        <div class="kpi-card {variant}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

    pred_kpi(k1, "Current Occupancy", f"{forecast_result.current_occupancy} / {forecast_result.bus_capacity}", f"{forecast_result.current_occupancy_pct}% ({forecast_result.current_status})")
    pred_kpi(k2, "Forecast Condition", forecast_result.forecast_condition.upper(), f"Over {forecast_result.total_stops_evaluated} upcoming stops", status_var)
    pred_kpi(k3, "Peak Predicted Occ", f"{forecast_result.max_predicted_occupancy} pax", f"{forecast_result.max_predicted_occupancy_pct}% capacity", status_var)

    first_warn_display = f"{forecast_result.first_warning_stop}" if forecast_result.first_warning_stop else "None"
    warn_sub = f"in {forecast_result.stops_until_warning} stops" if forecast_result.stops_until_warning else "No warning ahead"
    pred_kpi(k4, "First Warning Stop", first_warn_display, warn_sub, "kpi-warning" if forecast_result.first_warning_stop else "kpi-ok")

    first_crit_display = f"{forecast_result.first_critical_stop}" if forecast_result.first_critical_stop else "None"
    crit_sub = f"in {forecast_result.stops_until_critical} stops" if forecast_result.stops_until_critical else "No critical ahead"
    pred_kpi(k5, "First Critical Stop", first_crit_display, crit_sub, "kpi-critical" if forecast_result.first_critical_stop else "kpi-ok")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Early Warning Notice Callouts ────────────────────────────────────────
    notice = forecast_result.early_warning

    if notice.level == "CRITICAL":
        st.error(f"### {notice.headline}\n**Authority Advisory:** {notice.authority_action_message}\n\n**Passenger Advice:** {notice.passenger_advice_message}")
    elif notice.level == "WARNING":
        st.warning(f"### {notice.headline}\n**Authority Advisory:** {notice.authority_action_message}\n\n**Passenger Advice:** {notice.passenger_advice_message}")
    else:
        st.success(f"### {notice.headline}\n**Authority Advisory:** {notice.authority_action_message}\n\n**Passenger Advice:** {notice.passenger_advice_message}")

    st.markdown("---")

    # ── Plotly Forecast Chart ────────────────────────────────────────────────
    st.markdown('<div class="section-title">📈 Predicted Occupancy Trajectory</div>', unsafe_allow_html=True)
    st.caption("Visualizing passenger load progression along upcoming stops with capacity thresholds")

    # Chart data prep
    chart_stops = ["Current Stop"] + [s["stop_id"] for s in forecast_result.stop_forecasts]
    chart_occupancies = [forecast_result.current_occupancy] + [s["predicted_occupancy"] for s in forecast_result.stop_forecasts]
    chart_pcts = [forecast_result.current_occupancy_pct] + [s["predicted_occupancy_pct"] for s in forecast_result.stop_forecasts]

    fig_forecast = go.Figure()

    # Capacity line (100%)
    fig_forecast.add_hline(
        y=forecast_result.bus_capacity,
        line_dash="dash",
        line_color="#c62828",
        annotation_text=f"Full Capacity ({forecast_result.bus_capacity} pax)",
        annotation_position="top left",
        annotation_font_color="#c62828",
    )

    # Warning threshold line (85%)
    warn_pax_val = forecast_result.bus_capacity * 0.85
    fig_forecast.add_hline(
        y=warn_pax_val,
        line_dash="dot",
        line_color="#e65100",
        annotation_text=f"Warning Threshold 85% ({warn_pax_val:.0f} pax)",
        annotation_position="bottom left",
        annotation_font_color="#e65100",
    )

    # Main predicted line
    fig_forecast.add_trace(go.Scatter(
        x=chart_stops,
        y=chart_occupancies,
        mode="lines+markers+text",
        name="Predicted Occupancy",
        line=dict(color="#1a237e", width=3),
        marker=dict(
            size=10,
            color=["#1565c0" if p < 85 else ("#e65100" if p < 100 else "#c62828") for p in chart_pcts],
        ),
        text=[f"{occ} pax ({pct}%)" for occ, pct in zip(chart_occupancies, chart_pcts)],
        textposition="top center",
        hovertemplate="<b>%{x}</b><br>Occupancy: %{y} pax<extra></extra>",
    ))

    fig_forecast.update_layout(
        title=f"Occupancy Forecast Trajectory for Bus {pred_bus_id} on {pred_route_id}",
        xaxis_title="Upcoming Stops",
        yaxis_title="Passengers",
        yaxis=dict(range=[0, max(forecast_result.bus_capacity + 8, max(chart_occupancies) + 5)]),
        template="plotly_white",
        height=380,
        margin=dict(l=40, r=40, t=50, b=40),
    )
    st.plotly_chart(fig_forecast, use_container_width=True)

    st.markdown("---")

    # ── Multi-Stop Prediction Table ──────────────────────────────────────────
    st.markdown('<div class="section-title">📋 Multi-Stop Prediction Details</div>', unsafe_allow_html=True)
    st.caption("ℹ️ Boarding and Alighting values are derived from historical route averages (`HISTORICAL_ESTIMATES_ML`).")

    table_records = []
    for s in forecast_result.stop_forecasts:
        status_symbol = "🟢" if s["predicted_status"] == "Normal" else ("🟡" if s["predicted_status"] == "Warning" else "🔴")
        table_records.append({
            "Seq": s["sequence_index"],
            "Stop ID": s["stop_id"],
            "Starting Occupancy": s["starting_occupancy"],
            "+ Est. Boarding": s["estimated_boarding"],
            "- Est. Alighting": s["estimated_alighting"],
            "Net Change": f"{s['estimated_boarding'] - s['estimated_alighting']:+d}",
            "Predicted Occupancy": s["predicted_occupancy"],
            "Capacity": pred_capacity,
            "Predicted Occ. %": s["predicted_occupancy_pct"],
            "Crowd Status": f"{status_symbol} {s['predicted_status']}",
            "Data Source": "Historical Average + ML Model",
        })

    df_table = pd.DataFrame(table_records)
    st.dataframe(
        df_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Predicted Occ. %": st.column_config.ProgressColumn(
                "Predicted Occ. %",
                min_value=0,
                max_value=100,
                format="%.1f%%",
            ),
            "Predicted Occupancy": st.column_config.NumberColumn(
                "Predicted Occupancy",
                format="%d 👤",
            ),
        },
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Verified ML Evaluation Metrics Expander ──────────────────────────────
    with st.expander("📊 Verified Model Evaluation Metrics (20% Holdout Test Set)", expanded=False):
        st.markdown("""
        The Random Forest prediction model was evaluated on a verified 20% holdout test set (401 unseen records)
        split from `data/bus_occupancy.csv`.
        """)

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Mean Absolute Error (MAE)", "2.25 pax", "Average error per stop")
        mc2.metric("Root Mean Squared Error", "3.19 pax", "Penalizes large errors")
        mc3.metric("R² Score (Variance Explained)", "0.961", "96.1% variance captured")
        mc4.metric("Test Holdout Size", "401 records", "20% test partition")

        st.info("ℹ️ **Validation Note:** Features used: `current_occupancy`, `boarding`, `alighting`, `previous_occupancy`, `peak_hour`, `day_type`, `route_id`, and `stop_order`.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB 6 — SCHEDULING & FLEET OPTIMIZATION (MODULE 6)
# ══════════════════════════════════════════════════════════════════════════════

with tab6:

    st.markdown("""
    <div class="data-badge" style="background:#e0f2f1;border-color:#00897b;color:#004d40;">
        ⚡ MODULE 6 — Intelligent Bus Scheduling, Headway Optimization & Dispatch Interventions
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    > ⚠️ **Operational Notice:** All scheduling intervals, timetable departure slots, and dispatch notices displayed below are **DATA-DRIVEN ADVISORY RECOMMENDATIONS** derived from historical telemetry and Module 5 predictions. No real-world physical vehicle movement or schedule modification is performed without transport controller approval.
    """)

    # Instantiate Module 6 Engines
    demand_analyzer = RouteDemandAnalyzer()
    headway_optimizer = HeadwayOptimizer(demand_analyzer=demand_analyzer)
    dispatch_advisor = DispatchAdvisor(demand_analyzer=demand_analyzer, headway_optimizer=headway_optimizer)

    # Global Controls for Module 6
    st.markdown('<div class="section-title">⚙️ Operational Route & Fleet Parameters</div>', unsafe_allow_html=True)
    s_c1, s_c2, s_c3, s_c4 = st.columns(4)
    sel_sched_route = s_c1.selectbox("Select Route ID", all_routes, index=0, key="m6_route")
    sel_sched_day = s_c2.selectbox("Operating Schedule Type", ["Weekday", "Weekend"], index=0, key="m6_day_type")
    sel_sched_cap = s_c3.number_input("Bus Seating Capacity", min_value=20, max_value=120, value=60, step=5, key="m6_cap")
    sel_sched_fleet = s_c4.number_input("Available Route Fleet (Buses)", min_value=1, max_value=15, value=6, step=1, key="m6_fleet")

    st.markdown("---")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 1: ROUTE DEMAND ANALYSIS
    # ──────────────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📊 1. Route Demand & Capacity Vulnerability Analysis</div>', unsafe_allow_html=True)

    route_summaries = demand_analyzer.get_route_demand_summary()
    sel_prof = route_summaries.get(sel_sched_route)

    # 4 Key Demand KPIs
    dk1, dk2, dk3, dk4 = st.columns(4)
    if sel_prof:
        tier_color = "#c62828" if sel_prof.demand_tier == "HIGH_DEMAND" else "#f57f17"
        dk1.metric("Demand Classification", sel_prof.demand_tier.replace("_", " "), f"Tier: {sel_prof.demand_tier}")
        dk2.metric("Mean Passenger Load", f"{sel_prof.average_occupancy:.1f} pax", f"{sel_prof.average_occupancy_pct:.1f}% capacity")
        dk3.metric("Warning Runs (≥85%)", f"{sel_prof.warning_occurrences} runs", f"{sel_prof.warning_rate_pct:.1f}% frequency")
        dk4.metric("Critical Runs (100%)", f"{sel_prof.critical_occurrences} runs", f"{sel_prof.critical_rate_pct:.1f}% full capacity")

    # Route Comparison Table
    st.markdown("**Fleet-Wide Route Demand Comparison Table**")
    comp_rows = []
    for r_k, prof_k in route_summaries.items():
        comp_rows.append({
            "Route ID": r_k,
            "Demand Level": prof_k.demand_tier.replace("_", " "),
            "Total Boardings": f"{prof_k.total_boarding_demand:,} pax",
            "Avg Occupancy": f"{prof_k.average_occupancy:.1f} pax ({prof_k.average_occupancy_pct:.1f}%)",
            "Max Occupancy": f"{prof_k.max_occupancy} pax",
            "Warning Overcrowding Runs": f"{prof_k.warning_occurrences} ({prof_k.warning_rate_pct:.1f}%)",
            "Critical Runs (100%)": f"{prof_k.critical_occurrences} ({prof_k.critical_rate_pct:.1f}%)",
            "Peak Window": prof_k.peak_demand_period,
        })
    st.dataframe(pd.DataFrame(comp_rows), hide_index=True, use_container_width=True)

    st.markdown("---")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 2: OPTIMIZED TIMETABLE & HEADWAY RECOMMENDATION
    # ──────────────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">⏱️ 2. Demand-Responsive Headway & Optimized Timetable</div>', unsafe_allow_html=True)

    # Compute optimized timetable
    opt_timetable = headway_optimizer.generate_optimized_timetable(
        route_id=sel_sched_route,
        day_type=sel_sched_day.lower(),
        bus_capacity=int(sel_sched_cap),
        fleet_available=int(sel_sched_fleet),
    )

    tk1, tk2, tk3, tk4 = st.columns(4)
    tk1.metric("Morning Peak Headway", f"{opt_timetable.morning_peak_headway_min} min", "Baseline: 15 min")
    tk2.metric("Evening Peak Headway", f"{opt_timetable.evening_peak_headway_min} min", "Baseline: 15 min")
    tk3.metric("Off-Peak Headway", f"{opt_timetable.off_peak_headway_min} min", "Baseline: 20 min")
    tk4.metric("Daily Departures", f"{opt_timetable.total_departures} departures", f"{opt_timetable.service_increase_pct:+0.1f}% vs baseline (57)")

    # Rationale & Fleet Constraints
    with st.expander("ℹ️ Period Rationale & Operational Fleet Constraints", expanded=True):
        for rec_p in opt_timetable.period_recommendations:
            badge_icon = "🔴" if rec_p.fleet_constraint_active else "🟢"
            st.markdown(f"- **{rec_p.period_label}**: Headway **{rec_p.suggested_headway_min} min** ({rec_p.headway_delta_min:+d}m). Required Buses: **{rec_p.buses_required}**. {badge_icon} *{rec_p.rationale}*")

    # Chronological Departure Timetable Viewer
    st.markdown(f"**Suggested Timetable for {sel_sched_route} ({sel_sched_day})** — *06:00 to 22:00 (Total: {opt_timetable.total_departures} departures)*")
    tt_display = []
    for slot in opt_timetable.departures:
        tt_display.append({
            "Departure Time": slot.departure_time,
            "Operating Period": slot.period_name.replace("_", " "),
            "Interval (Headway)": f"{slot.headway_from_previous_min} min" if slot.headway_from_previous_min > 0 else "First Departure",
            "Bus Rotation": f"Bus Unit #{slot.bus_index_in_rotation}",
            "Demand Level": slot.forecasted_demand_level,
            "Advisory Note": slot.notes,
        })
    st.dataframe(pd.DataFrame(tt_display), hide_index=True, use_container_width=True, height=260)

    st.markdown("---")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 3: DISPATCH INTERVENTIONS & RELIEF BUS RECOMMENDATIONS
    # ──────────────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">🚨 3. Dispatch Interventions & Relief Bus Advisories</div>', unsafe_allow_html=True)

    # Active Bus Selector for targeted dispatch assessment
    da_c1, da_c2, da_c3 = st.columns(3)
    target_bus = da_c1.selectbox("Evaluate Bus ID", all_buses, index=0, key="m6_eval_bus")
    sim_curr_occ = da_c2.number_input("Current Live / Estimated Occupancy", min_value=0, max_value=int(sel_sched_cap), value=int(sel_sched_cap), step=1, key="m6_curr_occ")
    sim_spare_buses = da_c3.number_input("Standby Depot Spare Buses Available", min_value=0, max_value=5, value=1, step=1, key="m6_spares")

    # Construct depot state and evaluate
    depot_state = FleetDepotState(
        route_id=sel_sched_route,
        total_assigned_buses=int(sel_sched_fleet),
        active_in_service_buses=max(1, int(sel_sched_fleet) - int(sim_spare_buses)),
        spare_standby_buses=int(sim_spare_buses),
    )

    interv_rec = dispatch_advisor.evaluate_dispatch_need(
        route_id=sel_sched_route,
        bus_id=target_bus,
        current_occupancy=int(sim_curr_occ),
        bus_capacity=int(sel_sched_cap),
        predicted_occupancy=min(int(sel_sched_cap), int(sim_curr_occ) + 2),
        fleet_depot_state=depot_state,
    )

    # Highlight Callout for Intervention
    p_color = "#d32f2f" if interv_rec.priority == DispatchPriority.CRITICAL else ("#f57c00" if interv_rec.priority == DispatchPriority.HIGH else "#388e3c")
    st.markdown(f"""
    <div style="border-left: 5px solid {p_color}; background: #fafafa; padding: 12px 16px; border-radius: 4px; margin-bottom: 12px;">
        <span style="font-size: 1rem; font-weight: 700; color: {p_color};">[{interv_rec.priority.value} PRIORITY] {interv_rec.intervention_id}</span><br>
        <span style="font-size: 0.92rem; color: #37474f;"><b>Recommended Action:</b> {interv_rec.recommended_action}</span><br>
        <span style="font-size: 0.82rem; color: #78909c;">Depot Fleet: {interv_rec.spare_buses_available} spare(s) available &nbsp;|&nbsp; Relief Recommended: {'YES' if interv_rec.is_relief_bus_recommended else 'NO'} &nbsp;|&nbsp; Status: <b>{interv_rec.status.value}</b></span>
    </div>
    """, unsafe_allow_html=True)

    # Simulated Authority Decision & Recovery Monitoring
    st.markdown("**Authority Decision & Empirical Recovery Tracking**")
    dec_c1, dec_c2, dec_c3 = st.columns([1.5, 1.5, 2])
    
    if dec_c1.button("✅ Approve Relief Dispatch", key="btn_approve_relief"):
        dispatch_advisor.record_authority_decision(interv_rec.intervention_id, approved=True)
        st.success(f"Intervention {interv_rec.intervention_id} marked as APPROVED by Authority.")

    if dec_c2.button("❌ Reject / Cancel", key="btn_reject_relief"):
        dispatch_advisor.record_authority_decision(interv_rec.intervention_id, approved=False)
        st.warning(f"Intervention {interv_rec.intervention_id} marked as REJECTED.")

    post_occ_sim = dec_c3.number_input("Subsequent Occupancy Reading (Post-Intervention)", min_value=0, max_value=int(sel_sched_cap), value=32, step=1, key="m6_post_occ")
    if st.button("📥 Record Subsequent Telemetry & Check Recovery", key="btn_record_recovery"):
        updated_rec = dispatch_advisor.record_recovery_reading(interv_rec.intervention_id, post_occupancy=int(post_occ_sim))
        if updated_rec.recovery_confirmed:
            st.success(f"🎉 Recovery Verified! Occupancy reduced by {updated_rec.occupancy_reduction_pct}% (from {updated_rec.pre_intervention_occupancy} to {updated_rec.post_intervention_occupancy} pax). Status: {updated_rec.status.value}")
        else:
            st.info(f"Subsequent reading recorded: {updated_rec.post_intervention_occupancy} pax. Loading change: {updated_rec.occupancy_reduction_pct}%. Status: {updated_rec.status.value}")


# ──────────────────────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("""
---
<div style='text-align:center; color:#adb5bd; font-size:0.76rem; padding:8px 0'>
    🚌 Smart Public Transport Occupancy and Fleet Monitoring System &nbsp;|&nbsp;
    Module 1: Occupancy &nbsp;·&nbsp; Module 2: Overcrowding &nbsp;·&nbsp; Module 3: GPS &nbsp;·&nbsp; Module 4: Passenger Counting &nbsp;·&nbsp; Module 5: Prediction &nbsp;·&nbsp; Module 6: Scheduling & Fleet Optimization &nbsp;|&nbsp;
    <b>Historical Dataset & Simulated Telemetry — Not Live Hardware Sensor Data</b> &nbsp;|&nbsp;
    v6.0
</div>
""", unsafe_allow_html=True)
