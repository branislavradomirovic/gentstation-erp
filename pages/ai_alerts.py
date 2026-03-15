# gentstation_opus/pages/ai_alerts.py
import streamlit as st
import pandas as pd
from ui.header import render_page_header
from core.activity_logger import log_activity

def render(conn):
    render_page_header("🚨 AI Alerts & Incidents")
    st.markdown("Manage and track AI-detected safety hazards, operational anomalies, and other critical incidents.")

    # --- 1. FILTERS ---
    st.subheader("Filters")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_filter = st.multiselect(
            "Filter by Status",
            options=['new', 'acknowledged', 'resolved'],
            default=['new', 'acknowledged']
        )
    with col2:
        severity_filter = st.multiselect(
            "Filter by Severity",
            options=['HIGH', 'MEDIUM', 'LOW'],
            default=['HIGH', 'MEDIUM']
        )
    with col3:
        stations_df = pd.read_sql_query("SELECT id, name FROM stations ORDER BY name", conn)
        station_map = {row['name']: row['id'] for _, row in stations_df.iterrows()}
        station_filter_names = st.multiselect(
            "Filter by Station",
            options=list(station_map.keys())
        )
        station_filter_ids = [station_map[name] for name in station_filter_names]

    # --- 2. QUERY & DISPLAY ALERTS ---
    query = """
        SELECT a.id, a.created_at, s.name as station_name, a.severity, a.message, a.status
        FROM ai_alerts a
        JOIN stations s ON a.station_id = s.id
        WHERE 1=1
    """
    params = []

    if status_filter:
        query += f" AND a.status IN ({','.join(['?']*len(status_filter))})"
        params.extend(status_filter)
    if severity_filter:
        query += f" AND a.severity IN ({','.join(['?']*len(severity_filter))})"
        params.extend(severity_filter)
    if station_filter_ids:
        query += f" AND a.station_id IN ({','.join(['?']*len(station_filter_ids))})"
        params.extend(station_filter_ids)

    query += " ORDER BY a.created_at DESC LIMIT 500"
    alerts_df = pd.read_sql_query(query, conn, params=params)

    st.divider()
    st.subheader("Alerts Feed")

    if alerts_df.empty:
        st.info("No alerts match the current filters.")
    else:
        for _, row in alerts_df.iterrows():
            icon = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "ℹ️"}.get(row['severity'], "ℹ️")
            st.container(border=True).markdown(f"""
                **{icon} [{row['status'].upper()}]** at **{row['station_name']}**
                
                *Timestamp: {row['created_at']}*
                
                {row['message']}
            """)
            
            b_cols = st.columns(8)
            if row['status'] != 'acknowledged':
                if b_cols[0].button("Acknowledge", key=f"ack_{row['id']}", use_container_width=True):
                    conn.execute("UPDATE ai_alerts SET status = 'acknowledged' WHERE id = ?", (row['id'],))
                    conn.commit()
                    log_activity(conn, "ACK_ALERT", f"Acknowledged alert ID {row['id']}")
                    st.rerun()
            if row['status'] != 'resolved':
                if b_cols[1].button("Resolve", key=f"res_{row['id']}", use_container_width=True):
                    conn.execute("UPDATE ai_alerts SET status = 'resolved' WHERE id = ?", (row['id'],))
                    conn.commit()
                    log_activity(conn, "RESOLVE_ALERT", f"Resolved alert ID {row['id']}")
                    st.rerun()