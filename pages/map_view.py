# gentstation_opus/pages/map_view.py
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from ui.header import render_page_header

def get_station_status(conn, station_id):
    """
    Fetches the number of unprocessed submissions for a station and returns a status.
    Returns (status_color, pending_count)
    """
    pending_count = conn.execute(
        "SELECT COUNT(*) FROM submissions WHERE station_id = %s AND processed = 0",
        (station_id,)
    ).fetchone()[0]

    if pending_count >= 3:
        return "red", pending_count
    elif pending_count > 0:
        return "orange", pending_count
    else:
        return "green", pending_count

def render(conn):
    render_page_header("🗺️ Network Status Map")
    st.markdown("Live status of all stations based on pending submissions. 🟢: OK, 🟡: Pending, 🔴: High Volume.")

    try:
        stations_df = pd.read_sql_query(
            "SELECT id, name, lat, lon FROM stations WHERE lat IS NOT NULL AND lon IS NOT NULL",
            conn
        )

        if stations_df.empty:
            st.info("No stations with coordinates found in the database.")
            return

        # Create map without a specific center; we will fit it to the markers' bounds later.
        m = folium.Map(tiles="CartoDB positron")

        # --- Inject CSS for Pulsing Effect ---
        # This defines a keyframe animation and a custom class for the marker
        m.get_root().html.add_child(folium.Element("""
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
        """))

        # --- Fetch Active Stations (Last 1 hour) ---
        active_ids = set()
        try:
            rows = conn.execute("SELECT DISTINCT station_id FROM submissions WHERE timestamp >= NOW() - INTERVAL '1 HOUR'").fetchall()
            active_ids = {r[0] for r in rows}
        except Exception:
            pass

        # --- Layer 0: Recent Activity Pulse ---
        # Added before stations so the text popups of stations appear on top if needed, 
        # though Pulse is visual background usually.
        fg_pulse = folium.FeatureGroup(name="Recent Activity (1h)")
        for _, station in stations_df.iterrows():
            if station['id'] in active_ids:
                folium.Marker(
                    location=[station['lat'], station['lon']],
                    icon=folium.DivIcon(
                        icon_size=(14, 14),
                        icon_anchor=(7, 7), # Center the 14px icon
                        class_name="custom-div-icon",
                        html='<div class="pulse-marker"></div>'
                    ),
                    tooltip="Active: New Submission"
                ).add_to(fg_pulse)
        fg_pulse.add_to(m)

        # --- Layer 1: Station Status ---
        fg_stations = folium.FeatureGroup(name="Station Status")
        for _, station in stations_df.iterrows():
            color, pending = get_station_status(conn, station['id'])
            popup_html = f"<b>{station['name']}</b><br>Status: <b>{color.upper()}</b><br>Pending Reports: {pending}<br><small>(Click marker to edit)</small>"
            
            folium.CircleMarker(
                location=[station['lat'], station['lon']],
                radius=10, color=color, fill=True, fill_color=color, fill_opacity=0.7,
                popup=folium.Popup(popup_html, max_width=200),
                tooltip=f"{station['name']} ({pending} pending)"
            ).add_to(fg_stations)
        
        fg_stations.add_to(m)

        # --- Fit map to bounds of all stations ---
        # This ensures the map is perfectly centered and zoomed on the stations.
        bounds = [
            [stations_df['lat'].min(), stations_df['lon'].min()],
            [stations_df['lat'].max(), stations_df['lon'].max()]
        ]
        m.fit_bounds(bounds, padding=(30, 30))

        # --- Layer 2: High Risk Alerts (AI) ---
        fg_alerts = folium.FeatureGroup(name="⚠️ High Risk Alerts", show=False)
        try:
            # Fetch alerts from the last 7 days
            alerts_df = pd.read_sql_query("""
                SELECT a.message, a.created_at, s.lat, s.lon, s.name
                FROM ai_alerts a
                JOIN stations s ON a.station_id = s.id
                WHERE a.severity = 'HIGH' 
                  AND a.created_at >= NOW() - INTERVAL '7 days'
                  AND s.lat IS NOT NULL
            """, conn)

            for _, row in alerts_df.iterrows():
                folium.Marker(
                    location=[row['lat'], row['lon']],
                    icon=folium.Icon(color='red', icon='exclamation-triangle', prefix='fa'),
                    popup=f"<b>⚠️ ALERT: {row['name']}</b><br>{row['message']}<br><small>{row['created_at']}</small>",
                    tooltip=f"High Risk: {row['name']}"
                ).add_to(fg_alerts)
        except Exception:
            pass # Gracefully skip if table empty or missing
        
        fg_alerts.add_to(m)

        # Add Layer Control to toggle layers
        folium.LayerControl().add_to(m)

        map_data = st_folium(m, width="100%", height=700, returned_objects=["last_object_clicked"])

        # Handle marker click to redirect
        if map_data and map_data.get("last_object_clicked"):
            clicked = map_data["last_object_clicked"]
            # Find the station that matches the clicked coordinates (using small tolerance)
            c_lat, c_lon = clicked['lat'], clicked['lng']
            
            match = stations_df[
                (stations_df['lat'].sub(c_lat).abs() < 0.0001) & 
                (stations_df['lon'].sub(c_lon).abs() < 0.0001)
            ]
            
            if not match.empty:
                s_id = int(match.iloc[0]['id'])
                s_name = match.iloc[0]['name']
                if st.button(f"📝 Go to Details for {s_name}", type="primary"):
                    st.session_state["active_page"] = "Stations"
                    st.session_state["target_station_id"] = s_id
                    st.rerun()

    except Exception as e:
        st.error(f"Failed to load map view: {e}")
