# pages/admin_users.py
import streamlit as st
import re
import pandas as pd
from sqlalchemy import select, func
from core.database import get_connection
from core.activity_logger import log_activity
from core.auth import create_user, hash_password, verify_password
from core.comm_service import send_activation_email
from ui.header import render_page_header
from core.database import get_session
from core.models import User, Station, Region


def render(conn):
    render_page_header("🔧 System Administration")

    # --- 0. PERSISTENT STATE ---
    if "selected_admin_user_id" not in st.session_state:
        st.session_state.selected_admin_user_id = None

    # --- 1. DATA PREPARATION & METRICS ---
    with get_session() as session:
        total_users = session.scalar(select(func.count(User.id)))
        active_users = session.scalar(select(func.count(User.id)).where(User.is_active == True))
        locked_users = session.scalar(select(func.count(User.id)).where(User.locked_until.isnot(None)))

        m1, m2, m3 = st.columns(3)
        m1.metric("Total System Users", total_users or 0)
        m2.metric("Active Accounts", active_users or 0)
        m3.metric("Security Lockouts", locked_users or 0)
        st.divider()

        # Fetch existing users for the directory
        stmt = select(
            User.id, User.username, User.email, User.role, User.is_active, 
            User.failed_attempts, User.locked_until,
            User.station_id, User.region_id
        ).order_by(User.id.desc())
        
        df_users = pd.read_sql_query(stmt, session.bind)

    # --- SYSTEM MAINTENANCE CONTROL ---
    with st.expander("⚙️ System Maintenance", expanded=False):
        st.write("When enabled, only **General Manager** users can log in.")
        cur = conn.cursor()
        row_maint = cur.execute(
            "SELECT value FROM system_settings WHERE key='maintenance_mode'"
        ).fetchone()
        is_maint_on = row_maint and row_maint[0] == "1"

        new_maint = st.toggle("🚨 Enable Maintenance Mode", value=is_maint_on)
        if new_maint != is_maint_on:
            val = "1" if new_maint else "0"
            conn.execute(
                """
                INSERT INTO system_settings (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                ("maintenance_mode", val),
            )
            conn.commit()
            log_activity(conn, "MAINTENANCE_MODE", f"Set to {new_maint}")
            st.rerun()

    # --- ADMIN: BREAK SETTINGS ---
    with st.expander("☕ Admin: Break Settings", expanded=False):
        st.write("Configure default break duration for all gas stations.")
        try:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key=%s",
                ("default_break_minutes",),
            ).fetchone()
            current_default = int(row[0]) if row and row[0] else 15
        except Exception:
            current_default = 15

        new_val = st.number_input(
            "Default break duration (minutes)",
            min_value=1,
            max_value=240,
            value=current_default,
        )
        if st.button("Save Break Duration", type="primary", width="stretch"):
            try:
                conn.execute(
                    "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    ("default_break_minutes", str(int(new_val))),
                )
                conn.commit()
                log_activity(
                    conn,
                    "SETTING_CHANGE",
                    f"Admin set default_break_minutes to {int(new_val)}",
                )
                st.success("Default break duration updated.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save: {e}")

    st.divider()
    # --- 2. CREATE NEW USER ---
    # Move options fetching up so they are available for both Create and Edit forms
    stations_df = pd.read_sql_query("SELECT id, name FROM stations ORDER BY name", conn)
    station_options = [(row["name"], row["id"]) for _, row in stations_df.iterrows()]
    regions_df = pd.read_sql_query("SELECT id, name FROM regions ORDER BY name", conn)
    region_options = [(row["name"], row["id"]) for _, row in regions_df.iterrows()]

    st.markdown("### Create new system user")

    with st.form("create_user_form"):
        c_a, c_b = st.columns(2)
        first_name = c_a.text_input("First name")
        surname = c_b.text_input("Surname")
        username = st.text_input("Username")
        email = st.text_input("Email")
        role = st.selectbox(
            "Role",
            [
                "General Manager",
                "Region Manager",
                "Gas Station Manager",
                "Employee",
            ],
        )
        station_id = None
        region_id = None
        if role in ("Employee", "Gas Station Manager"):
            selected_station = st.selectbox(
                "Assign Station (Required)",
                options=[(None, None)] + station_options,
                format_func=lambda x: x[0] if x[0] else "Select station...",
            )
            station_id = selected_station[1] if selected_station else None
        elif role == "Region Manager":
            selected_region = st.selectbox(
                "Assign Region (Required)",
                options=[(None, None)] + region_options,
                format_func=lambda x: x[0] if x[0] else "Select region...",
            )
            region_id = selected_region[1] if selected_region else None

        pwd = st.text_input("Temporary password", value="", type="password")
        if st.form_submit_button("Create user"):
            email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
            clean_user = (username or "").strip()
            if not clean_user or not pwd:
                st.error("Username and password required")
            elif email and not re.match(email_regex, (email or "").strip()):
                st.error("A valid email address is required.")
            elif role in ("Employee", "Gas Station Manager") and not station_id:
                st.error("Station is required for this role.")
            elif role == "Region Manager" and not region_id:
                st.error("Region is required for this role.")
            else:
                try:
                    u = create_user(
                        username=clean_user,
                        password=pwd,
                        email=(email or "").strip() or None,
                        role=role,
                        name=(first_name or "").strip() or None,
                        surname=(surname or "").strip() or None,
                        station_id=station_id,
                        region_id=region_id,
                    )  # create_user now handles all user fields
                    log_activity(
                        conn, "CREATE_USER", f"Created user {username} role {role}"
                    )
                    sent, msg = send_activation_email(
                        conn, u["id"], reset_password=True
                    )
                    if not sent:
                        st.warning(f"User created, but activation email failed: {msg}")
                    st.success(f"User {username} created.")
                except Exception as e:
                    st.error(f"Failed to create user: {e}")

    st.divider()
    # --- 3. USER DIRECTORY ---
    st.markdown("### 👥 Existing System Users")
    st.caption("Click a row to manage account details, security, and permissions.")

    if df_users.empty:
        st.info("No users yet.")
    else:
        selection_event = st.dataframe(
            df_users,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="admin_user_directory",
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "is_active": st.column_config.CheckboxColumn("Active"),
                "locked_until": st.column_config.DatetimeColumn("Locked Until"),
                "station_id": None,
                "region_id": None
            }
        )

        # Update state based on selection
        rows = selection_event.get("selection", {}).get("rows", [])
        if rows:
            st.session_state.selected_admin_user_id = int(df_users.iloc[rows[0]]["id"])

    if st.session_state.selected_admin_user_id:
        selected_id = st.session_state.selected_admin_user_id
        curr_row = df_users[df_users["id"] == selected_id]
        if curr_row.empty:
            st.session_state.selected_admin_user_id = None
            st.rerun()
        
        user_rec = curr_row.iloc[0]

        st.divider()
        c_title, c_close = st.columns([5, 1])
        c_title.subheader(f"⚙️ Manage User: {user_rec['username']}")
        if c_close.button("Close ✖️", key="close_admin_mgmt", use_container_width=True):
            st.session_state.selected_admin_user_id = None
            st.rerun()

        tab_details, tab_security = st.tabs(["📝 Profile Details", "🔑 Security & Access"])

        with tab_details:
            st.write(f"Account Role: **{user_rec['role']}**")
            new_role = st.selectbox("Role", ["General Manager", "Region Manager", "Gas Station Manager", "Employee"], 
                                    index=["General Manager", "Region Manager", "Gas Station Manager", "Employee"].index(user_rec["role"]),
                                    key=f"role_selector_edit_{selected_id}")

            with st.form(f"edit_admin_user_{selected_id}"):
                new_email = st.text_input("Email Address", value=user_rec["email"] or "")

                # Assignment logic for Edit Form
                edit_station_id = None
                edit_region_id = None

                if new_role in ("Employee", "Gas Station Manager"):
                    curr_st_id = user_rec["station_id"]
                    st_idx = 0
                    if pd.notna(curr_st_id):
                        for i, opt in enumerate(station_options):
                            if opt[1] == int(curr_st_id):
                                st_idx = i + 1
                                break
                    sel_st = st.selectbox("Assign Station (Required)", options=[(None, None)] + station_options, index=st_idx, format_func=lambda x: x[0] if x[0] else "Select station...")
                    edit_station_id = sel_st[1]
                elif new_role == "Region Manager":
                    curr_reg_id = user_rec["region_id"]
                    reg_idx = 0
                    if pd.notna(curr_reg_id):
                        for i, opt in enumerate(region_options):
                            if opt[1] == int(curr_reg_id):
                                reg_idx = i + 1
                                break
                    sel_reg = st.selectbox("Assign Region (Required)", options=[(None, None)] + region_options, index=reg_idx, format_func=lambda x: x[0] if x[0] else "Select region...")
                    edit_region_id = sel_reg[1]

                if st.form_submit_button("💾 Save Profile Changes", use_container_width=True):
                    # Input Validation
                    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
                    
                    if not re.match(email_regex, (new_email or "").strip()):
                        st.error("A valid email address is required.")
                    elif new_role == "Region Manager" and not edit_region_id:
                        st.error("Region Manager requires a region assignment.")
                    elif new_role in ("Employee", "Gas Station Manager") and not edit_station_id:
                        st.error("Station is required for this role.")
                    else:
                        conn.execute(
                            "UPDATE users SET email = %s, role = %s, station_id = %s, region_id = %s WHERE id = %s", 
                            ((new_email or "").strip() or None, new_role, edit_station_id, edit_region_id, selected_id)
                        )
                        conn.commit()
                        st.success("Profile updated.")
                        st.rerun()

            # --- DELETE CONFIRMATION ---
            st.divider()
            if st.button("🗑️ Delete User Account", key=f"del_admin_{selected_id}", type="secondary", use_container_width=True):
                st.session_state[f"confirm_admin_del_{selected_id}"] = True
            
            if st.session_state.get(f"confirm_admin_del_{selected_id}"):
                st.warning(f"⚠️ **Confirm**: Delete `{user_rec['username']}`? All settings and profile data will be lost.")
                c_d1, c_d2 = st.columns(2)
                if c_d1.button("✅ Yes, Delete", key=f"do_admin_del_{selected_id}", type="primary", use_container_width=True):
                    try:
                        conn.execute("DELETE FROM users WHERE id = %s", (selected_id,))
                        conn.commit()
                        log_activity(conn, "DELETE_USER", f"Deleted ID {selected_id}")
                        st.session_state.selected_admin_user_id = None
                        st.session_state.pop(f"confirm_admin_del_{selected_id}", None)
                        st.success("User deleted.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not delete: {e}")
                if c_d2.button("❌ Cancel", key=f"cancel_admin_del_{selected_id}", use_container_width=True):
                    st.session_state.pop(f"confirm_admin_del_{selected_id}", None)
                    st.rerun()

        with tab_security:
            col_s1, col_col_s2 = st.columns(2)
            with col_s1:
                st.write("**Account Status**")
                if user_rec["is_active"]:
                    if st.button("Deactivate Account", key=f"deact_{selected_id}", use_container_width=True):
                        conn.execute("UPDATE users SET is_active = FALSE WHERE id = %s", (selected_id,))
                        conn.commit()
                        st.rerun()
                else:
                    if st.button("Activate Account", key=f"act_{selected_id}", type="primary", use_container_width=True):
                        conn.execute("UPDATE users SET is_active = TRUE WHERE id = %s", (selected_id,))
                        conn.commit()
                        st.rerun()

                if user_rec["locked_until"]:
                    if st.button("🔓 Unlock Account", key=f"unlock_{selected_id}", type="primary", use_container_width=True):
                        conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = %s", (selected_id,))
                        conn.commit()
                        st.rerun()

            with col_col_s2:
                st.write("**Credentials**")
                if st.button("📧 Resend Activation Email", key=f"resend_act_{selected_id}", use_container_width=True):
                    sent, msg = send_activation_email(conn, selected_id, reset_password=True)
                    if sent: st.success(msg)
                    else: st.error(msg)

            st.divider()
            st.write("**Manual Password Reset**")
            with st.form(f"manual_reset_{selected_id}"):
                manual_pw = st.text_input("New Temporary Password", type="password")
                if st.form_submit_button("Reset Password", use_container_width=True):
                    if not manual_pw:
                        st.error("Enter a password.")
                    else:
                        conn.execute("UPDATE users SET password_hash = %s, updated_at = %s, force_password_change = TRUE WHERE id = %s", 
                                     (hash_password(manual_pw), pd.Timestamp.now().isoformat(), selected_id))
                        conn.commit()
                        st.success("Password reset successfully.")
