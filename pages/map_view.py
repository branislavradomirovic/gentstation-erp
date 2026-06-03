# gentstation_opus/pages/map_view.py
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from ui.header import render_page_header
from core.database import get_schema_readiness


def get_station_status(conn, station_id):
    """
    Fetches the number of unprocessed submissions for a station and returns a status.
    Returns (status_color, pending_count)
    """
    pending_count = conn.execute(
        "SELECT COUNT(*) FROM submissions WHERE station_id = %s AND processed = 0",
        (station_id,),
    ).fetchone()[0]

    if pending_count >= 3:
        return "red", pending_count
    elif pending_count > 0:
        return "orange", pending_count
    else:
        return "green", pending_count


def render(conn):
    render_page_header("🗺️ Network Status Map")
    st.markdown(
        '<div class="gs-page-intro">Review station coverage, queued workload, and recent activity geographically. Border color reflects queue pressure while the inner marker color reflects station category.</div>',
        unsafe_allow_html=True,
    )

    schema_state = get_schema_readiness(conn)
    if not schema_state["is_ready"]:
        st.warning(
            "Map View is unavailable because the Postgres schema is behind the current code."
        )
        for msg in schema_state["blockers"] + schema_state["warnings"]:
            st.caption(msg)
        return

    try:
        stations_df = pd.read_sql_query(
            """
            SELECT s.id, s.name, sc.name as category, sc.color, sc.description, s.lat, s.lon
            FROM stations s
            LEFT JOIN station_categories sc ON s.category_id = sc.id
            WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL
            """,
            conn,
        )

        if stations_df.empty:
            st.info("No stations with coordinates found in the database.")
            return

        active_row = conn.execute(
            "SELECT COUNT(DISTINCT station_id) FROM submissions WHERE timestamp >= NOW() - INTERVAL '1 HOUR'"
        ).fetchone()
        high_volume = 0
        pending_total = 0
        for station_id in stations_df["id"].tolist():
            _color, pending = get_station_status(conn, station_id)
            pending_total += pending
            if pending >= 3:
                high_volume += 1

        overview_tab, map_tab = st.tabs(["📊 Overview", "🗺️ Interactive Map"])

        with overview_tab:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Mapped Stations", int(len(stations_df)))
            m2.metric("Active in Last Hour", int(active_row[0] if active_row else 0))
            m3.metric("High-Volume Stations", int(high_volume))
            m4.metric("Pending Reports", int(pending_total))
            st.caption(
                "Use the map tab to inspect queue pressure, recent activity, and high-risk alerts by station."
            )

        # Create map with a reliable default base layer and add optional alternates.
        center_lat = float(stations_df["lat"].mean())
        center_lon = float(stations_df["lon"].mean())
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=7,
            tiles=None,
            control_scale=True,
        )
        folium.TileLayer("OpenStreetMap", name="Standard Map", control=True).add_to(m)
        folium.TileLayer("CartoDB positron", name="Light Map", control=True).add_to(m)

        # --- Inject CSS for Pulsing Effect ---
        # This defines a keyframe animation and a custom class for the marker
        m.get_root().html.add_child(
            folium.Element(
                """
            <style>
                @keyframes pulse {
                    0% { box-shadow: 0 0 0 0 rgba(255, 0, 0, 0.7); }
                    70% { box-shadow: 0 0 0 15px rgba(255, 0, 0, 0); }
                    100% { box-shadow: 0 0 0 0 rgba(255, 0, 0, 0); }
                }
                .pulse-marker {
                    background-color: #ff3333;
                    border-radius: 50%;
                    width: 14px;
                    height: 14px;
                    animation: pulse 1.5s infinite;
                }
                /* Remove default white square from DivIcon */
                .custom-div-icon {
                    background: transparent;
                    border: none;
                }
            </style>
        """
            )
        )

        # --- Build Legend HTML ---
        legend_html = '''
             <div style="position: absolute; bottom: 50px; left: 50px; width: 170px; 
             border:2px solid rgba(0,0,0,0.1); z-index:9999; font-size:12px;
             background-color: rgba(255, 255, 255, 0.9); padding: 10px; border-radius: 8px; 
             box-shadow: 0 0 10px rgba(0,0,0,0.1); font-family: sans-serif;">
             <b style="display:block; margin-bottom: 5px;">Map Legend</b>
             <div style="margin-bottom: 3px;"><span style="color:#28a745; font-size:14px;">●</span> OK (0 pending)</div>
             <div style="margin-bottom: 3px;"><span style="color:#fd7e14; font-size:14px;">●</span> Pending (1-2)</div>
             <div style="margin-bottom: 3px;"><span style="color:#dc3545; font-size:14px;">●</span> High Volume (3+)</div>
             <hr style="margin: 5px 0;">
             <div style="margin-bottom: 3px;"><span style="color:#ff3333; font-size:14px;">○</span> Recent Activity (1h)</div>
             <small style="color: #666; display:block; margin-top: 5px;"><i>Marker inner color represents Category.</i></small>
             </div>
             '''
        m.get_root().html.add_child(folium.Element(legend_html)
        )

        # --- Fetch Active Stations (Last 1 hour) ---
        active_ids = set()
        try:
            rows = conn.execute(
                "SELECT DISTINCT station_id FROM submissions WHERE timestamp >= NOW() - INTERVAL '1 HOUR'"
            ).fetchall()
            active_ids = {r[0] for r in rows}
        except Exception:
            pass

        # --- Layer 0: Recent Activity Pulse ---
        # Added before stations so the text popups of stations appear on top if needed,
        # though Pulse is visual background usually.
        fg_pulse = folium.FeatureGroup(name="Recent Activity (1h)")
        for _, station in stations_df.iterrows():
            if station["id"] in active_ids:
                folium.Marker(
                    location=[station["lat"], station["lon"]],
                    icon=folium.DivIcon(
                        icon_size=(14, 14),
                        icon_anchor=(7, 7),  # Center the 14px icon
                        class_name="custom-div-icon",
                        html='<div class="pulse-marker"></div>',
                    ),
                    tooltip="Active: New Submission",
                ).add_to(fg_pulse)
        fg_pulse.add_to(m)

        # --- Layer 1: Station Status ---
        fg_stations = folium.FeatureGroup(name="Station Status")
        for _, station in stations_df.iterrows():
            color, pending = get_station_status(conn, station["id"])

            cat_color = station.get("color") or "#808080"
            cat_desc = station.get("description") or ""
            tooltip_text = f"{station['name']} ({station['category']}) - {pending} pending" + (f" - {cat_desc}" if cat_desc else "")
            
            # Custom Teardrop Marker
            # The border color reflects the pending status (Green/Orange/Red)
            status_border = "#28a745" if color == "green" else "#fd7e14" if color == "orange" else "#dc3545"
            
            marker_html = f'''
                <div style="
                    background-color: {cat_color};
                    width: 30px;
                    height: 30px;
                    border-radius: 50% 50% 50% 0;
                    transform: rotate(-45deg);
                    border: 3px solid {status_border};
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 0 8px rgba(0,0,0,0.4);
                ">
                    <div style="
                        width: 8px; 
                        height: 8px; 
                        background: white; 
                        border-radius: 50%;
                        transform: rotate(45deg);
                    "></div>
                </div>
            '''

            popup_html = f"<b>{station['name']}</b><br>Type: {station['category']}<br>Pending Reports: {pending}<br><small>(Click marker to edit)</small>"

            folium.Marker(
                location=[station["lat"], station["lon"]],
                popup=folium.Popup(popup_html, max_width=200),
                tooltip=tooltip_text,
                icon=folium.DivIcon(icon_size=(30, 30), icon_anchor=(15, 30), html=marker_html)
            ).add_to(fg_stations)

        fg_stations.add_to(m)

        # --- Fit map to bounds of all stations ---
        # This ensures the map is perfectly centered and zoomed on the stations.
        min_lat = float(stations_df["lat"].min())
        max_lat = float(stations_df["lat"].max())
        min_lon = float(stations_df["lon"].min())
        max_lon = float(stations_df["lon"].max())
        if min_lat == max_lat and min_lon == max_lon:
            m.location = [min_lat, min_lon]
            m.zoom_start = 14
        else:
            bounds = [
                [min_lat, min_lon],
                [max_lat, max_lon],
            ]
            m.fit_bounds(bounds, padding=(30, 30))

        # --- Layer 2: High Risk Alerts (AI) ---
        fg_alerts = folium.FeatureGroup(name="⚠️ High Risk Alerts", show=False)
        try:
            # Fetch alerts from the last 7 days
            alerts_df = pd.read_sql_query(
                """
                SELECT a.message, a.created_at, s.lat, s.lon, s.name
                FROM ai_alerts a
                JOIN stations s ON a.station_id = s.id
                WHERE a.severity = 'HIGH'
                  AND a.created_at >= NOW() - INTERVAL '7 days'
                  AND s.lat IS NOT NULL
            """,
                conn,
            )

            for _, row in alerts_df.iterrows():
                folium.Marker(
                    location=[row["lat"], row["lon"]],
                    icon=folium.Icon(
                        color="red", icon="exclamation-triangle", prefix="fa"
                    ),
                    popup=f"<b>⚠️ ALERT: {row['name']}</b><br>{row['message']}<br><small>{row['created_at']}</small>",
                    tooltip=f"High Risk: {row['name']}",
                ).add_to(fg_alerts)
        except Exception:
            pass  # Gracefully skip if table empty or missing

        fg_alerts.add_to(m)

        # Add Layer Control to toggle layers
        folium.LayerControl().add_to(m)

        with map_tab:
            map_data = st_folium(
                m, width="100%", height=700, returned_objects=["last_object_clicked"]
            )

            # Handle marker click to redirect
            if map_data and map_data.get("last_object_clicked"):
                clicked = map_data["last_object_clicked"]
                # Find the station that matches the clicked coordinates (using small tolerance)
                c_lat, c_lon = clicked["lat"], clicked["lng"]

                match = stations_df[
                    (stations_df["lat"].sub(c_lat).abs() < 0.0001)
                    & (stations_df["lon"].sub(c_lon).abs() < 0.0001)
                ]

                if not match.empty:
                    s_id = int(match.iloc[0]["id"])
                    s_name = match.iloc[0]["name"]
                    if st.button(f"📝 Go to Details for {s_name}", type="primary"):
                        st.session_state["active_page"] = "Stations"
                        st.session_state["target_station_id"] = s_id
                        st.rerun()

    except Exception as e:
        st.error(f"Failed to load map view: {e}")
