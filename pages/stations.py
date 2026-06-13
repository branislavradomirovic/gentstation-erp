# gentstation_opus/pages/stations.py
import os
import re
import streamlit as st
import pandas as pd
import folium
from sqlalchemy import select, func, or_, asc, desc, case
from sqlalchemy.orm import joinedload, selectinload
from streamlit_folium import st_folium
from core.activity_logger import log_activity
from core.subscription import RESOURCE_STATIONS, UsageLimitError, require_usage_capacity
from ui.header import render_page_header
from core.database import get_session, get_schema_readiness
from core.models import Station, Region, User, Submission, SystemSetting, StationCategory
import urllib.parse
import urllib.request
import json
from psycopg2 import IntegrityError

# Import email service
try:
    from core.comm_service import send_station_qr_email
except ImportError:

    def send_station_qr_email(*args):
        st.error("Email service unavailable")


def _ensure_dict(payload):
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except Exception:
        return {}

def render(conn):
    render_page_header("⛽ Stations Management")

    schema_state = get_schema_readiness(conn)
    if not schema_state["is_ready"]:
        st.warning(
            "Stations Management is partially unavailable because the Postgres schema is behind the current code."
        )
        for msg in schema_state["blockers"] + schema_state["warnings"]:
            st.caption(msg)
        st.info(
            "Apply the relational station category migration before using this page."
        )
        return

    # --- DATA PREPARATION WITH ORM ---
    with get_session() as session:
        # Load Categories from the structured table
        categories_list = session.execute(select(StationCategory).order_by(StationCategory.name)).scalars().all()

        CATEGORY_COLORS = {}
        CATEGORY_DESCRIPTIONS = {}
        category_id_map = {}

        for cat in categories_list:
            CATEGORY_COLORS[cat.name] = cat.color
            CATEGORY_DESCRIPTIONS[cat.name] = cat.description
            category_id_map[cat.name] = cat.id

        if not CATEGORY_COLORS:
            CATEGORY_COLORS = {"Retail": "blue", "Other": "gray"}

        # --- 0. CONFIG & SUMMARY METRICS ---
        # Load staffing thresholds
        s_over = session.get(SystemSetting, 'staffing_threshold_over')
        s_under = session.get(SystemSetting, 'staffing_threshold_under')
        threshold_over = int(s_over.value) if s_over else 5
        threshold_under = int(s_under.value) if s_under else 2

        st_count = session.scalar(select(func.count(Station.id)))
        staff_count = session.scalar(select(func.count(User.id)).where(User.station_id.isnot(None)))
        pending_count = session.scalar(select(func.count(Submission.id)).where(Submission.processed == 0))

        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("Total Stations", st_count or 0)
        m_col2.metric("Network Staff", staff_count or 0)
        m_col3.metric("Pending Audits", pending_count or 0)
        st.divider()

        regions_list = session.execute(select(Region).order_by(Region.name)).scalars().all()
        regions_map = {r.name: r.id for r in regions_list}

        # Fetch only necessary fields for managers to optimize memory and speed
        mgr_query = select(User.id, User.name, User.surname, User.username).where(
            User.role.in_(['Gas Station Manager', 'Gas Station Supervisor', 'General Manager'])
        )
        managers = session.execute(mgr_query).all()
        mgr_map = {f"{m.name or ''} {m.surname or ''}".strip() or m.username: m.id for m in managers}

    # --- 1. ADD NEW STATION ---
    with st.expander("➕ Add New Station", expanded=False):
        st.write("📍 **Step 1: Select Location on Map**")

        # Initialize map centered on the region
        m_create = folium.Map(location=[44.2108, 20.9224], zoom_start=7)

        # Show a marker if the user has already clicked on the map
        if "create_lat" in st.session_state and "create_lon" in st.session_state:
            folium.Marker(
                [st.session_state.create_lat, st.session_state.create_lon],
                icon=folium.Icon(color="blue", icon="info-sign"),
                draggable=True,
            ).add_to(m_create)

        # Render map and catch clicks
        map_create_data = st_folium(
            m_create, width="100%", height=300, key="map_create"
        )

        # Update session state with coordinates on click
        create_click_data = map_create_data.get("last_object_clicked") or map_create_data.get("last_clicked")
        if create_click_data:
            clicked_lat = create_click_data["lat"]
            clicked_lon = create_click_data["lng"]
            if (
                st.session_state.get("create_lat") != float(clicked_lat)
                or st.session_state.get("create_lon") != float(clicked_lon)
            ):
                st.session_state.create_lat = clicked_lat
                st.session_state.create_lon = clicked_lon
                st.rerun()

        st.write("📝 **Step 2: Station Details**")
        with st.form("add_station_form"):
            s_name = st.text_input("Station Name")
            s_addr = st.text_input("Physical Address")
            s_email = st.text_input("Station Email (optional)")
            region_name = st.selectbox(
                "Region", ["-- None --"] + list(regions_map.keys())
            )
            s_category = st.selectbox(
                "Station Type / Category", options=list(CATEGORY_COLORS.keys()), index=0
            )
            if CATEGORY_DESCRIPTIONS.get(s_category):
                st.caption(f"ℹ️ {CATEGORY_DESCRIPTIONS[s_category]}")
            mgr_name = st.selectbox(
                "Assign Gas Station Manager", ["-- None --"] + list(mgr_map.keys())
            )

            st.caption("📍 GPS coordinates are captured automatically from the map pointer above.")
            c1, c2 = st.columns(2)
            lat_val = c1.number_input(
                "Latitude (via Map)",
                value=st.session_state.get("create_lat", 0.0),
                format="%.6f",
                disabled=True
            )
            lon_val = c2.number_input(
                "Longitude (via Map)",
                value=st.session_state.get("create_lon", 0.0),
                format="%.6f",
                disabled=True
            )

            if st.form_submit_button("Create Station"):
                email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
                if not s_name.strip():
                    st.error("Station name is required.")
                elif s_email.strip() and not re.match(email_regex, s_email.strip()):
                    st.error("Please enter a valid station email address.")
                elif s_category not in CATEGORY_COLORS:
                    st.error(f"Selected category '{s_category}' is no longer valid. Please refresh the page.")
                else:
                    # Database Insertion
                    region_id = (
                        regions_map.get(region_name)
                        if region_name != "-- None --"
                        else None
                    )

                    try:
                        require_usage_capacity(conn, RESOURCE_STATIONS)
                        with get_session() as session:
                            new_station = Station(
                                name=s_name.strip(),
                                region_id=region_id,
                                physical_address=s_addr.strip() or None,
                                email=s_email.strip() or None,
                                lat=lat_val,
                                lon=lon_val,
                                category_id=category_id_map.get(s_category)
                            )
                            session.add(new_station)
                            session.flush() # Get the new ID

                            if mgr_name != "-- None --":
                                mgr_id = mgr_map.get(mgr_name)
                                manager = session.get(User, mgr_id)
                                if manager:
                                    manager.station_id = new_station.id

                            new_id = new_station.id
                    except UsageLimitError as exc:
                        st.error(str(exc))
                        return

                    # LOGGING AND FEEDBACK
                    log_activity(
                        conn,
                        "CREATE_STATION",
                        f"Created station {s_name} (ID {new_id})",
                    )
                    st.success(f"✅ Station '{s_name}' has been successfully created!")
                    st.toast(f"Station {s_name} added to database.", icon="⛽")

                    # Cleanup session and refresh
                    st.session_state.pop("create_lat", None)
                    st.session_state.pop("create_lon", None)
                    st.rerun()

    # --- SEARCH & FILTERING ---
    st.subheader("Existing Stations")

    c_search, c_region, c_cat = st.columns([2, 1, 1])
    search_query = c_search.text_input("🔍 Search", placeholder="Name, address, or email...", key="station_search_input")

    # Use session state for the multiselect to allow programmatic updates from the chart
    if "station_filter_regions" not in st.session_state:
        st.session_state.station_filter_regions = []

    selected_regions = c_region.multiselect("🌍 Filter Regions", options=list(regions_map.keys()), key="station_filter_regions")

    # Use session state for the multiselect to allow programmatic updates from the chart
    if "station_filter_categories" not in st.session_state:
        st.session_state.station_filter_categories = []

    selected_categories = c_cat.multiselect("🏷️ Filter Categories", options=list(CATEGORY_COLORS.keys()), key="station_filter_categories")

    c_sort_col, c_sort_dir, _ = st.columns([1.5, 1, 1.5])
    sort_options = {"ID": Station.id, "Name": Station.name, "Region": Region.name, "Address": Station.physical_address}
    sort_col_name = c_sort_col.selectbox("Sort By", options=list(sort_options.keys()), index=1)
    sort_desc = c_sort_dir.toggle("Descending", value=False)

    # Track filter/sort state to reset pagination
    current_filter_state = f"{search_query}-{selected_regions}-{selected_categories}-{sort_col_name}-{sort_desc}"
    if "last_filter_state" not in st.session_state:
        st.session_state.last_filter_state = current_filter_state

    if current_filter_state != st.session_state.last_filter_state:
        st.session_state.stations_page = 1
        st.session_state.last_filter_state = current_filter_state

    # --- PAGINATION SETTINGS ---
    PAGE_SIZE = 20
    if "stations_page" not in st.session_state:
        st.session_state.stations_page = 1

    # --- ORM QUERY BUILDING (Optimized Projections) ---
    # We fetch specific columns and use subqueries for managers.
    # This avoids N+1 issues and DetachedInstanceErrors during rendering.
    mgr_priority = case(
        (User.role == 'Gas Station Manager', 1),
        (User.role == 'Gas Station Supervisor', 2),
        else_=3
    )

    mgr_name_sub = select(
        func.coalesce(func.nullif(func.trim(User.name + ' ' + User.surname), ''), User.email, User.username)
    ).where(
        User.station_id == Station.id,
        User.role.in_(['Gas Station Manager', 'Gas Station Supervisor', 'General Manager'])
    ).order_by(mgr_priority).limit(1).scalar_subquery()

    mgr_id_sub = select(User.id).where(
        User.station_id == Station.id,
        User.role.in_(['Gas Station Manager', 'Gas Station Supervisor', 'General Manager'])
    ).order_by(mgr_priority).limit(1).scalar_subquery()

    # Subquery to calculate current staffing levels per station
    staff_count_sub = select(func.count(User.id)).where(User.station_id == Station.id).scalar_subquery()

    # Base statement for both table view and export
    base_stmt = select(
        Station.id,
        Station.name,
        StationCategory.name.label("category"),
        Region.name.label("region_name"),
        Station.physical_address,
        Station.email,
        mgr_name_sub.label("manager"),
        mgr_id_sub.label("manager_id"),
        staff_count_sub.label("staff_count")
    ).outerjoin(Region).outerjoin(StationCategory, Station.category_id == StationCategory.id)


    # --- 2. STATIONS TABLE ---
    # Build filters
    filters = []
    if search_query:
        search_pattern = f"%{search_query}%"
        filters.append(or_(
            Station.name.ilike(search_pattern),
            Station.physical_address.ilike(search_pattern),
            Station.email.ilike(search_pattern)
        ))

    if selected_regions:
        region_ids = [regions_map[name] for name in selected_regions]
        filters.append(Station.region_id.in_(region_ids))

    if selected_categories:
        selected_category_ids = [
            category_id_map[name] for name in selected_categories if name in category_id_map
        ]
        if selected_category_ids:
            filters.append(Station.category_id.in_(selected_category_ids))

    # --- 1.5 ANALYTICS CHARTS ---
    def group_small_items(df, label_col, limit=8):
        """Groups items beyond the top N into an 'Others' bucket for cleaner charts."""
        if len(df) <= limit:
            return df
        df = df.sort_values("Count", ascending=False)
        top = df.head(limit).copy()
        others_val = df.iloc[limit:]["Count"].sum()
        others = pd.DataFrame([{label_col: "Others", "Count": others_val}])
        return pd.concat([top, others], ignore_index=True)

    try:
        import plotly.express as px
    except ImportError:
        st.warning("📊 Analytics charts are currently disabled because the 'plotly' library is not installed. Run `pip install plotly` to enable them.")
        px = None

    if px:
        with get_session() as session:
            st.markdown("#### 📈 Network Analytics")

            # Data Toggle for Analytics Charts
            metric_choice = st.radio(
                "Analytics Metric:",
                ["Stations", "Employees"],
                horizontal=True,
                label_visibility="collapsed",
                key="regional_metric_toggle"
            )

            chart_col1, chart_col2 = st.columns(2)

            # Query 1: Category Distribution (Bar Chart)
            if metric_choice == "Employees":
                dist_stmt = select(
                    StationCategory.name.label("Category"),
                    func.count(User.id).label("Count"),
                ).select_from(StationCategory)\
                    .outerjoin(Station, Station.category_id == StationCategory.id)\
                    .outerjoin(User, User.station_id == Station.id)\
                    .group_by(StationCategory.name)
            else:
                dist_stmt = select(
                    StationCategory.name.label("Category"),
                    func.count(Station.id).label("Count"),
                ).select_from(StationCategory)\
                    .outerjoin(Station, Station.category_id == StationCategory.id)\
                    .group_by(StationCategory.name)

            if filters:
                dist_stmt = dist_stmt.where(*filters)
            dist_results_raw = session.execute(dist_stmt).all()
            dist_df_all = pd.DataFrame(dist_results_raw, columns=["Category", "Count"])
            dist_df_all["Category"] = dist_df_all["Category"].fillna("Unassigned")

            # Query 2: Regional Distribution (Pie Chart)
            if metric_choice == "Employees":
                # Count unique users assigned to the region OR to stations within that region
                reg_dist_stmt = select(Region.name, func.count(User.id).label("Count"))\
                    .outerjoin(Station, Station.region_id == Region.id)\
                    .outerjoin(User, or_(User.region_id == Region.id, User.station_id == Station.id))\
                    .group_by(Region.name)
            else:
                reg_dist_stmt = select(Region.name, func.count(Station.id).label("Count"))\
                    .outerjoin(Region).group_by(Region.name)

            if filters:
                reg_dist_stmt = reg_dist_stmt.where(*filters)
            reg_results_raw = session.execute(reg_dist_stmt).all()
            reg_df_all = pd.DataFrame(reg_results_raw, columns=["Region", "Count"])
            reg_df_all["Region"] = reg_df_all["Region"].fillna("Unassigned")

            with chart_col1:
                if not dist_df_all.empty:
                    dist_df_grouped = group_small_items(dist_df_all, "Category")
                    fig_bar = px.bar(
                        dist_df_grouped,
                        y="Category", x="Count",
                        orientation='h',
                        color="Category",
                        title=f"Category {metric_choice} Distribution",
                        color_discrete_map=CATEGORY_COLORS
                    )
                    fig_bar.update_layout(showlegend=False, height=350, margin=dict(t=40, b=20, l=0, r=0), yaxis={'categoryorder':'total ascending'})

                    # Make the chart interactive
                    bar_event = st.plotly_chart(fig_bar, use_container_width=True, on_select="rerun", key="cat_dist_chart")

                    # If a bar is clicked, add that category to the filters
                    if bar_event and bar_event.get("selection", {}).get("points"):
                        clicked_cat = bar_event["selection"]["points"][0].get("y")
                        if clicked_cat and clicked_cat not in st.session_state.station_filter_categories:
                            st.session_state.station_filter_categories.append(clicked_cat)
                            st.rerun()


            with chart_col2:
                if not reg_df_all.empty:
                    reg_df_grouped = group_small_items(reg_df_all, "Region", limit=6)

                    fig_pie = px.pie(reg_df_grouped, values='Count', names='Region',
                                 title=f"Regional {metric_choice} Spread",
                                 color_discrete_sequence=px.colors.qualitative.Safe)
                    fig_pie.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=350)

                    # Make the chart interactive
                    pie_event = st.plotly_chart(fig_pie, use_container_width=True, on_select="rerun", key="reg_dist_chart")

                    # If a slice is clicked, add that region to the filters
                    if pie_event and pie_event.get("selection", {}).get("points"):
                        clicked_reg = pie_event["selection"]["points"][0].get("label")
                        # Ignore clicks on 'Others' grouping or 'Unassigned' and check if already in filters
                        if clicked_reg and clicked_reg not in ["Others", "Unassigned"] and clicked_reg not in st.session_state.station_filter_regions:
                            st.session_state.station_filter_regions.append(clicked_reg)
                            st.rerun()

            # --- DETAILED DATA TABLE ---
            with st.expander("📄 View Detailed Analytics Table", expanded=False):
                table_col1, table_col2 = st.columns(2)
                with table_col1:
                    st.caption("Category Breakdown")
                    dist_df_all["Share %"] = (dist_df_all["Count"] / dist_df_all["Count"].sum() * 100).round(1)
                    st.dataframe(dist_df_all.sort_values("Count", ascending=False), use_container_width=True, hide_index=True)

                with table_col2:
                    st.caption("Regional Breakdown")
                    reg_df_all["Share %"] = (reg_df_all["Count"] / reg_df_all["Count"].sum() * 100).round(1)
                    st.dataframe(reg_df_all.sort_values("Count", ascending=False), use_container_width=True, hide_index=True)

    with get_session() as session:
        # Get total count for pagination UI
        # We need to join Region if sorting or filtering by Region attributes
        count_stmt = select(func.count(Station.id)).outerjoin(Region)
        if filters:
            count_stmt = count_stmt.where(*filters)

        total_count = session.scalar(count_stmt)
        total_pages = (total_count // PAGE_SIZE) + (1 if total_count % PAGE_SIZE > 0 else 0)

        # Ensure current page is within bounds
        if st.session_state.stations_page > total_pages and total_pages > 0:
            st.session_state.stations_page = total_pages

        offset = (st.session_state.stations_page - 1) * PAGE_SIZE

        stmt = base_stmt
        if filters:
            stmt = stmt.where(*filters)

        # Dynamic Order By
        sort_attr = sort_options[sort_col_name]
        order_func = desc(sort_attr) if sort_desc else asc(sort_attr)
        stmt = stmt.order_by(order_func).limit(PAGE_SIZE).offset(offset)

        stations_rows = session.execute(stmt).all()
        df = pd.DataFrame([r._asdict() for r in stations_rows])

    # Pagination Controls (Top)
    p_col1, p_col2, p_col3 = st.columns([1, 2, 1])
    if p_col1.button("⬅️ Previous", key="pagination_prev_top", disabled=st.session_state.stations_page <= 1, use_container_width=True):
        st.session_state.stations_page -= 1
        st.rerun()

    p_col2.markdown(f"<p style='text-align: center;'>Page <b>{st.session_state.stations_page}</b> of {total_pages}<br><small>{total_count} matching stations</small></p>", unsafe_allow_html=True)

    if p_col3.button("Next ➡️", key="pagination_next_top", disabled=st.session_state.stations_page >= total_pages, use_container_width=True):
        st.session_state.stations_page += 1
        st.rerun()

    if df.empty:
        st.info("No stations available.")
    else:
        # Custom Table Header
        cols = st.columns([0.5, 1.5, 1.0, 0.8, 1.2, 1.5, 2, 1.5])
        cols[0].markdown("**ID**")
        cols[1].markdown("**Name**")
        cols[2].markdown("**Type**")
        cols[3].markdown("**Staff**")
        cols[4].markdown("**Region**")
        cols[5].markdown("**Address**")
        cols[6].markdown("**Email**")
        cols[7].markdown("**Manager**")
        st.divider()

        for _, row in df.iterrows():
            c = st.columns([0.5, 1.5, 1.0, 0.8, 1.2, 1.5, 2, 1.5], vertical_alignment="center")
            c[0].write(str(row["id"]))
            c[1].write(row["name"])
            c[2].write(row["category"] or "-")

            # Staffing indicator based on dynamic thresholds
            staff_num = int(row["staff_count"] or 0)
            if staff_num > threshold_over:
                staff_icon = "🔴"
            elif staff_num < threshold_under:
                staff_icon = "🟡"
            else:
                staff_icon = "👤"
            c[3].write(f"{staff_icon} {staff_num}")

            c[4].write(row["region_name"] if row["region_name"] else "-")
            c[5].write(row["physical_address"] if row["physical_address"] else "-")
            c[6].write(row["email"] if row["email"] else "-")

            mgr_name = row["manager"]
            mgr_id = row["manager_id"]

            if pd.notna(mgr_id) and mgr_name:
                if c[7].button(
                    f"👤 {mgr_name}",
                    key=f"nav_mgr_st_{row['id']}",
                    help="Go to Employee Details",
                ):
                    st.session_state["active_page"] = "Employees"
                    st.session_state["target_employee_id"] = int(mgr_id)
                    st.rerun()
            else:
                c[7].write(mgr_name if mgr_name else "-")

            st.divider()

    # Pagination Controls (Bottom)
    p_btm_col1, p_btm_col2, p_btm_col3 = st.columns([1, 2, 1])
    if p_btm_col1.button("⬅️ Previous", key="pagination_prev_bottom", disabled=st.session_state.stations_page <= 1, use_container_width=True):
        st.session_state.stations_page -= 1
        st.rerun()
    p_btm_col2.markdown(f"<p style='text-align: center;'>Page <b>{st.session_state.stations_page}</b></p>", unsafe_allow_html=True)
    if p_btm_col3.button("Next ➡️", key="pagination_next_bottom", disabled=st.session_state.stations_page >= total_pages, use_container_width=True):
        st.session_state.stations_page += 1
        st.rerun()

    # --- 3. EDIT / DELETE STATION ---
    st.divider()
    st.subheader("✏️ Edit / Delete Station")
    station_ids = df["id"].tolist() if not df.empty else []

    # Handle navigation from Employee Directory (persisting selection)
    sb_key = "station_selector_main"
    if "target_station_id" in st.session_state:
        tgt = st.session_state.pop("target_station_id")
        if tgt in station_ids:
            st.session_state[sb_key] = tgt

    if station_ids:
        sel = st.selectbox(
            "Select Station to Modify",
            station_ids,
            key=sb_key,
            format_func=lambda x: f"ID {x}: {df[df['id']==x]['name'].values[0]}",
        )

        # Load existing data for selected station
        # We extract attributes into a dictionary to avoid DetachedInstanceError after the session closes
        with get_session() as session:
            st_obj = session.get(Station, sel)
            if not st_obj:
                st.error("Station not found.")
                st.stop()
            curr = {
                "name": st_obj.name,
                "physical_address": st_obj.physical_address,
                "email": st_obj.email,
                "region_id": st_obj.region_id,
                "lat": st_obj.lat,
                "lon": st_obj.lon,
                "category": st_obj.category.name if st_obj.category else "Other"
            }

        tab_edit, tab_staff, tab_audit, tab_perf, tab_mobile = st.tabs([
            "📝 Edit Details", "👥 Staff & Manager", "📜 Audit History", "📊 Performance", "📱 Mobile Access"
        ])

        with tab_edit:
            st.write("📍 **Update Location (Optional)**")
            st.caption("Click on the map to set a new location pointer for this station.")
            # Initialize map at current station coordinates
            start_lat = curr["lat"] if curr["lat"] else 44.2108
            start_lon = curr["lon"] if curr["lon"] else 20.9224

            m_edit = folium.Map(location=[start_lat, start_lon], zoom_start=12)

            # Use session state or database values for marker
            display_lat = st.session_state.get(f"edit_lat_{sel}", start_lat)
            display_lon = st.session_state.get(f"edit_lon_{sel}", start_lon)

            # Get color and description based on station category
            station_category = curr.get("category", "Other")
            marker_color = CATEGORY_COLORS.get(station_category, "#808080")
            cat_desc = CATEGORY_DESCRIPTIONS.get(station_category, "")
            tooltip_text = f"{curr['name']} ({station_category})" + (f" - {cat_desc}" if cat_desc else "")

            # Professional Teardrop Marker using custom HTML and Hex Color support
            marker_html = f'''
                <div style="
                    background-color: {marker_color};
                    width: 32px;
                    height: 32px;
                    border-radius: 50% 50% 50% 0;
                    transform: rotate(-45deg);
                    border: 2px solid white;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 0 5px rgba(0,0,0,0.3);
                "><i class="fa fa-star" style="color: white; transform: rotate(45deg); font-size: 14px;"></i></div>
            '''

            folium.Marker(
                [display_lat, display_lon],
                tooltip=tooltip_text,
                icon=folium.DivIcon(icon_size=(32, 32), icon_anchor=(16, 32), html=marker_html),
                draggable=True,
            ).add_to(m_edit)

            # Render edit map
            map_edit_data = st_folium(
                m_edit, width="100%", height=250, key=f"map_edit_{sel}"
            )

            # Update if user clicks a new location
            edit_click_data = map_edit_data.get("last_object_clicked") or map_edit_data.get("last_clicked")
            if edit_click_data:
                e_lat = edit_click_data["lat"]
                e_lon = edit_click_data["lng"]
                if (
                    st.session_state.get(f"edit_lat_{sel}") != e_lat
                    or st.session_state.get(f"edit_lon_{sel}") != e_lon
                ):
                    st.session_state[f"edit_lat_{sel}"] = e_lat
                    st.session_state[f"edit_lon_{sel}"] = e_lon
                    st.rerun()

            with st.form(f"edit_station_{sel}"):
                name = st.text_input("Station Name", value=curr["name"])
                addr = st.text_input("Address", value=curr["physical_address"] or "")
                email = st.text_input("Email", value=curr["email"] or "")

                # Region Dropdown logic
                region_options = ["-- None --"] + list(regions_map.keys())
                current_region_name = next(
                    (k for k, v in regions_map.items() if v == curr["region_id"]),
                    "-- None --",
                )
                sel_region = st.selectbox(
                    "Region",
                    region_options,
                    index=region_options.index(current_region_name),
                )

                # Category Dropdown logic
                cat_options = list(CATEGORY_COLORS.keys())
                sel_cat = st.selectbox(
                    "Station Category",
                    cat_options,
                    index=cat_options.index(curr["category"]) if curr["category"] in cat_options else 0,
                )
                if CATEGORY_DESCRIPTIONS.get(sel_cat):
                    st.caption(f"ℹ️ {CATEGORY_DESCRIPTIONS[sel_cat]}")

                c3, c4 = st.columns(2)
                st.info("💡 **Tip:** Click on the map above to update the station's location pointer.")
                u_lat = c3.number_input("Latitude", value=float(display_lat), format="%.6f", disabled=True)
                u_lon = c4.number_input("Longitude", value=float(display_lon), format="%.6f", disabled=True)

                if st.form_submit_button("Save Basic Details", width="stretch"):
                    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
                    if not name.strip():
                        st.error("Station name cannot be empty.")
                    elif email.strip() and not re.match(email_regex, email.strip()):
                        st.error("Please enter a valid station email address.")
                    elif sel_cat not in CATEGORY_COLORS:
                        st.error(f"Selected category '{sel_cat}' is no longer valid. Please refresh the page.")
                    else:
                        region_id = regions_map.get(sel_region) if sel_region != "-- None --" else None
                        conn.execute(
                            "UPDATE stations SET name=%s, physical_address=%s, email=%s, region_id=%s, lat=%s, lon=%s, category_id=%s WHERE id=%s",
                            (name.strip(), addr.strip() or None, email.strip() or None, region_id, u_lat, u_lon, category_id_map.get(sel_cat), sel),
                        )
                        conn.commit()
                        log_activity(conn, "UPDATE_STATION", f"Updated station ID {sel} ({name})")
                        st.success(f"💾 Changes for '{name}' have been saved.")
                        st.rerun()

            if st.button("🗑️ Delete Station", type="secondary", use_container_width=True):
                try:
                    conn.execute("DELETE FROM stations WHERE id = %s", (sel,))
                    conn.commit()
                    log_activity(conn, "DELETE_STATION", f"Deleted station ID {sel}")
                    st.success(f"Station ID {sel} removed.")
                    st.rerun()
                except IntegrityError:
                    st.error("Cannot delete station: It contains linked records (e.g., employees, history).")

        with tab_staff:
            st.subheader("Assign Manager")
            mgr_options = ["-- None --"] + list(mgr_map.keys())
            curr_mgr_name_q = pd.read_sql_query(
                """
                SELECT COALESCE(NULLIF(TRIM(COALESCE(name, '') || ' ' || COALESCE(surname, '')), ''), email, username) as fullname
                FROM users WHERE station_id = %s
                ORDER BY CASE role WHEN 'Gas Station Manager' THEN 0 WHEN 'Gas Station Supervisor' THEN 1 ELSE 2 END, id LIMIT 1
                """, conn, params=(sel,)
            )
            curr_mgr_name = curr_mgr_name_q["fullname"].iloc[0] if not curr_mgr_name_q.empty else "-- None --"
            sel_mgr = st.selectbox("Select Manager", mgr_options, index=mgr_options.index(curr_mgr_name) if curr_mgr_name in mgr_options else 0)

            if st.button("Update Assigned Manager", key=f"btn_assign_mgr_{sel}", type="primary", use_container_width=True):
                conn.execute("UPDATE users SET station_id = NULL WHERE station_id = %s AND role IN ('Gas Station Manager', 'Gas Station Supervisor')", (sel,))
                if sel_mgr != "-- None --":
                    mgr_id = mgr_map.get(sel_mgr)
                    conn.execute("UPDATE users SET station_id = %s WHERE id = %s", (sel, mgr_id))
                conn.commit()
                st.success("Manager assignment updated.")
                st.rerun()

            st.divider()
            st.subheader("Assigned Staff")
            assigned_employees_df = pd.read_sql_query(
                "SELECT name, surname, role, email FROM users WHERE station_id = %s",
                conn,
                params=(sel,),
            )
            if assigned_employees_df.empty:
                st.info("No employees are currently assigned to this station.")
            else:
                st.dataframe(assigned_employees_df, width="stretch", hide_index=True)

        with tab_audit:
            st.subheader("📜 AI Audit History")
            audit_query = """
                SELECT s.timestamp, s.data_json, u.name || ' ' || u.surname as employee_name, s.video_path
                FROM submissions s
                JOIN users u ON s.employee_id = u.id
                WHERE s.station_id = %s AND s.processed = 1 AND s.data_json IS NOT NULL
                ORDER BY s.timestamp DESC LIMIT 50
            """
            audit_df = pd.read_sql_query(audit_query, conn, params=(sel,))
            if audit_df.empty:
                st.info("No AI-processed audit reports found for this station.")
            else:
                for _, report in audit_df.iterrows():
                    with st.container(border=True):
                        report_data = _ensure_dict(report["data_json"])
                        st.markdown(f"**Submitted by:** `{report['employee_name']}` on **{report['timestamp']}**")
                        score_cols = st.columns(4)
                        score_cols[0].metric("Safety", f"{report_data.get('safety_score', 'N/A')}/10")
                        score_cols[1].metric("Cleanliness", f"{report_data.get('cleanliness_score', 'N/A')}/10")
                        score_cols[2].metric("Staff", f"{report_data.get('staff_score', 'N/A')}/10")
                        score_cols[3].metric("Merchandising", f"{report_data.get('merchandising_score', 'N/A')}/10")
                        st.markdown(f"**AI Summary:** *{report_data.get('summary', 'No summary available.')}*")
                        if report["video_path"] and os.path.exists(report["video_path"]):
                            with st.expander("🎥 Watch Video Footage"):
                                st.video(report["video_path"])

        with tab_perf:
            st.subheader("📈 Performance Trends")
            trend_date = st.date_input("Select Month", value=pd.Timestamp.now(), key=f"perf_date_{sel}")
            selected_month = trend_date.strftime("%Y-%m")

            t_col1, t_col2 = st.columns(2)
            with t_col1:
                st.write("**Daily Submissions**")
                trend_df = pd.read_sql_query(
                    "SELECT to_char(timestamp, 'YYYY-MM-DD') as day, COUNT(*) as count FROM submissions WHERE station_id = %s AND to_char(timestamp, 'YYYY-MM') = %s GROUP BY day ORDER BY day",
                    conn, params=(sel, selected_month)
                )
                if not trend_df.empty: st.bar_chart(trend_df.set_index("day"))
                else: st.caption("No data for this month.")

            with t_col2:
                st.write("**12-Month Volume**")
                monthly_df = pd.read_sql_query(
                    "SELECT to_char(timestamp, 'YYYY-MM') as month, COUNT(*) as count FROM submissions WHERE station_id = %s AND timestamp >= NOW() - INTERVAL '12 months' GROUP BY month ORDER BY month",
                    conn, params=(sel,)
                )
                if not monthly_df.empty: st.line_chart(monthly_df.set_index("month"))
                else: st.caption("No yearly data.")

        with tab_mobile:
            st.subheader("📱 Mobile Access (QR Code)")
            bot_handle = os.getenv("TELEGRAM_BOT_HANDLE", "your_bot_username")
            bot_link = f"https://t.me/{bot_handle}"
            qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(bot_link)}"
            c_qr, c_desc = st.columns([1, 3])
            with c_qr: st.image(qr_api_url, width=150)
            with c_desc:
                st.markdown(f"**Bot Link:** {bot_handle}")
                st.caption("Distribute this QR code to employees at this station. Scanning it will open the reporting bot in Telegram.")

                # Download Logic
                try:
                    with urllib.request.urlopen(qr_api_url) as resp:
                        qr_bytes = resp.read()
                        st.download_button("⬇️ Download QR Code", qr_bytes, key=f"dl_qr_{sel}", file_name=f"station_{sel}_qr.png", mime="image/png", use_container_width=True)
                except: st.warning("Download unavailable.")

                # Email Logic
                mgr_email_row = conn.execute(
                    "SELECT email FROM users WHERE station_id = %s AND role = 'Gas Station Manager'",
                    (sel,)
                ).fetchone()

                if st.button("📧 Share via Email", key=f"email_qr_{sel}", disabled=(not mgr_email_row), use_container_width=True):
                    send_station_qr_email(curr["name"], mgr_email_row[0], bot_link, qr_api_url)
                    st.success("Email sent to Manager.")
