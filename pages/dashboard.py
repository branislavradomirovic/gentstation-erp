import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from ui.header import render_page_header
from core.database import fetch_df, get_schema_readiness
from ai_engine.risk_engine import run_risk_cycle


def _resolve_column(df: pd.DataFrame, *candidates: str):
    if df is None or df.empty:
        return None
    direct = set(df.columns)
    for name in candidates:
        if name in direct:
            return name
    lowered = {str(col).lower(): col for col in df.columns}
    for name in candidates:
        match = lowered.get(str(name).lower())
        if match is not None:
            return match
    return None


def get_status_emoji(unprocessed_count):
    """Visual status based on unprocessed submissions."""
    if unprocessed_count == 0:
        return "🟢"
    elif unprocessed_count < 3:
        return "🟡"
    else:
        return "🔴"


def render(conn):
    render_page_header("📊 Dashboard")
    st.markdown(
        '<div class="gs-page-intro">Track network health, recent AI activity, and risk concentration from one compact operations surface.</div>',
        unsafe_allow_html=True,
    )

    schema_state = get_schema_readiness(conn)
    categories_ready = schema_state["is_ready"]
    if not categories_ready:
        st.warning(
            "Category-aware dashboard features are limited because the Postgres schema is behind the current code."
        )
        for msg in schema_state["blockers"] + schema_state["warnings"]:
            st.caption(msg)

    # --- 1. METRICS ROW ---
    st.markdown("#### Network Snapshot")
    col1, col2, col3, col4 = st.columns(4)

    try:
        total_regions = conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0]
        total_stations = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
        total_employees = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role IN ('Employee', 'Gas Station Supervisor', 'Gas Station Manager', 'Region Manager', 'General Manager')"
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
            st.metric("Open Queue", pending_tasks)
            if st.button("🗺️ View on Map", key="nav_map", width="stretch"):
                st.session_state.active_page = "Map View"
                st.rerun()
    except Exception as e:
        conn.rollback()
        st.warning(f"Metrics partially unavailable: {e}")

    st.divider()

    # --- 2. REGIONAL STATUS TABLE (Existing Dashboard Element) ---
    st.subheader("Regional Status")
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
    st.subheader("Merchandising Performance")
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
            station_col = _resolve_column(df_merch, "Station", "station")
            score_col = _resolve_column(df_merch, "Score", "score")
            if station_col and score_col:
                chart_df = df_merch.rename(
                    columns={station_col: "Station", score_col: "Score"}
                )
                st.bar_chart(chart_df.set_index("Station")[["Score"]])
            else:
                st.info("Merchandising data is available, but expected chart columns were not returned.")
        else:
            st.info("No merchandising data available yet.")
    except Exception as e:
        conn.rollback()
        st.warning(f"Merchandising analytics unavailable: {e}")

    st.divider()

    # --- 3. EXECUTIVE OPERATIONS OVERVIEW (TABS) ---
    st.subheader("Risk & Activity")

    # Run risk engine to refresh rankings and anomalies
    risk_results = {}
    with st.spinner("Analyzing real-time station risk..."):
        risk_results = run_risk_cycle()

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📍 Operational Map",
            "📊 Risk Ranking",
            "👥 Staff Performance",
            "🚨 Anomaly Feed",
        ]
    )

    with tab1:
        if not categories_ready:
            st.info("Operational Map will be available after the station category migration is applied.")
        else:
            try:
                query_stations = """
                    SELECT s.id, s.name, sc.name as category, sc.color, sc.description, s.physical_address, s.lat, s.lon 
                    FROM stations s 
                    LEFT JOIN station_categories sc ON s.category_id = sc.id 
                    WHERE s.lat IS NOT NULL
                """
                df_stats = fetch_df(conn, query_stations)

                if not df_stats.empty:
                    m = folium.Map(
                        location=[44.2108, 20.9224], zoom_start=7, tiles="CartoDB positron"
                    )

                    # Layer 1: Stations with Risk Coloring
                    fg_stations = folium.FeatureGroup(name="Stations & Risk")
                    for _, s in df_stats.iterrows():
                        cat_color = s["color"] or "#808080"
                        cat_desc = s["description"] or ""
                        tooltip_text = f"{s['name']} ({s['category']})" + (f" - {cat_desc}" if cat_desc else "")
                        
                        # Custom HTML Marker
                        marker_html = f'''
                            <div style="
                                background-color: {cat_color};
                                width: 24px;
                                height: 24px;
                                border-radius: 50% 50% 50% 0;
                                transform: rotate(-45deg);
                                border: 2px solid white;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                box-shadow: 0 0 5px rgba(0,0,0,0.3);
                            ">
                                <div style="
                                    width: 6px; 
                                    height: 6px; 
                                    background: white; 
                                    border-radius: 50%;
                                    transform: rotate(45deg);
                                "></div>
                            </div>
                        '''

                        folium.Marker(
                            [s["lat"], s["lon"]],
                            popup=f"<b>{s['name']}</b><br>Type: {s['category']}<br>{s['physical_address']}",
                            tooltip=tooltip_text,
                            icon=folium.DivIcon(icon_size=(24, 24), icon_anchor=(12, 24), html=marker_html)
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
