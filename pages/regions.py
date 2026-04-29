# gentstation_opus/pages/regions.py
import streamlit as st
import pandas as pd
from psycopg2 import IntegrityError
from core.activity_logger import log_activity
from ui.header import render_page_header


def render(conn):
    render_page_header("🌍 Regions Management")

    # Top: create new region
    with st.expander("➕ Add New Region"):
        with st.form("add_region_form"):
            r_name = st.text_input("Region Name")
            r_email = st.text_input("Region Email (optional)")
            if st.form_submit_button("Create Region"):
                if not r_name.strip():
                    st.error("Region name is required.")
                else:
                    conn.execute(
                        "INSERT INTO regions (name, email) VALUES (%s,%s)",
                        (r_name.strip(), r_email.strip() or None),
                    )
                    conn.commit()
                    log_activity(conn, "CREATE_REGION", f"Added region: {r_name}")
                    st.success(f"Region '{r_name}' added.")
                    st.rerun()

    # Region list
    regions_query = """
        SELECT
            r.id AS "ID",
            r.name AS "Name",
            r.email AS "Email",
            (SELECT COUNT(*) FROM stations s WHERE s.region_id = r.id) AS "Stations",
            COALESCE((SELECT u.name || ' ' || u.surname FROM users u WHERE u.region_id = r.id AND u.role = 'Region Manager' LIMIT 1), '-') AS "Region Manager",
            (SELECT u.id FROM users u WHERE u.region_id = r.id AND u.role = 'Region Manager' LIMIT 1) AS "Region Manager ID",
            (
                SELECT COUNT(DISTINCT u.id)
                FROM users u
                LEFT JOIN stations s ON u.station_id = s.id
                WHERE
                    u.region_id = r.id OR
                    s.region_id = r.id OR
                    u.id IN (SELECT dr.user_id FROM director_regions dr WHERE dr.region_id = r.id)
            ) AS "Employees"
        FROM regions r
        ORDER BY r.id
    """
    df_regions = pd.read_sql_query(regions_query, conn)
    if df_regions.empty:
        st.info("No regions yet. Add one using the form above.")
        return

    st.subheader("Existing Regions")

    # Custom Table Header
    cols = st.columns([1.5, 2, 1, 1, 2])
    cols[0].markdown("**Name**")
    cols[1].markdown("**Region Manager**")
    cols[2].markdown("**Stations**")
    cols[3].markdown("**Employees**")
    cols[4].markdown("**Email**")
    st.divider()

    for _, row in df_regions.iterrows():
        c = st.columns([1.5, 2, 1, 1, 2], vertical_alignment="center")
        c[0].write(row["Name"])

        # Clickable Manager Name
        mgr_name = row["Region Manager"]
        mgr_id = row["Region Manager ID"]

        if pd.notna(mgr_id) and mgr_name != "-":
            if c[1].button(
                f"👤 {mgr_name}",
                key=f"nav_mgr_{row['ID']}",
                help="Go to Employee Details",
            ):
                st.session_state["active_page"] = "Employees"
                st.session_state["target_employee_id"] = int(mgr_id)
                st.rerun()
        else:
            c[1].write(mgr_name)

        c[2].write(str(row["Stations"]))
        c[3].write(str(row["Employees"]))
        c[4].write(row["Email"] if row["Email"] else "-")
        st.divider()

    # Edit / delete region
    st.subheader("✏️ Edit or Delete a Region")
    region_ids = df_regions["ID"].tolist()
    selected = st.selectbox(
        "Choose region",
        region_ids,
        format_func=lambda x: f"ID {x}: {df_regions[df_regions['ID']==x]['Name'].values[0]}",
    )

    curr = df_regions[df_regions["ID"] == selected].iloc[0]

    with st.expander("📝 Edit Region Details", expanded=False):
        with st.form(f"edit_region_{selected}"):
            new_name = st.text_input("Region Name", value=curr["Name"])
            new_email = st.text_input(
                "Region Email", value=curr["Email"] if curr["Email"] else ""
            )
            if st.form_submit_button("Save Changes"):
                if not new_name.strip():
                    st.error("Region name cannot be empty.")
                else:
                    conn.execute(
                        "UPDATE regions SET name = %s, email = %s WHERE id = %s",
                        (new_name.strip(), new_email.strip() or None, selected),
                    )
                    conn.commit()
                    log_activity(
                        conn,
                        "UPDATE_REGION",
                        f"Updated region {selected} -> {new_name}",
                    )
                    st.success("Region updated.")
                    st.rerun()

    if st.button("🗑️ Delete Region", key=f"del_region_{selected}"):
        try:
            conn.execute("DELETE FROM regions WHERE id = %s", (selected,))
            conn.commit()
            log_activity(conn, "DELETE_REGION", f"Deleted region ID {selected}")
            st.success("Region deleted.")
            st.rerun()
        except IntegrityError:
            st.error(
                "Cannot delete region: Stations are currently assigned to this region. Please reassign them first."
            )
        except Exception as e:
            st.error(f"An error occurred: {e}")

    st.divider()
    st.subheader("🔗 Stations in the selected Region")
    stations = pd.read_sql_query(
        "SELECT id, name, physical_address FROM stations WHERE region_id = %s ORDER BY id",
        conn,
        params=(selected,),
    )
    if stations.empty:
        st.info("No stations assigned to this region.")
    else:
        st.dataframe(stations, width="stretch", hide_index=True)

    st.divider()
    st.subheader("👥 Attach/Assign Region Manager")
    # List Region Manager employees
    mgrs = pd.read_sql_query(
        "SELECT id, name || ' ' || surname as fullname FROM users WHERE role = 'Region Manager' ORDER BY name",
        conn,
    )
    mgr_list = ["-- None --"] + mgrs["fullname"].tolist()
    selected_mgr = st.selectbox("Select Region Manager to assign", mgr_list)
    if st.button("Assign Manager to Region"):
        if selected_mgr == "-- None --":
            st.info("Choose a Region Manager from the list.")
        else:
            mgr_id = int(mgrs[mgrs["fullname"] == selected_mgr]["id"].values[0])
            # For simplicity we set user.region_id = region
            conn.execute(
                "UPDATE users SET region_id = %s WHERE id = %s", (selected, mgr_id)
            )
            conn.commit()
            log_activity(
                conn,
                "ASSIGN_REGION_MANAGER",
                f"Assigned employee {mgr_id} to region {curr['Name']}",
            )
            st.success(f"Assigned {selected_mgr} to region {curr['Name']}")
            st.rerun()
