# gentstation_opus/pages/stations.py
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from core.activity_logger import log_activity

def render(conn):
    st.title("⛽ Stations Management")

    # --- DATA PREPARATION ---
    regions = pd.read_sql_query("SELECT id, name FROM regions ORDER BY name", conn)
    regions_map = {row['name']: row['id'] for _, row in regions.iterrows()} if not regions.empty else {}

    mgrs = pd.read_sql_query("""
        SELECT id, name || ' ' || surname as fullname 
        FROM employees 
        WHERE role = 'Gas Station Manager' 
        ORDER BY name
    """, conn)
    mgr_map = {row['fullname']: row['id'] for _, row in mgrs.iterrows()} if not mgrs.empty else {}

   # --- 1. ADD NEW STATION ---
    with st.expander("➕ Add New Station", expanded=False):
        st.write("📍 **Step 1: Select Location on Map**")
        
        # Initialize map centered on the region
        m_create = folium.Map(location=[44.2108, 20.9224], zoom_start=7)
        
        # Show a marker if the user has already clicked on the map
        if "create_lat" in st.session_state and "create_lon" in st.session_state:
            folium.Marker([st.session_state.create_lat, st.session_state.create_lon], 
                          icon=folium.Icon(color='blue', icon='info-sign')).add_to(m_create)

        # Render map and catch clicks
        map_create_data = st_folium(m_create, width="100%", height=300, key="map_create")

        # Update session state with coordinates on click
        if map_create_data.get("last_clicked"):
            st.session_state.create_lat = map_create_data["last_clicked"]["lat"]
            st.session_state.create_lon = map_create_data["last_clicked"]["lng"]
            st.rerun()

        st.write("📝 **Step 2: Station Details**")
        with st.form("add_station_form"):
            s_name = st.text_input("Station Name")
            s_addr = st.text_input("Physical Address")
            s_email = st.text_input("Station Email (optional)")
            region_name = st.selectbox("Region", ["-- None --"] + list(regions_map.keys()))
            mgr_name = st.selectbox("Assign Gas Station Manager", ["-- None --"] + list(mgr_map.keys()))
            
            c1, c2 = st.columns(2)
            # Pre-filled from map click
            lat_val = c1.number_input("Latitude", value=st.session_state.get("create_lat", 0.0), format="%.6f")
            lon_val = c2.number_input("Longitude", value=st.session_state.get("create_lon", 0.0), format="%.6f")

            if st.form_submit_button("Create Station"):
                if not s_name.strip():
                    st.error("Station name is required.")
                else:
                    # Database Insertion
                    region_id = regions_map.get(region_name) if region_name != "-- None --" else None
                    cursor = conn.execute("""
                        INSERT INTO stations (name, region_id, physical_address, email, lat, lon, category)
                        VALUES (?,?,?,?,?,?,?)
                    """, (s_name.strip(), region_id, s_addr.strip() or None, s_email.strip() or None, lat_val, lon_val, "Retail"))
                    new_id = cursor.lastrowid
                    
                    # Link Manager
                    if mgr_name != "-- None --":
                        mgr_id = mgr_map.get(mgr_name)
                        conn.execute("UPDATE employees SET station_id = ? WHERE id = ?", (new_id, mgr_id))
                    
                    conn.commit()
                    
                    # LOGGING AND FEEDBACK
                    log_activity(conn, "CREATE_STATION", f"Created station {s_name} (ID {new_id})")
                    st.success(f"✅ Station '{s_name}' has been successfully created!")
                    st.toast(f"Station {s_name} added to database.", icon="⛽")
                    
                    # Cleanup session and refresh
                    st.session_state.pop("create_lat", None)
                    st.session_state.pop("create_lon", None)
                    st.rerun()
                    st.rerun()

    # --- 2. STATIONS TABLE ---
    df = pd.read_sql_query("""
        SELECT s.id, s.name, r.name as region_name,
               s.physical_address, s.email, s.lat, s.lon,
               (SELECT name || ' ' || surname FROM employees WHERE station_id = s.id AND role = 'Gas Station Manager' LIMIT 1) as manager
        FROM stations s
        LEFT JOIN regions r ON s.region_id = r.id
        ORDER BY s.id
    """, conn)

    st.subheader("Existing Stations")
    if df.empty:
        st.info("No stations available.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

    # --- 3. EDIT / DELETE STATION ---
    st.divider()
    st.subheader("✏️ Edit / Delete Station")
    station_ids = df['id'].tolist() if not df.empty else []
    
    if station_ids:
        sel = st.selectbox("Select Station to Modify", station_ids, 
                           format_func=lambda x: f"ID {x}: {df[df['id']==x]['name'].values[0]}")
        
        # Load existing data for selected station
        curr = pd.read_sql_query("SELECT * FROM stations WHERE id = ?", conn, params=(sel,)).iloc[0]
        
        st.write("📍 **Update Location (Optional)**")
        # Initialize map at current station coordinates
        start_lat = curr['lat'] if curr['lat'] else 44.2108
        start_lon = curr['lon'] if curr['lon'] else 20.9224
        
        m_edit = folium.Map(location=[start_lat, start_lon], zoom_start=12)
        
        # Use session state or database values for marker
        display_lat = st.session_state.get(f"edit_lat_{sel}", start_lat)
        display_lon = st.session_state.get(f"edit_lon_{sel}", start_lon)
        folium.Marker([display_lat, display_lon], tooltip="Target Location", 
                      icon=folium.Icon(color='orange')).add_to(m_edit)

        # Render edit map
        map_edit_data = st_folium(m_edit, width="100%", height=250, key=f"map_edit_{sel}")

        # Update if user clicks a new location
        if map_edit_data.get("last_clicked"):
            st.session_state[f"edit_lat_{sel}"] = map_edit_data["last_clicked"]["lat"]
            st.session_state[f"edit_lon_{sel}"] = map_edit_data["last_clicked"]["lng"]
            st.rerun()

        with st.form(f"edit_station_{sel}"):
            name = st.text_input("Station Name", value=curr['name'])
            addr = st.text_input("Address", value=curr['physical_address'] or "")
            email = st.text_input("Email", value=curr['email'] or "")
            
            # Region Dropdown logic
            region_options = ["-- None --"] + list(regions_map.keys())
            current_region_name = next((k for k,v in regions_map.items() if v == curr['region_id']), "-- None --")
            sel_region = st.selectbox("Region", region_options, index=region_options.index(current_region_name))
            
            # Manager Dropdown logic
            mgr_options = ["-- None --"] + list(mgr_map.keys())
            curr_mgr_name_q = pd.read_sql_query("""
                SELECT name || ' ' || surname as fullname FROM employees 
                WHERE station_id = ? AND role = 'Gas Station Manager' LIMIT 1
            """, conn, params=(sel,))
            curr_mgr_name = curr_mgr_name_q['fullname'].iloc[0] if not curr_mgr_name_q.empty else "-- None --"
            sel_mgr = st.selectbox("Gas Station Manager", mgr_options, 
                                   index=mgr_options.index(curr_mgr_name) if curr_mgr_name in mgr_options else 0)
            
            c3, c4 = st.columns(2)
            u_lat = c3.number_input("Lat", value=float(display_lat), format="%.6f")
            u_lon = c4.number_input("Lon", value=float(display_lon), format="%.6f")

            if st.form_submit_button("Save Station Changes"):
                # Update Database
                region_id = regions_map.get(sel_region) if sel_region != "-- None --" else None
                conn.execute("""
                    UPDATE stations SET name=?, physical_address=?, email=?, region_id=?, lat=?, lon=? 
                    WHERE id=?
                """, (name.strip(), addr.strip() or None, email.strip() or None, region_id, u_lat, u_lon, sel))
                
                # Update Manager link
                conn.execute("UPDATE employees SET station_id = NULL WHERE station_id = ? AND role = 'Gas Station Manager'", (sel,))
                if sel_mgr != "-- None --":
                    mgr_id = mgr_map.get(sel_mgr)
                    conn.execute("UPDATE employees SET station_id = ? WHERE id = ?", (sel, mgr_id))
                
                conn.commit()
                
                # LOGGING AND FEEDBACK
                log_activity(conn, "UPDATE_STATION", f"Updated station ID {sel} ({name})")
                st.success(f"💾 Changes for '{name}' have been saved.")
                st.toast("Update successful!", icon="📝")

                # Clear session state and refresh
                st.session_state.pop(f"edit_lat_{sel}", None)
                st.session_state.pop(f"edit_lon_{sel}", None)
                st.rerun()

        # Separate delete button outside the form for safety
        if st.button("🗑️ Delete Station", type="secondary"):
            try:
                conn.execute("DELETE FROM stations WHERE id = ?", (sel,))
                conn.commit()
                log_activity(conn, "DELETE_STATION", f"Deleted station ID {sel}")
                st.success(f"Station ID {sel} removed.")
                st.toast("Station deleted.", icon="🗑️")
                st.rerun()
            except Exception:
                st.error("Cannot delete station: It has linked records (employees or logs).")