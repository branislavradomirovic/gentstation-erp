import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from ui.header import render_page_header
from core.activity_logger import log_activity


def fetch_df(conn, query, params=None):
    cur = conn.cursor()
    cur.execute(query, params or ())
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description] if cur.description else []
    return pd.DataFrame(rows, columns=columns)


def get_status_emoji(unprocessed_count):
    """Visual status based on unprocessed submissions."""
    if unprocessed_count == 0:
        return "🟢" 
    elif unprocessed_count < 3:
        return "🟡" 
    else:
        return "🔴"

def render(conn):
   # --- 0. FORCE TOP ALIGNMENT (REMOVES GAP) ---
    st.markdown("""
        <style>
            /* Remove padding from the main container */
            .block-container {
                padding-top: 1rem !important;
                padding-bottom: 0rem !important;
            }
            /* Remove margin from the title to keep it flush */
            h1 {
                margin-top: 1.4rem !important;
                padding-top: 0rem !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # Use a more compact layout for the title and metrics
    render_page_header("📊 Network Overview")

    # --- 1. METRICS ROW ---
    st.markdown("#### Key Performance Indicators")
    col1, col2, col3, col4 = st.columns(4)
    
    try:
        total_regions = conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0]
        total_stations = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
        total_employees = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        # Wrap in COALESCE/IFNULL to prevent NoneType errors
        pending_tasks = conn.execute("SELECT COUNT(id) FROM submissions WHERE processed = 0").fetchone()[0] or 0

        with col1:
            st.metric("Total Regions", total_regions)
            if st.button("📂 Manage Regions", key="nav_regions", width="stretch"):
                st.session_state.active_page = "Regions"
                st.rerun()
        with col2:
            st.metric("Total Stations", total_stations)
            if st.button("⛽ Manage Stations", key="nav_stations", width="stretch"):
                st.session_state.active_page = "Stations"
                st.rerun()
        with col3:
            st.metric("Total Employees", total_employees)
            if st.button("👥 Manage Employees", key="nav_employees", width="stretch"):
                st.session_state.active_page = "Employees"
                st.rerun()
        with col4:
            st.metric("Pending Tasks", pending_tasks)
            if st.button("🗺️ View on Map", key="nav_map", width="stretch"):
                st.session_state.active_page = "Map View"
                st.rerun()
    except Exception as e:
        st.warning(f"Metrics partially unavailable: {e}")

    st.divider()

    # --- 2. REGIONAL STATUS TABLE ---
    st.subheader("🌍 Regional Status Overview")
    try:
        query_regions = """
            SELECT r.name as "Region", COUNT(s.id) as "Stations",
            COALESCE(SUM((SELECT COUNT(*) FROM submissions WHERE station_id = s.id AND processed = 0)), 0) as "Pending"
            FROM regions r 
            LEFT JOIN stations s ON r.id = s.region_id 
            GROUP BY r.id
        """
        df_reg_status = fetch_df(conn, query_regions)
        df_reg_status['Status'] = df_reg_status['Pending'].apply(get_status_emoji)
        
        st.dataframe(
            df_reg_status[['Status', 'Region', 'Stations', 'Pending']], 
            width="stretch", 
            hide_index=True
        )
    except Exception as e:
        st.info("Regional table data not yet available.")

    # --- 2.5 MERCHANDISING INSIGHTS ---
    st.subheader("🛒 Merchandising Performance")
    try:
        query_merch = """
            SELECT 
                st.name as Station, 
                AVG(CAST(s.data_json->>'merchandising_score' AS FLOAT)) as Score
            FROM submissions s
            JOIN stations st ON s.station_id = st.id
            WHERE s.processed = 1 AND s.data_json IS NOT NULL
            GROUP BY st.id
            ORDER BY Score DESC
        """
        df_merch = fetch_df(conn, query_merch)
        if not df_merch.empty:
            st.bar_chart(df_merch.set_index("Station"))
        else:
            st.info("No merchandising data available yet.")
    except Exception as e:
        st.warning(
            "Merchandising analytics unavailable. If you still see a json_extract() error, "
            "restart the Streamlit server so it picks up the PostgreSQL query changes."
        )

    st.divider()

    # --- 3. INTERACTIVE MAP ---
    st.subheader("📍 Station Location Map")
    try:
        query_stations = "SELECT name, physical_address, lat, lon FROM stations WHERE lat IS NOT NULL"
        df_stats = fetch_df(conn, query_stations)

        if not df_stats.empty:
            m = folium.Map(location=[44.2108, 20.9224], zoom_start=7)
            
            # Layer 1: Stations (Blue Markers)
            fg_stations = folium.FeatureGroup(name="Stations")
            for _, s in df_stats.iterrows():
                folium.Marker(
                    [s['lat'], s['lon']], 
                    popup=f"<b>{s['name']}</b><br>{s['physical_address']}",
                    tooltip=s['name'],
                    icon=folium.Icon(color='blue', icon='gas-pump', prefix='fa')
                ).add_to(fg_stations)
            fg_stations.add_to(m)

            # Layer 2: Recent Activity (Red Circles)
            fg_activity = folium.FeatureGroup(name="Recent Activity (24h)")
            query_activity = """
                SELECT s.lat, s.lon, e.name || ' ' || e.surname as emp_name, sub.timestamp, s.name as station
                FROM submissions sub
                JOIN stations s ON sub.station_id = s.id
                JOIN employees e ON sub.employee_id = e.id
                WHERE sub.timestamp >= NOW() - INTERVAL '1 DAY' AND s.lat IS NOT NULL
                ORDER BY sub.timestamp DESC LIMIT 50
            """
            df_act = fetch_df(conn, query_activity)
            for _, row in df_act.iterrows():
                folium.CircleMarker(
                    location=[row['lat'], row['lon']],
                    radius=6, color="red", fill=True, fill_opacity=0.6,
                    popup=f"{row['emp_name']} @ {row['station']}<br>{row['timestamp']}",
                    tooltip="Recent Submission"
                ).add_to(fg_activity)
            fg_activity.add_to(m)

            folium.LayerControl().add_to(m)
            st_folium(m, width="100%", height=450, key="dashboard_map")
        else:
            st.info("Add coordinates to stations to see them on the map.")
    except Exception as e:
        st.error(f"Map Error: {e}")

    # --- 3.5 RECENT UNRESOLVED ALERTS ---
    st.divider()
    st.subheader("🚨 Recent Unresolved Alerts")
    try:
        # Query for new or acknowledged alerts, limit to 5 for the dashboard view
        alerts_query = """
            SELECT a.id, a.created_at, s.name as station_name, a.severity, a.message
            FROM ai_alerts a
            JOIN stations s ON a.station_id = s.id
            WHERE a.status IN ('new', 'acknowledged')
            ORDER BY a.created_at DESC
            LIMIT 5
        """
        alerts_df = fetch_df(conn, alerts_query)

        if alerts_df.empty:
            st.success("✅ No outstanding alerts to display.")
        else:
            for _, row in alerts_df.iterrows():
                icon = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "ℹ️"}.get(row['severity'], "ℹ️")
                
                with st.container(border=True):
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"**{icon} {row['severity']}** at **{row['station_name']}** ({row['created_at']})")
                        st.caption(row['message'])
                    with col2:
                        st.write("") # for vertical alignment
                        if st.button("Resolve", key=f"dash_res_{row['id']}", width="stretch"):
                            conn.execute("UPDATE ai_alerts SET status = 'resolved' WHERE id = ?", (row['id'],))
                            conn.commit()
                            log_activity(conn, "RESOLVE_ALERT", f"Resolved alert ID {row['id']} from dashboard")
                            st.toast(f"Alert {row['id']} resolved!", icon="✅")
                            st.rerun()
    except Exception as e:
        st.caption(f"Could not load alerts: {e}")

    # --- 4. RECENT ACTIVITY PREVIEW ---
    st.divider()
    st.subheader("🕒 Recent System Activity")
    try:
        # NOTE: Updated 'timestamp' to match standard SQL or your log schema
        audit_query = """
            SELECT timestamp as "Time", user_name as "User", action as "Action", ip_address as "IP" 
            FROM activity_logs 
            ORDER BY timestamp DESC LIMIT 5
        """
        df_recent = fetch_df(conn, audit_query)
        st.table(df_recent)
    except Exception as e:
        st.caption("No recent activity logs found.")
