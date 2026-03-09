import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

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
                margin-top: 0.8rem !important;
                padding-top: 0rem !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # Use a more compact layout for the title and metrics
    st.title("📊 Network Overview")

    # --- 1. METRICS ROW ---
    st.markdown("#### Key Performance Indicators")
    col1, col2, col3, col4 = st.columns(4)
    
    try:
        total_regions = conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0]
        total_stations = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
        total_employees = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        # Wrap in COALESCE/IFNULL to prevent NoneType errors
        pending_tasks = conn.execute("SELECT COUNT(id) FROM submissions WHERE processed = 0").fetchone()[0] or 0

        col1.metric("Total Regions", total_regions)
        col2.metric("Total Stations", total_stations)
        col3.metric("Total Employees", total_employees)
        col4.metric("Pending Tasks", pending_tasks)
    except Exception as e:
        st.warning(f"Metrics partially unavailable: {e}")

    st.divider()

    # --- 2. REGIONAL STATUS TABLE ---
    st.subheader("🌍 Regional Status Overview")
    try:
        query_regions = """
            SELECT r.name as 'Region', COUNT(s.id) as 'Stations',
            COALESCE(SUM((SELECT COUNT(*) FROM submissions WHERE station_id = s.id AND processed = 0)), 0) as 'Pending'
            FROM regions r 
            LEFT JOIN stations s ON r.id = s.region_id 
            GROUP BY r.id
        """
        df_reg_status = pd.read_sql_query(query_regions, conn)
        df_reg_status['Status'] = df_reg_status['Pending'].apply(get_status_emoji)
        
        st.dataframe(
            df_reg_status[['Status', 'Region', 'Stations', 'Pending']], 
            use_container_width=True, 
            hide_index=True
        )
    except Exception as e:
        st.info("Regional table data not yet available.")

    # --- 3. INTERACTIVE MAP ---
    st.subheader("📍 Station Location Map")
    try:
        query_stations = "SELECT name, physical_address, lat, lon FROM stations WHERE lat IS NOT NULL"
        df_stats = pd.read_sql_query(query_stations, conn)

        if not df_stats.empty:
            m = folium.Map(location=[44.2108, 20.9224], zoom_start=7)
            for _, s in df_stats.iterrows():
                folium.Marker(
                    [s['lat'], s['lon']], 
                    popup=f"<b>{s['name']}</b><br>{s['physical_address']}",
                    tooltip=s['name']
                ).add_to(m)
            st_folium(m, width="100%", height=450, key="dashboard_map")
        else:
            st.info("Add coordinates to stations to see them on the map.")
    except Exception as e:
        st.error(f"Map Error: {e}")

    # --- 4. RECENT ACTIVITY PREVIEW ---
    st.divider()
    st.subheader("🕒 Recent System Activity")
    try:
        # NOTE: Updated 'timestamp' to match standard SQL or your log schema
        audit_query = """
            SELECT timestamp as 'Time', user_name as 'User', action as 'Action' 
            FROM activity_logs 
            ORDER BY timestamp DESC LIMIT 5
        """
        df_recent = pd.read_sql_query(audit_query, conn)
        st.table(df_recent)
    except Exception as e:
        st.caption("No recent activity logs found.")