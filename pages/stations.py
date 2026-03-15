# gentstation_opus/pages/stations.py
import streamlit as st
import sqlite3
import pandas as pd
import folium
from streamlit_folium import st_folium
from core.activity_logger import log_activity
from ui.header import render_page_header
import urllib.parse
import urllib.request

# Import email service
try:
    from core.comm_service import send_station_qr_email
except ImportError:
    def send_station_qr_email(*args): st.error("Email service unavailable")

def render(conn):
    render_page_header("⛽ Stations Management")

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
            clicked_lat = map_create_data["last_clicked"]["lat"]
            clicked_lon = map_create_data["last_clicked"]["lng"]
            if st.session_state.get("create_lat") != clicked_lat or st.session_state.get("create_lon") != clicked_lon:
                st.session_state.create_lat = clicked_lat
                st.session_state.create_lon = clicked_lon
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

    # --- 2.1 TRENDS CHART ---
    st.markdown("### 📊 Daily Submission Trends")
    
    col_trend_filter, _ = st.columns([1, 3])
    with col_trend_filter:
        trend_date = st.date_input("Select Month (pick any day in month)", value=pd.Timestamp.now())
    
    selected_month = trend_date.strftime('%Y-%m')

    try:
        trend_df = pd.read_sql_query("""
            SELECT strftime('%Y-%m-%d', timestamp) as day, COUNT(*) as count
            FROM submissions
            WHERE timestamp IS NOT NULL
              AND strftime('%Y-%m', timestamp) = ?
            GROUP BY day
            ORDER BY day
        """, conn, params=(selected_month,))
        if not trend_df.empty:
            st.bar_chart(trend_df.set_index("day"))
        else:
            st.info(f"No submission data available for {selected_month}.")
    except Exception as e:
        st.error(f"Could not load trends: {e}")

    # --- 2.2 MONTHLY TRENDS CHART ---
    st.markdown("### 📅 Monthly Submission Trends (Last 12 Months)")
    try:
        monthly_df = pd.read_sql_query("""
            SELECT strftime('%Y-%m', timestamp) as month, COUNT(*) as count
            FROM submissions
            WHERE timestamp >= date('now', '-12 months')
            GROUP BY month
            ORDER BY month
        """, conn)
        if not monthly_df.empty:
            st.line_chart(monthly_df.set_index("month"))
        else:
            st.info("No submission data available for the last 12 months.")
    except Exception as e:
        st.error(f"Could not load monthly trends: {e}")

    # --- 3. EDIT / DELETE STATION ---
    st.divider()
    st.subheader("✏️ Edit / Delete Station")
    station_ids = df['id'].tolist() if not df.empty else []
    
    # Handle navigation from Employee Directory (persisting selection)
    sb_key = "station_selector_main"
    if "target_station_id" in st.session_state:
        tgt = st.session_state.pop("target_station_id")
        if tgt in station_ids:
            st.session_state[sb_key] = tgt

    if station_ids:
        sel = st.selectbox("Select Station to Modify", station_ids, key=sb_key,
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
                      icon=folium.Icon(color='red', icon='star', prefix='fa')).add_to(m_edit)

        # Render edit map
        map_edit_data = st_folium(m_edit, width="100%", height=250, key=f"map_edit_{sel}")

        # Update if user clicks a new location
        if map_edit_data.get("last_clicked"):
            e_lat = map_edit_data["last_clicked"]["lat"]
            e_lon = map_edit_data["last_clicked"]["lng"]
            if st.session_state.get(f"edit_lat_{sel}") != e_lat or st.session_state.get(f"edit_lon_{sel}") != e_lon:
                st.session_state[f"edit_lat_{sel}"] = e_lat
                st.session_state[f"edit_lon_{sel}"] = e_lon
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
                if not name.strip():
                    st.error("Station name cannot be empty.")
                else:
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

        st.markdown("---")
        st.subheader("👥 Employees Assigned to this Station")
        assigned_employees_df = pd.read_sql_query(
            "SELECT name, surname, role, email FROM employees WHERE station_id = ?",
            conn,
            params=(sel,)
        )
        if assigned_employees_df.empty:
            st.info("No employees are currently assigned to this station.")
        else:
            st.dataframe(assigned_employees_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("📱 Mobile Access (QR Code)")
        
        # Bot handle (matches core/comm_service.py)
        bot_handle = "BaneTest_Bot"
        bot_link = f"https://t.me/{bot_handle}"
        qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(bot_link)}"
        
        c_qr, c_desc = st.columns([1, 4])
        with c_qr:
            st.image(qr_api_url, width=150)
        with c_desc:
            st.markdown(f"**Bot Link:** [{bot_handle}]({bot_link})")
            st.caption("Distribute this QR code to employees at this station. Scanning it will open the reporting bot in Telegram.")
            
            # Fetch manager email for this station
            mgr_email_row = conn.execute("SELECT email FROM employees WHERE station_id = ? AND role = 'Gas Station Manager'", (sel,)).fetchone()
            mgr_email = mgr_email_row[0] if mgr_email_row else None

            col_dl, col_email = st.columns(2)
            
            try:
                with urllib.request.urlopen(qr_api_url) as response:
                    qr_bytes = response.read()
                    with col_dl:
                        st.download_button("⬇️ Download QR Code", qr_bytes, file_name=f"station_{sel}_qr.png", mime="image/png", use_container_width=True)
            except Exception:
                st.warning("Could not generate download (Internet required).")
            
            with col_email:
                if st.button("📧 Share via Email", disabled=(not mgr_email), help="Send instructions to Station Manager", use_container_width=True):
                    if mgr_email:
                        send_station_qr_email(curr['name'], mgr_email, bot_link, qr_api_url)
                    else:
                        st.error("No manager email found.")

        # Separate delete button outside the form for safety
        if st.button("🗑️ Delete Station", type="secondary"):
            try:
                conn.execute("DELETE FROM stations WHERE id = ?", (sel,))
                conn.commit()
                log_activity(conn, "DELETE_STATION", f"Deleted station ID {sel}")
                st.success(f"Station ID {sel} removed.")
                st.toast("Station deleted.", icon="🗑️")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Cannot delete station: It contains linked records (e.g., employees, history).")
            except Exception as e:
                st.error(f"Error deleting station: {e}")