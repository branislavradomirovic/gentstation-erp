# gentstation_opus/pages/regions.py
import streamlit as st
import pandas as pd
import folium
from psycopg2 import IntegrityError
from sqlalchemy import select, func, or_
from streamlit_folium import st_folium
from core.activity_logger import log_activity
from ui.header import render_page_header
from core.database import get_session
from core.models import Region, Station, User, Submission

def render(conn):
    render_page_header("🌍 Regions Management")

    # --- 0. PERSISTENT STATE ---
    if "selected_region_id" not in st.session_state:
        st.session_state.selected_region_id = None

    # --- 1. DATA PREPARATION (ORM) ---
    with get_session() as session:
        # Global Metrics
        total_regions = session.scalar(select(func.count(Region.id)))
        total_stations = session.scalar(select(func.count(Station.id)))
        total_staff = session.scalar(select(func.count(User.id)).where(or_(User.region_id.isnot(None), User.station_id.isnot(None))))

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Regions", total_regions or 0)
        m2.metric("Network Stations", total_stations or 0)
        m3.metric("Regional Personnel", total_staff or 0)
        st.divider()

        # --- 2. ACTIONS & SEARCH ---
        c_search, c_add = st.columns([3, 1], vertical_alignment="bottom")
        search_term = c_search.text_input("🔍 Search Regions", placeholder="Filter by name or email...")
        
        with c_add.expander("➕ New Region"):
            with st.form("add_region_form", clear_on_submit=True):
                r_name = st.text_input("Region Name")
                r_email = st.text_input("Region Email (optional)")
                if st.form_submit_button("Create Region", use_container_width=True):
                    if not r_name.strip():
                        st.error("Region name is required.")
                    else:
                        new_reg = Region(name=r_name.strip(), email=r_email.strip() or None)
                        session.add(new_reg)
                        session.commit()
                        log_activity(conn, "CREATE_REGION", f"Added region: {r_name}")
                        st.success(f"Region '{r_name}' added.")
                        st.rerun()

        # Fetch Region Directory Data
        # Note: We use subqueries for counts to keep the main directory load snappy
        st_sub = select(func.count(Station.id)).where(Station.region_id == Region.id).scalar_subquery()
        
        # Subquery for Region Manager Name
        mgr_sub = select(
            func.coalesce(func.nullif(func.trim(User.name + ' ' + User.surname), ''), User.email, User.username)
        ).where(User.region_id == Region.id, User.role == 'Region Manager').limit(1).scalar_subquery()

        mgr_id_sub = select(User.id).where(User.region_id == Region.id, User.role == 'Region Manager').limit(1).scalar_subquery()

        stmt = select(
            Region.id.label("ID"),
            Region.name.label("Name"),
            Region.email.label("Email"),
            st_sub.label("Stations"),
            mgr_sub.label("Manager"),
            mgr_id_sub.label("Manager_ID")
        ).order_by(Region.name)

        if search_term:
            stmt = stmt.where(or_(Region.name.ilike(f"%{search_term}%"), Region.email.ilike(f"%{search_term}%")))

        df_regions = pd.read_sql_query(stmt, session.bind)

        # Fetch all stations for the map and their pending submission status
        pending_sub = select(func.count(Submission.id)).where(
            Submission.station_id == Station.id, Submission.processed == 0
        ).scalar_subquery()

        stmt_all_stations = select(
            Station.id, Station.name, Station.lat, Station.lon, Station.region_id,
            Region.name.label("region_name"), pending_sub.label("pending_count")
        ).outerjoin(Region).where(
            Station.lat.isnot(None), Station.lon.isnot(None)
        )
        df_all_stations = pd.read_sql_query(stmt_all_stations, session.bind)

    if df_regions.empty:
        st.info("No regions found matching your criteria.")
        return

    # --- 3. REGION DIRECTORY ---
    st.subheader("🏢 Region Directory")
    st.caption("Select a row below to manage region details, stations, or staff.")

    # The 'key' parameter helps Streamlit maintain component state across reruns.
    selection_event = st.dataframe(
        df_regions,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="regions_directory_table",
        column_config={
            "ID": st.column_config.NumberColumn(width="small"),
            "Stations": st.column_config.NumberColumn(format="%d ⛽"),
            "Email": st.column_config.TextColumn(width="medium"),
            "Manager_ID": None  # Hide internal ID
        }
    )

    # --- 4. SELECTION & MANAGEMENT ---
    # Update the persistent ID when the user clicks a row in the table
    rows = selection_event.get("selection", {}).get("rows", [])
    if rows:
        st.session_state.selected_region_id = int(df_regions.iloc[rows[0]]["ID"])
    
    if st.session_state.selected_region_id is None:
        st.info("💡 Tip: Click a region in the table above to view management options.")
        return

    # Use the persistent ID to fetch current data. This ensures the management editor 
    # stays open even after a Save/Rerun cycle where the table might reset.
    curr_df = df_regions[df_regions["ID"] == st.session_state.selected_region_id]
    if curr_df.empty:
        # Handle case where selected region was deleted or is hidden by search filters
        st.session_state.selected_region_id = None
        st.rerun()

    curr = curr_df.iloc[0]
    selected_id = st.session_state.selected_region_id

    st.divider()
    # Professional header with a Close button
    c_header, c_close = st.columns([5, 1])
    c_header.subheader(f"⚙️ Manage: {curr['Name']}")
    if c_close.button("Close ✖️", help="Clear selection and return to directory", use_container_width=True):
        st.session_state.selected_region_id = None
        st.rerun()

    tab_edit, tab_stations, tab_manager, tab_map = st.tabs(["📝 Edit Details", "🔗 Stations", "👥 Region Manager", "🗺️ Network Map"])

    with tab_edit:
        with st.form(f"edit_region_form_{selected_id}"):
            new_name = st.text_input("Region Name", value=curr["Name"])
            new_email = st.text_input("Region Email", value=curr["Email"] if curr["Email"] else "")
            if st.form_submit_button("💾 Save Changes", use_container_width=True):
                if not new_name.strip():
                    st.error("Region name cannot be empty.")
                else:
                    with get_session() as session:
                        session.query(Region).filter(Region.id == selected_id).update({
                            Region.name: new_name.strip(),
                            Region.email: new_email.strip() or None
                        })
                        session.commit()
                    log_activity(conn, "UPDATE_REGION", f"Updated region {selected_id} -> {new_name}")
                    st.success("Region updated.")
                    st.rerun()

        if st.button("🗑️ Delete Region", type="secondary", use_container_width=True, key=f"del_region_btn_{selected_id}"):
            with get_session() as session:
                try:
                    session.query(Region).filter(Region.id == selected_id).delete()
                    session.commit()
                    log_activity(conn, "DELETE_REGION", f"Deleted region ID {selected_id}")
                    st.success("Region deleted.")
                    st.rerun()
                except IntegrityError:
                    st.error("Cannot delete region: Stations are currently assigned to this region.")

    with tab_stations:
        stations_df = pd.read_sql_query(
            "SELECT id as \"ID\", name as \"Station Name\", physical_address as \"Address\" FROM stations WHERE region_id = %s ORDER BY id",
            conn,
            params=(selected_id,),
        )
        if stations_df.empty:
            st.info("No stations assigned to this region.")
        else:
            st.dataframe(stations_df, width="stretch", hide_index=True)

    with tab_manager:
        # Show current manager jump link
        if pd.notna(curr["Manager_ID"]):
            st.markdown(f"**Current Manager:** `{curr['Manager']}`")
            if st.button(f"👤 View {curr['Manager']}'s Profile", type="secondary", use_container_width=True):
                st.session_state["active_page"] = "Employees"
                st.session_state["target_employee_id"] = int(curr["Manager_ID"])
                st.rerun()
            st.divider()

        # Selection for new manager
        mgrs = pd.read_sql_query(
            """
            SELECT
                id,
                COALESCE(
                    NULLIF(TRIM(COALESCE(name,'') || ' ' || COALESCE(surname,'')), ''),
                    email,
                    username
                ) as fullname
            FROM users
            WHERE role = 'Region Manager'
            ORDER BY name
            """,
            conn,
        )
        mgr_list = ["-- None --"] + mgrs["fullname"].tolist()
        selected_mgr = st.selectbox("Select Region Manager to assign", mgr_list)
        if st.button("Assign Manager to Region", type="primary", use_container_width=True):
            if selected_mgr == "-- None --":
                st.info("Please choose a Region Manager from the list.")
            else:
                mgr_id = int(mgrs[mgrs["fullname"] == selected_mgr]["id"].values[0])
                with get_session() as session:
                    session.query(User).filter(User.id == mgr_id).update({User.region_id: selected_id})
                    session.commit()
                log_activity(
                    conn,
                    "ASSIGN_REGION_MANAGER",
                    f"Assigned {selected_mgr} to region {curr['Name']}",
                )
                st.success(f"Updated Region Manager.")
                st.rerun()

    with tab_map:
        st.subheader("🌍 Regional Network Map")
        st.caption("All stations colored by region. Selected region stations are highlighted with stars.")
        
        if df_all_stations.empty:
            st.info("No station coordinates available to map.")
        else:
            # Color palette for regions
            MAP_COLORS = [
                'blue', 'green', 'purple', 'orange', 'darkred', 
                'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue', 
                'darkpurple', 'pink', 'lightblue', 'lightgreen'
            ]
            
            # Initialize map
            m = folium.Map(tiles="CartoDB positron")

            # --- Inject CSS for Status Pulses ---
            m.get_root().html.add_child(folium.Element("""
                <style>
                    @keyframes pulse-red {
                        0% { box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.7); }
                        70% { box-shadow: 0 0 0 15px rgba(220, 53, 69, 0); }
                        100% { box-shadow: 0 0 0 0 rgba(220, 53, 69, 0); }
                    }
                    @keyframes pulse-orange {
                        0% { box-shadow: 0 0 0 0 rgba(253, 126, 20, 0.7); }
                        70% { box-shadow: 0 0 0 15px rgba(253, 126, 20, 0); }
                        100% { box-shadow: 0 0 0 0 rgba(253, 126, 20, 0); }
                    }
                    .pulse-red { background-color: #dc3545; border-radius: 50%; width: 14px; height: 14px; animation: pulse-red 1.5s infinite; }
                    .pulse-orange { background-color: #fd7e14; border-radius: 50%; width: 14px; height: 14px; animation: pulse-orange 1.5s infinite; }
                    .custom-div-icon { background: transparent; border: none; }
                </style>
            """))

            # --- Build Legend HTML ---
            legend_items = ""
            for _, reg in df_regions.iterrows():
                reg_color = MAP_COLORS[int(reg["ID"]) % len(MAP_COLORS)]
                legend_items += f'<div><i class="fa fa-circle" style="color:{reg_color}"></i> {reg["Name"]}</div>'
            
            legend_html = f'''
                 <div style="position: absolute; bottom: 30px; left: 20px; width: auto; 
                 border:2px solid rgba(0,0,0,0.1); z-index:9999; font-size:12px;
                 background-color: rgba(255, 255, 255, 0.9); padding: 10px; border-radius: 8px; 
                 box-shadow: 0 0 10px rgba(0,0,0,0.1); font-family: sans-serif;">
                 <b style="display:block; margin-bottom: 5px;">Region Legend</b>
                 {legend_items}
                 <hr style="margin: 5px 0;">
                 <div><span style="color:#dc3545">●</span> High Risk (3+)</div>
                 <div><span style="color:#fd7e14">●</span> Pending (1-2)</div>
                 </div>
                 '''
            m.get_root().html.add_child(folium.Element(legend_html))

            fg_pulse = folium.FeatureGroup(name="Safety Status Pulses")
            fg_stations = folium.FeatureGroup(name="Network Stations")
            
            for _, station in df_all_stations.iterrows():
                is_selected = int(station['region_id']) == selected_id if pd.notna(station['region_id']) else False
                pending = int(station['pending_count'] or 0)
                
                # 1. Add Pulse Layer if station has pending items
                if pending > 0 and is_selected:
                    p_class = "pulse-red" if pending >= 3 else "pulse-orange"
                    folium.Marker(
                        location=[station["lat"], station["lon"]],
                        icon=folium.DivIcon(
                            icon_size=(14, 14),
                            icon_anchor=(7, 7),
                            class_name="custom-div-icon",
                            html=f'<div class="{p_class}"></div>',
                        ),
                        tooltip=f"Alert: {pending} tasks pending"
                    ).add_to(fg_pulse)
                
                # Assign color based on region ID
                reg_id = int(station['region_id']) if pd.notna(station['region_id']) else 0
                color = MAP_COLORS[reg_id % len(MAP_COLORS)]
                
                # Marker details
                icon_type = "star" if is_selected else "gas-pump"
                prefix = "fa"
                
                folium.Marker(
                    location=[station["lat"], station["lon"]],
                    popup=f"<b>{station['name']}</b><br>Region: {station['region_name'] or 'N/A'}",
                    tooltip=f"{station['name']} - {pending} pending",
                    icon=folium.Icon(color=color, icon=icon_type, prefix=prefix)
                ).add_to(fg_stations)

            fg_pulse.add_to(m)
            fg_stations.add_to(m)
            
            # Auto-zoom to focus on the selected region's stations
            df_target = df_all_stations[df_all_stations['region_id'] == selected_id]
            if not df_target.empty:
                bounds = [[df_target["lat"].min(), df_target["lon"].min()], 
                          [df_target["lat"].max(), df_target["lon"].max()]]
            else:
                bounds = [[df_all_stations["lat"].min(), df_all_stations["lon"].min()], 
                          [df_all_stations["lat"].max(), df_all_stations["lon"].max()]]
            m.fit_bounds(bounds, padding=(30, 30))
            
            st_folium(m, width="100%", height=500, key=f"region_map_{selected_id}")
