# gentstation_opus/pages/gm_dashboard.py
"""
Executive AI Dashboard (General Manager)
- risk heatmap (folium + streamlit_folium)
- station ranking by risk
- employee performance summary (based on latest reports)
- AI anomaly alerts (from ai_alerts table)
"""

from unicodedata import name

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
from ui.header import render_page_header
from ai_engine.risk_engine import run_risk_cycle

def render(conn):
    render_page_header("🧭 Executive Dashboard — General Manager")

    # Top KPI row
    st.subheader("Top-level KPIs")
    total_stations = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    total_alerts = conn.execute("SELECT COUNT(*) FROM ai_alerts WHERE severity='HIGH' AND status != 'resolved'").fetchone()[0]
    avg_safety_query = conn.execute(
        "SELECT AVG(CAST(data_json->>'safety_score' AS REAL)) FROM submissions WHERE processed = 1 AND data_json IS NOT NULL"
    ).fetchone()[0]
    col1, col2, col3 = st.columns(3)
    col1.metric("Stations", total_stations)
    col2.metric("High-Severity Alerts", total_alerts)
    col3.metric("Avg Safety Score", round(avg_safety_query or 0, 2))

    st.divider()

    # Run risk engine to refresh alerts (careful: this may write ai_alerts)
    risk_results = {}
    with st.spinner("Analyzing station risk..."):
        risk_results = run_risk_cycle()

    # Station Risk Rankings
    st.subheader("Station Risk Ranking")
    df_stations = pd.read_sql_query("SELECT id, name, region_id, lat, lon FROM stations", conn)

    ranking_rows = []
    for _, station in df_stations.iterrows():
        sid = station['id']
        risk_data = risk_results.get(sid)
        
        if risk_data:
            risk_score = risk_data.get('risk', 0)
            safety_score = risk_data.get('metrics', {}).get('safety_score', 'N/A')
        else:
            # Fallback for stations with no reports
            risk_score = 0
            safety_score = 'N/A'
            
        ranking_rows.append({
            "station_id": sid,
            "station_name": station['name'],
            "region_id": station['region_id'],
            "lat": station['lat'],
            "lon": station['lon'],
            "safety": safety_score,
            "risk_score": round(risk_score, 2)
        })

    ranking_df = pd.DataFrame(ranking_rows).sort_values("risk_score", ascending=False)
    if ranking_df.empty:
        st.info("No station data available.")
    else:       
        st.dataframe(ranking_df[['station_id','station_name','region_id','safety','risk_score']], width="stretch", hide_index=True)

    st.divider()

    # Risk Heatmap (markers with color by risk)
    st.subheader("Risk Map")
    if ranking_df.empty:
        st.info("No station locations available.")
    else:
        # Create map instance (auto-centered later via fit_bounds)
        m = folium.Map(tiles="CartoDB positron")
        for _, row in ranking_df.iterrows():
            lat = row['lat'] or 44.8
            lon = row['lon'] or 20.4
            risk = row['risk_score']
            if risk >= 70:
                color = "red"
            elif risk >= 40:
                color = "orange"
            else:
                color = "green"
            folium.CircleMarker(
                location=[lat, lon],
                radius=10,
                color=color,
                fill=True,
                fill_opacity=0.7,
                popup=f"{row['station_name']} (Risk {row['risk_score']})"
            ).add_to(m)
            
        # Auto-focus map on all markers
        lats = ranking_df['lat'].dropna()
        lons = ranking_df['lon'].dropna()
        if not lats.empty and not lons.empty:
            bounds = [[lats.min(), lons.min()], [lats.max(), lons.max()]]
            m.fit_bounds(bounds, padding=(30, 30))
            
        st_folium(m, width="100%", height=450)

    st.divider()

    # Employee performance (derived from ai_reports contributions per station)
    st.subheader("Employee Performance Snapshot")
    # Metric: count of submissions per employee
    perf_df = pd.read_sql_query("""
        SELECT 
            e.id as employee_id, 
            e.name || ' ' || e.surname as fullname, 
            e.role, 
            s.name as station_name,
            COUNT(sub.id) as reports_count
        FROM employees e
        LEFT JOIN submissions sub ON sub.employee_id = e.id
        LEFT JOIN stations s ON e.station_id = s.id
        GROUP BY e.id, e.name, e.surname, e.role, s.name
        ORDER BY reports_count DESC
        LIMIT 50
    """, conn)
    if perf_df.empty:
        st.info("No performance data yet.")
    else:
        st.dataframe(perf_df, width="stretch", hide_index=True)

    st.divider()

    # AI anomaly alerts (recent)
    st.subheader("AI Anomaly Alerts (Recent)")
    alerts = pd.read_sql_query("""
        SELECT a.id, s.name as station, a.severity, a.message, a.created_at, a.status
        FROM ai_alerts a
        LEFT JOIN stations s ON s.id = a.station_id
        WHERE a.status != 'resolved'
        ORDER BY a.created_at DESC
        LIMIT 50
    """, conn)
    if alerts.empty:
        st.success("No unresolved anomalies detected.")
    else:
        for _, a in alerts.iterrows():
            if a['severity'] == "HIGH":
                st.error(f"[{a['created_at']}] **{a['station']}**: {a['message']} (Status: {a['status']})")
            elif a['severity'] == "MEDIUM":
                st.warning(f"[{a['created_at']}] **{a['station']}**: {a['message']} (Status: {a['status']})")
            else:
                st.info(f"[{a['created_at']}] **{a['station']}**: {a['message']} (Status: {a['status']})")
