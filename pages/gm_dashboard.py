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
from core.database import get_connection
from ui.header import render_page_header
from ai_engine.risk_engine import run_risk_cycle

def render(conn):
    render_page_header("🧭 Executive Dashboard — General Manager")

    # Top KPI row
    st.subheader("Top-level KPIs")
    total_stations = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
    total_alerts = conn.execute("SELECT COUNT(*) FROM ai_alerts WHERE severity='HIGH'").fetchone()[0]
    avg_risk_query = conn.execute("SELECT AVG(json_extract(kpi_json, '$.safety') ) FROM ai_reports WHERE kpi_json IS NOT NULL").fetchone()[0]
    col1, col2, col3 = st.columns(3)
    col1.metric("Stations", total_stations)
    col2.metric("High Alerts (last)", total_alerts)
    col3.metric("Avg Safety (approx)", round(avg_risk_query or 0, 2))

    st.divider()

    # Run risk engine to refresh alerts (careful: this may write ai_alerts)
    if st.button("🔄 Recompute risk now"):
        with st.spinner("Computing risk and anomalies..."):
            results = run_risk_cycle()
            st.success("Risk recomputed.")
    else:
        results = None

    # Station Risk Rankings
    st.subheader("Station Risk Ranking")
    df_risk = pd.read_sql_query("""
        SELECT id, name, region_id, lat, lon FROM stations
    """, conn)
    # Fetch latest risk per station from ai_alerts or ai_reports (we'll compute risk if missing)
    # Join with latest ai_reports.kpi_json to show metrics
    kpis = pd.read_sql_query("""
        SELECT station_id, kpi_json, created_at FROM ai_reports
        WHERE station_id IS NOT NULL
        ORDER BY created_at DESC
    """, conn)
    # build map of station->kpi (latest)
    latest_kpi = {}
    for _, r in kpis.iterrows():
        sid = r['station_id']
        if sid not in latest_kpi:
            try:
                latest_kpi[sid] = json.loads(r['kpi_json']) if r['kpi_json'] else {}
            except:
                latest_kpi[sid] = {}

    ranking_rows = []
    for _, s in df_risk.iterrows():
        sid = s['id']
        metrics = latest_kpi.get(sid, {})
        # simple risk: use safety -> lower safety => higher risk
        safety = metrics.get('safety') or metrics.get('safety_score') or 7
        risk_est = 100 - (safety * 10)
        ranking_rows.append({
            "station_id": sid,
            "station_name": s['name'],
            "region_id": s['region_id'],
            "lat": s['lat'],
            "lon": s['lon'],
            "safety": safety,
            "risk_score": round(risk_est, 2)
        })

    ranking_df = pd.DataFrame(ranking_rows).sort_values("risk_score", ascending=False)
    if ranking_df.empty:
        st.info("No station KPIs yet.")
    else:       
        st.dataframe(ranking_df[['station_id','station_name','region_id','safety','risk_score']], use_container_width=True)

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
    # Naive metric: count of ai_reports per station and average sentiment
    perf_df = pd.read_sql_query("""
        SELECT e.id as employee_id, e.name || ' ' || e.surname as fullname, e.role, e.station_id,
               COUNT(ar.id) as reports_count,
               AVG(ar.sentiment) as avg_sentiment
        FROM employees e
        LEFT JOIN ai_reports ar ON ar.station_id = e.station_id
        GROUP BY e.id
        ORDER BY reports_count DESC
        LIMIT 50
    """, conn)
    if perf_df.empty:
        st.info("No performance data yet.")
    else:
        st.dataframe(perf_df, use_container_width=True)

    st.divider()

    # AI anomaly alerts (recent)
    st.subheader("AI Anomaly Alerts (Recent)")
    alerts = pd.read_sql_query("""
        SELECT a.id, s.name as station, a.severity, a.message, a.created_at
        FROM ai_alerts a
        LEFT JOIN stations s ON s.id = a.station_id
        ORDER BY a.created_at DESC
        LIMIT 50
    """, conn)
    if alerts.empty:
        st.success("No anomalies detected.")
    else:
        for _, a in alerts.iterrows():
            if a['severity'] == "HIGH":
                st.error(f"[{a['created_at']}] {a['station']}: {a['message']}")
            elif a['severity'] == "MEDIUM":
                st.warning(f"[{a['created_at']}] {a['station']}: {a['message']}")
            else:
                st.info(f"[{a['created_at']}] {a['station']}: {a['message']}")