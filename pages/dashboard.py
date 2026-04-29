import os
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from ui.header import render_page_header
from core.activity_logger import log_activity
from core.database import test_redis_connection, DB_HOST, fetch_df
from core.video_processor import test_ollama_connection, OLLAMA_BASE_URL
from ai_engine.risk_engine import run_risk_cycle
from core.comm_service import test_smtp_connection


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
    st.markdown(
        """
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
    """,
        unsafe_allow_html=True,
    )

    # Use a more compact layout for the title and metrics
    render_page_header("📊 Dashboard")

    # --- 1. METRICS ROW ---
    st.markdown("#### Key Performance Indicators")
    col1, col2, col3, col4 = st.columns(4)

    try:
        total_regions = conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0]
        total_stations = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
        total_employees = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role IN ('Employee', 'Gas Station Supervisor', 'Gas Station Manager', 'Region Manager', 'Region Director', 'General Manager')"
        ).fetchone()[
            0
        ]  # Count users who are considered employees
        # Wrap in COALESCE/IFNULL to prevent NoneType errors
        pending_tasks = (
            conn.execute(
                "SELECT COUNT(id) FROM submissions WHERE processed = 0"
            ).fetchone()[0]
            or 0
        )

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
        conn.rollback()
        st.warning(f"Metrics partially unavailable: {e}")

    st.divider()

    # --- 2. REGIONAL STATUS TABLE (Existing Dashboard Element) ---
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
        df_reg_status["Status"] = df_reg_status["Pending"].apply(get_status_emoji)

        st.dataframe(
            df_reg_status[["Status", "Region", "Stations", "Pending"]],
            width="stretch",
            hide_index=True,
        )
    except Exception as e:
        conn.rollback()
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
        conn.rollback()
        st.warning(
            "Merchandising analytics unavailable. If you still see a json_extract() error, "
            "restart the Streamlit server so it picks up the PostgreSQL query changes."
        )

    st.divider()

    # --- 3. EXECUTIVE OPERATIONS OVERVIEW (TABS) ---
    st.subheader("🧭 Executive & Risk Overview")

    # Run risk engine to refresh rankings and anomalies
    risk_results = {}
    with st.spinner("Analyzing real-time station risk..."):
        risk_results = run_risk_cycle(conn)

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📍 Operational Map",
            "📊 Risk Ranking",
            "👥 Staff Performance",
            "🚨 Anomaly Feed",
        ]
    )

    with tab1:
        try:
            query_stations = "SELECT id, name, physical_address, lat, lon FROM stations WHERE lat IS NOT NULL"
            df_stats = fetch_df(conn, query_stations)

            if not df_stats.empty:
                m = folium.Map(
                    location=[44.2108, 20.9224], zoom_start=7, tiles="CartoDB positron"
                )

                # Layer 1: Stations with Risk Coloring
                fg_stations = folium.FeatureGroup(name="Stations & Risk")
                for _, s in df_stats.iterrows():
                    risk_data = risk_results.get(s["id"], {})
                    risk_score = risk_data.get("risk", 0)
                    color = (
                        "red"
                        if risk_score >= 70
                        else "orange" if risk_score >= 40 else "green"
                    )

                    folium.Marker(
                        [s["lat"], s["lon"]],
                        popup=f"<b>{s['name']}</b><br>Risk Score: {risk_score}<br>{s['physical_address']}",
                        tooltip=f"{s['name']} (Risk: {risk_score})",
                        icon=folium.Icon(color=color, icon="gas-pump", prefix="fa"),
                    ).add_to(fg_stations)
                fg_stations.add_to(m)

                # Layer 2: Recent Activity (Red Circles)
                fg_activity = folium.FeatureGroup(name="Recent Activity (24h)")
                query_activity = """
                    SELECT s.lat, s.lon, u.name || ' ' || u.surname as emp_name, sub.timestamp, s.name as station
                    FROM submissions sub
                    JOIN stations s ON sub.station_id = s.id
                    JOIN users u ON sub.employee_id = u.id
                    WHERE sub.timestamp >= NOW() - INTERVAL '1 DAY' AND s.lat IS NOT NULL
                    ORDER BY sub.timestamp DESC LIMIT 50
                """
                df_act = fetch_df(conn, query_activity)
                for _, row in df_act.iterrows():
                    folium.CircleMarker(
                        location=[row["lat"], row["lon"]],
                        radius=6,
                        color="red",
                        fill=True,
                        fill_opacity=0.6,
                        popup=f"{row['emp_name']} @ {row['station']}<br>{row['timestamp']}",
                    ).add_to(fg_activity)
                fg_activity.add_to(m)

                folium.LayerControl().add_to(m)
                st_folium(m, width="100%", height=500, key="dashboard_combined_map")
            else:
                st.info("Add coordinates to stations to see them on the map.")
        except Exception as e:
            st.error(f"Map Error: {e}")

    with tab2:
        df_stations = fetch_df(conn, "SELECT id, name, region_id FROM stations")
        ranking_rows = []
        for _, station in df_stations.iterrows():
            sid = station["id"]
            risk_data = risk_results.get(sid, {})
            ranking_rows.append(
                {
                    "Station": station["name"],
                    "Safety Score": risk_data.get("metrics", {}).get(
                        "safety_score", "N/A"
                    ),
                    "Risk Score": round(risk_data.get("risk", 0), 2),
                }
            )
        ranking_df = pd.DataFrame(ranking_rows).sort_values(
            "Risk Score", ascending=False
        )
        st.dataframe(ranking_df, use_container_width=True, hide_index=True)

    with tab3:
        perf_df = fetch_df(
            conn,
            """
            SELECT u.name || ' ' || u.surname as "Employee", s.name as "Station", COUNT(sub.id) as "Total Reports"
            FROM users u
            LEFT JOIN submissions sub ON sub.employee_id = u.id
            LEFT JOIN stations s ON u.station_id = s.id
            GROUP BY u.id, u.name, u.surname, s.name
            ORDER BY "Total Reports" DESC LIMIT 50
        """,
        )
        st.dataframe(perf_df, use_container_width=True, hide_index=True)

    with tab4:
        st.markdown("#### Recent AI Anomaly Alerts")
        try:
            alerts_query = """
                SELECT a.id, a.created_at, s.name as station_name, a.severity, a.message
                FROM ai_alerts a
                JOIN stations s ON a.station_id = s.id
                WHERE a.status IN ('new', 'acknowledged')
                ORDER BY a.created_at DESC LIMIT 10
            """
            alerts_df = fetch_df(conn, alerts_query)
            if alerts_df.empty:
                st.success("✅ No outstanding anomalies detected.")
            else:
                for _, row in alerts_df.iterrows():
                    icon = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "ℹ️"}.get(
                        row["severity"], "ℹ️"
                    )
                    with st.container(border=True):
                        st.markdown(
                            f"**{icon} {row['severity']}** at **{row['station_name']}** ({row['created_at']})"
                        )
                        st.caption(row["message"])
        except Exception as e:
            st.caption(f"Could not load alerts: {e}")
