# gentstation_opus/pages/regions.py
import streamlit as st
import sqlite3
import pandas as pd
from core.activity_logger import log_activity

def render(conn):
    st.title("🌍 Regions Management")

    # Top: create new region
    with st.expander("➕ Add New Region"):
        with st.form("add_region_form"):
            r_name = st.text_input("Region Name")
            r_email = st.text_input("Region Email (optional)")
            if st.form_submit_button("Create Region"):
                if not r_name.strip():
                    st.error("Region name is required.")
                else:
                    conn.execute("INSERT INTO regions (name, email) VALUES (?,?)", (r_name.strip(), r_email.strip() or None))
                    conn.commit()
                    log_activity(conn, "CREATE_REGION", f"Added region: {r_name}")
                    st.success(f"Region '{r_name}' added.")
                    st.rerun()

    # Region list
    df_regions = pd.read_sql_query("SELECT * FROM regions ORDER BY id", conn)
    if df_regions.empty:
        st.info("No regions yet. Add one using the form above.")
        return

    st.subheader("Existing Regions")
    st.dataframe(df_regions, use_container_width=True, hide_index=True)

    st.divider()

    # Edit / delete region
    st.subheader("✏️ Edit or Delete a Region")
    region_ids = df_regions['id'].tolist()
    selected = st.selectbox("Choose region", region_ids, format_func=lambda x: f"ID {x}: {df_regions[df_regions['id']==x]['name'].values[0]}")

    curr = df_regions[df_regions['id'] == selected].iloc[0]

    with st.expander("📝 Edit Region Details", expanded=False):
        with st.form(f"edit_region_{selected}"):
            new_name = st.text_input("Region Name", value=curr['name'])
            new_email = st.text_input("Region Email", value=curr['email'] if curr['email'] else "")
            if st.form_submit_button("Save Changes"):
                if not new_name.strip():
                    st.error("Region name cannot be empty.")
                else:
                    conn.execute("UPDATE regions SET name = ?, email = ? WHERE id = ?", (new_name.strip(), new_email.strip() or None, selected))
                    conn.commit()
                    log_activity(conn, "UPDATE_REGION", f"Updated region {selected} -> {new_name}")
                    st.success("Region updated.")
                    st.rerun()

    if st.button("🗑️ Delete Region", key=f"del_region_{selected}"):
        try:
            conn.execute("DELETE FROM regions WHERE id = ?", (selected,))
            conn.commit()
            log_activity(conn, "DELETE_REGION", f"Deleted region ID {selected}")
            st.success("Region deleted.")
            st.rerun()
        except sqlite3.IntegrityError:
            st.error("Cannot delete region: Stations are currently assigned to this region. Please reassign them first.")
        except Exception as e:
            st.error(f"An error occurred: {e}")

    st.divider()
    st.subheader("🔗 Stations in the selected Region")
    stations = pd.read_sql_query("SELECT id, name, physical_address FROM stations WHERE region_id = ? ORDER BY id", conn, params=(selected,))
    if stations.empty:
        st.info("No stations assigned to this region.")
    else:
        st.dataframe(stations, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("👥 Attach/Assign Region Manager")
    # List Region Manager employees
    mgrs = pd.read_sql_query("SELECT id, name || ' ' || surname as fullname FROM employees WHERE role = 'Region Manager' ORDER BY name", conn)
    mgr_list = ["-- None --"] + mgrs['fullname'].tolist()
    selected_mgr = st.selectbox("Select Region Manager to assign", mgr_list)
    if st.button("Assign Manager to Region"):
        if selected_mgr == "-- None --":
            st.info("Choose a Region Manager from the list.")
        else:
            mgr_id = int(mgrs[mgrs['fullname'] == selected_mgr]['id'].values[0])
            # For simplicity we set employee.region_id = region
            conn.execute("UPDATE employees SET region_id = ? WHERE id = ?", (selected, mgr_id))
            conn.commit()
            log_activity(conn, "ASSIGN_REGION_MANAGER", f"Assigned employee {mgr_id} to region {selected}")
            st.success(f"Assigned {selected_mgr} to region {curr['name']}")
            st.rerun()