import streamlit as st
import re
import pandas as pd
import secrets
from psycopg2 import IntegrityError
from core.activity_logger import log_activity
from core.auth import (
    create_user,
    hash_password as hash_password_bcrypt,
)  # Use bcrypt for all passwords
from core.report_scope import (
    get_station_manager_options,
    get_region_manager_options,
    get_general_manager_options,
)
from ui.header import render_page_header

# Import the communication service logic
try:
    from core.comm_service import send_welcome_comms
except ImportError:
    # Fallback if service isn't created yet
    def send_welcome_comms(data):
        return None


def generate_temp_password(n: int = 10) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"  # pragma: allowlist secret
    return "".join(secrets.choice(alphabet) for _ in range(n))


def render(conn):
    render_page_header("👥 Employees")
    st.markdown(
        '<div class="gs-page-intro">Manage reporting users, Telegram linkage, and account access from one tabbed workspace.</div>',
        unsafe_allow_html=True,
    )

    # --- PRE-FETCH DATA FOR DROPDOWNS ---
    stations_df = pd.read_sql_query("SELECT id, name FROM stations ORDER BY name", conn)
    station_options = [(row["name"], row["id"]) for _, row in stations_df.iterrows()]

    regions_df = pd.read_sql_query("SELECT id, name FROM regions ORDER BY name", conn)
    region_options = [(row["name"], row["id"]) for _, row in regions_df.iterrows()]

    role_options = ["Employee", "Gas Station Manager", "Region Manager", "General Manager"]
    station_manager_options = get_station_manager_options(conn)
    region_manager_options = get_region_manager_options(conn)
    general_manager_options = get_general_manager_options(conn)
    directory_query = """
        SELECT
               u.id,
               COALESCE(NULLIF(TRIM(COALESCE(u.name,'') || ' ' || COALESCE(u.surname,'')), ''), u.email, u.username, ('User ' || u.id::text)) as fullname,
               u.email,
               u.role,
               s.name as station_name,
               u.station_id,
               COALESCE(r.name, rs.name) as region_name,
               u.telegram_chat_id
        FROM users u
        LEFT JOIN stations s ON u.station_id = s.id
        LEFT JOIN regions r ON u.region_id = r.id
        LEFT JOIN regions rs ON s.region_id = rs.id
        WHERE 1=1
    """
    df = pd.DataFrame()

    tab_register, tab_directory, tab_manage = st.tabs(
        ["➕ Register Employee", "📇 Directory", "⚙️ Manage Account"]
    )

    # --- 1. REGISTER NEW EMPLOYEE ---
    with tab_register:
        st.markdown("#### New Employee Onboarding")
        st.caption(
            "Create a reporting user, assign the right operational scope, and trigger invite communications."
        )
        role = st.selectbox(
            "Role",
            role_options,
            key="new_employee_role_selector",
            help="Select role first. Assignment fields below update automatically.",
        )

        with st.form("add_emp", clear_on_submit=True):
            col1, col2 = st.columns(2)
            first = col1.text_input("First name")
            last = col2.text_input("Surname")
            email = st.text_input("Email")

            # --- Conditional Assignment Widgets ---
            assign_station_id = None
            assign_region_id = None
            assign_manager_user_id = None
            if role in ["Employee", "Gas Station Supervisor", "Gas Station Manager"]:
                assign_station = st.selectbox(
                    "Assign Station (Required)",
                    options=[(None, None)] + station_options,
                    format_func=lambda x: x[0] if x[0] else "Select a station...",
                )
                if assign_station:
                    assign_station_id = assign_station[1]
                if role == "Employee":
                    mgr_choice = st.selectbox(
                        "Reports To (Gas Station Manager)",
                        options=[None] + [opt["id"] for opt in station_manager_options],
                        format_func=lambda x: "Select a manager..." if x is None else next(
                            (opt["label"] for opt in station_manager_options if opt["id"] == x),
                            f"Manager {x}",
                        ),
                    )
                    assign_manager_user_id = mgr_choice
                elif role == "Gas Station Manager":
                    mgr_choice = st.selectbox(
                        "Reports To (Region Manager)",
                        options=[None] + [opt["id"] for opt in region_manager_options],
                        format_func=lambda x: "Select a manager..." if x is None else next(
                            (opt["label"] for opt in region_manager_options if opt["id"] == x),
                            f"Manager {x}",
                        ),
                    )
                    assign_manager_user_id = mgr_choice

            elif role == "Region Manager":
                assign_region = st.selectbox(
                    "Assign Region (Required)",
                    options=[(None, None)] + region_options,
                    format_func=lambda x: x[0] if x[0] else "Select a region...",
                )
                if assign_region:
                    assign_region_id = assign_region[1]
                mgr_choice = st.selectbox(
                    "Reports To (General Manager)",
                    options=[None] + [opt["id"] for opt in general_manager_options],
                    format_func=lambda x: "Select a manager..." if x is None else next(
                        (opt["label"] for opt in general_manager_options if opt["id"] == x),
                        f"Manager {x}",
                    ),
                )
                assign_manager_user_id = mgr_choice

            if st.form_submit_button("Create Employee & Send Invites"):
                email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
                name_regex = r"^[a-zA-Z\s\-\']+$"
                clean_first = (first or "").strip()
                clean_email = (email or "").strip()
                
                if not clean_first or not re.match(name_regex, clean_first):
                    st.error("A valid first name is required (letters, spaces, hyphens only).")
                elif not re.match(email_regex, clean_email):
                    st.error("A valid email address is required.")
                elif (
                    role
                    in ["Employee", "Gas Station Manager"]
                    and not assign_station_id
                ):
                    st.error("A station MUST be selected for this role.")
                elif role == "Region Manager" and not assign_region_id:
                    st.error("A region MUST be selected for this role.")
                elif role != "General Manager" and not assign_manager_user_id:
                    st.error("A reporting manager MUST be selected for this role.")
                else:
                    # Generate Credentials
                    temp_pw = generate_temp_password()  # Plain text for email

                    try:
                        # Create user directly in the unified 'users' table
                        user_data = create_user(
                            username=clean_email,
                            password=temp_pw,  # create_user hashes it
                            email=clean_email,
                            role=role,
                            name=clean_first,
                            surname=(last or "").strip(),
                            station_id=assign_station_id,
                            region_id=assign_region_id,
                            manager_user_id=assign_manager_user_id,
                        )
                        new_id = user_data["id"]

                        conn.commit()  # Commit after all inserts

                        log_activity(
                            conn, "CREATE_EMPLOYEE", f"Created {first} {last} ({role})"
                        )

                        # --- START LIFECYCLE: EMAIL & TELEGRAM ---
                        user_info = {
                            "id": new_id,
                            "name": f"{clean_first} {last or ''}".strip(),
                            "email": clean_email,
                            "role": role,
                            "password_plain": temp_pw,  # Pass plain text for email
                        }

                        # This function handles the Email + Telegram logic
                        tg_link = send_welcome_comms(user_info)

                        st.success(f"✅ {first} {last} registered successfully!")
                        st.info(
                            f"🔑 Temporary Password: **{temp_pw}** (Sent via Email)"
                        )

                        if tg_link:
                            st.warning(
                                f"📲 Telegram Registration Required: [Register Bot]({tg_link})"
                            )
                            st.toast("Telegram invitation generated.", icon="🤖")

                        st.balloons()
                    except IntegrityError as e:
                        conn.rollback()
                        st.error(f"Database integrity error: {e}")
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Database error: {e}")

    with tab_directory:
        st.markdown("#### Employee Directory")
        st.caption(
            "Filter active reporting users by region or search for a specific person by name or email."
        )

        c_filter_1, c_filter_2 = st.columns([1, 2])
        with c_filter_1:
            sel_region_filter = st.selectbox(
                "Filter by Region", ["All"] + [opt[0] for opt in region_options]
            )
        with c_filter_2:
            search_text = st.text_input(
                "Search (Name or Email)", placeholder="Type to filter..."
            )

        dir_query_filtered = directory_query
        dir_params_filtered = []
        if sel_region_filter != "All":
            rid_filter = next(
                (opt[1] for opt in region_options if opt[0] == sel_region_filter), None
            )
            if rid_filter:
                dir_query_filtered += " AND (u.region_id = %s OR s.region_id = %s)"
                dir_params_filtered.extend([rid_filter, rid_filter])

        if search_text:
            like_pattern = f"%{search_text}%"
            dir_query_filtered += (
                " AND (COALESCE(u.name,'') || ' ' || COALESCE(u.surname,'') LIKE %s OR u.email LIKE %s)"
            )
            dir_params_filtered.extend([like_pattern, like_pattern])

        dir_query_filtered += " ORDER BY u.id"
        df = pd.read_sql_query(dir_query_filtered, conn, params=dir_params_filtered)

        if df.empty:
            st.info("No employees found.")
        else:
            df["TG Status"] = df["telegram_chat_id"].apply(
                lambda x: "🔗 Linked" if x else "❌ Unlinked"
            )
            st.dataframe(
                df[
                    [
                        "id",
                        "fullname",
                        "email",
                        "role",
                        "station_name",
                        "region_name",
                        "TG Status",
                    ]
                ].rename(
                    columns={
                        "id": "ID",
                        "fullname": "Name",
                        "email": "Email",
                        "role": "Role",
                        "station_name": "Station",
                        "region_name": "Region",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    # --- 3. EDIT / DELETE SECTION ---
    with tab_manage:
        st.markdown("#### Employee Account Management")
        st.caption(
            "Select an employee to update profile details, access settings, Telegram linkage, or recent reporting history."
        )
        emp_ids = df["id"].tolist() if not df.empty else []

        # Handle navigation from other pages (persisting selection)
        sb_key = "emp_selector_main"
        if "target_employee_id" in st.session_state:
            tgt = st.session_state.pop("target_employee_id")
            if tgt in emp_ids:
                st.session_state[sb_key] = tgt

        if not emp_ids:
            st.info("Use the Directory tab to locate employees before opening account management.")
            return

        sel = st.selectbox(
            "Select employee",
            emp_ids,
            key=sb_key,
            format_func=lambda x: f"ID {x}: {df[df['id'] == x]['fullname'].values[0]}",
        )
        rec = pd.read_sql_query(
            "SELECT * FROM users WHERE id = %s", conn, params=(sel,)
        ).iloc[0]

        tab_edit, tab_security, tab_activity = st.tabs(
            ["📝 Edit Details", "🔑 Access & Security", "📊 Activity History"]
        )

        with tab_edit:
            e_role = st.selectbox(
                "Role",
                role_options,
                index=(
                    role_options.index(rec["role"])
                    if rec["role"] in role_options
                    else 0
                ),
                key=f"edit_role_{sel}",
                help="Changing the role will automatically update the assignment fields inside the form below."
            )

            with st.form(f"edit_emp_{sel}"):
                e_name = st.text_input("First name", value=rec["name"] or "", key=f"edit_fn_{sel}")
                e_surname = st.text_input("Surname", value=rec["surname"] or "", key=f"edit_ln_{sel}")
                e_email = st.text_input("Email", value=rec["email"] or "", key=f"edit_em_{sel}")

                # --- Conditional Assignment Widgets for Edit Form ---
                e_station_id = None
                e_region_id = None
                e_manager_user_id = rec["manager_user_id"] if "manager_user_id" in rec else None

                if e_role in ["Employee", "Gas Station Manager"]:
                    curr_stat_idx = next(
                        (
                            i + 1
                            for i, opt in enumerate(station_options)
                            if opt[1] == rec["station_id"]
                        ),
                        0,
                    )
                    e_stat = st.selectbox(
                        "Station (Required)",
                        options=[(None, None)] + station_options,
                        index=curr_stat_idx,
                        format_func=lambda x: x[0] if x[0] else "Select a station...",
                        key=f"edit_assign_st_{sel}"
                    )
                    if e_stat:
                        e_station_id = e_stat[1]
                    if e_role == "Employee":
                        e_manager_user_id = st.selectbox(
                            "Reports To (Gas Station Manager)",
                            options=[None] + [opt["id"] for opt in station_manager_options],
                            index=([None] + [opt["id"] for opt in station_manager_options]).index(rec["manager_user_id"]) if rec["manager_user_id"] in [opt["id"] for opt in station_manager_options] else 0,
                            format_func=lambda x: "Select a manager..." if x is None else next(
                                (opt["label"] for opt in station_manager_options if opt["id"] == x),
                                f"Manager {x}",
                            ),
                            key=f"edit_assign_mgr_station_{sel}",
                        )
                    elif e_role == "Gas Station Manager":
                        e_manager_user_id = st.selectbox(
                            "Reports To (Region Manager)",
                            options=[None] + [opt["id"] for opt in region_manager_options],
                            index=([None] + [opt["id"] for opt in region_manager_options]).index(rec["manager_user_id"]) if rec["manager_user_id"] in [opt["id"] for opt in region_manager_options] else 0,
                            format_func=lambda x: "Select a manager..." if x is None else next(
                                (opt["label"] for opt in region_manager_options if opt["id"] == x),
                                f"Manager {x}",
                            ),
                            key=f"edit_assign_mgr_region_{sel}",
                        )

                elif e_role == "Region Manager":
                    curr_reg_idx = next(
                        (
                            i + 1
                            for i, opt in enumerate(region_options)
                            if opt[1] == rec["region_id"]
                        ),
                        0,
                    )
                    e_reg = st.selectbox(
                        "Region (Required)",
                        options=[(None, None)] + region_options,
                        index=curr_reg_idx,
                        format_func=lambda x: x[0] if x[0] else "Select a region...",
                        key=f"edit_assign_reg_{sel}"
                    )
                    if e_reg:
                        e_region_id = e_reg[1]
                    e_manager_user_id = st.selectbox(
                        "Reports To (General Manager)",
                        options=[None] + [opt["id"] for opt in general_manager_options],
                        index=([None] + [opt["id"] for opt in general_manager_options]).index(rec["manager_user_id"]) if rec["manager_user_id"] in [opt["id"] for opt in general_manager_options] else 0,
                        format_func=lambda x: "Select a manager..." if x is None else next(
                            (opt["label"] for opt in general_manager_options if opt["id"] == x),
                            f"Manager {x}",
                        ),
                        key=f"edit_assign_mgr_gm_{sel}",
                    )
                else:
                    e_manager_user_id = None

                if st.form_submit_button("💾 Save Profile Changes", use_container_width=True):
                    # Input Validation
                    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
                    name_regex = r"^[a-zA-Z\s\-\']+$"
                    clean_e_name = (e_name or "").strip()
                    clean_e_email = (e_email or "").strip()
                    
                    if not clean_e_name or not re.match(name_regex, clean_e_name):
                        st.error("A valid first name is required (letters, spaces, hyphens only).")
                    elif not re.match(email_regex, clean_e_email):
                        st.error("A valid email address is required.")
                    elif (
                        e_role
                        in ["Employee", "Gas Station Manager"]
                        and not e_station_id
                    ):
                        st.error("A station MUST be selected for this role.")
                    elif e_role == "Region Manager" and not e_region_id:
                        st.error("A region MUST be selected for this role.")
                    elif e_role != "General Manager" and not e_manager_user_id:
                        st.error("A reporting manager MUST be selected for this role.")
                    else:
                        try:
                            if e_role in ["Employee", "Gas Station Manager"]:
                                region_row = conn.execute(
                                    "SELECT region_id FROM stations WHERE id = %s",
                                    (e_station_id,),
                                ).fetchone()
                                if not region_row or region_row[0] is None:
                                    st.error("Selected station must belong to a region.")
                                    st.stop()
                                final_station_id = e_station_id
                                final_region_id = region_row[0]
                            elif e_role == "Region Manager":
                                final_station_id = None
                                final_region_id = e_region_id
                            else:
                                final_station_id = None
                                final_region_id = None

                            conn.execute(
                                "UPDATE users SET name=%s, surname=%s, email=%s, role=%s, station_id=%s, region_id=%s, manager_user_id=%s, username=%s WHERE id=%s",
                                (clean_e_name or None, (e_surname or "").strip() or None, clean_e_email, e_role, final_station_id, final_region_id, e_manager_user_id, clean_e_email, sel),
                            )
                            conn.commit()
                            st.success("Changes saved successfully.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

            # --- DELETE CONFIRMATION DIALOG ---
            st.divider()
            if st.button("🗑️ Delete Employee Record", key=f"btn_del_emp_{sel}", type="secondary", use_container_width=True):
                st.session_state[f"confirm_delete_{sel}"] = True

            if st.session_state.get(f"confirm_delete_{sel}"):
                st.warning(f"⚠️ **Confirm Deletion**: Are you sure you want to delete **{rec['name']} {rec['surname']}**? This action cannot be undone.")
                c_del_1, c_del_2 = st.columns(2)
                if c_del_1.button("✅ Yes, Delete Permanently", key=f"real_del_{sel}", type="primary", use_container_width=True):
                    try:
                        conn.execute("DELETE FROM users WHERE id = %s", (sel,))
                        conn.commit()
                        log_activity(conn, "DELETE_EMPLOYEE", f"Deleted ID {sel}")
                        st.session_state.pop(f"confirm_delete_{sel}", None)
                        st.success("Employee record deleted.")
                        st.rerun()
                    except IntegrityError:
                        st.error("Cannot delete employee: They have linked submissions or other dependent records.")
                if c_del_2.button("❌ Cancel", key=f"cancel_del_{sel}", use_container_width=True):
                    st.session_state.pop(f"confirm_delete_{sel}", None)
                    st.rerun()

        with tab_security:
            st.subheader("Access Control")
            e_tg = st.text_input(
                "Telegram Chat ID (Manual Edit)", value=rec["telegram_chat_id"] or "", key=f"edit_tg_{sel}",
                help="Used to link the employee to the Telegram reporting bot."
            )
            if st.button("Update Telegram ID", key=f"btn_update_tg_{sel}", use_container_width=True):
                conn.execute("UPDATE users SET telegram_chat_id = %s WHERE id = %s", (e_tg.strip() if e_tg.strip() else None, sel))
                conn.commit()
                st.success("Telegram Chat ID updated.")
                st.rerun()

            st.divider()
            st.subheader("Communication & Credentials")
            if st.button("🔄 Resend Welcome Invite / Reset Password", key=f"btn_resend_{sel}", type="primary", use_container_width=True):
                try:
                    new_pw = generate_temp_password()
                    new_bcrypt = hash_password_bcrypt(new_pw)
                    conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_bcrypt, sel))
                    conn.commit()

                    user_info = {
                        "id": sel,
                        "name": f"{rec['name']} {rec['surname']}",
                        "email": rec["email"],
                        "role": rec["role"],
                        "password_plain": new_pw,
                    }
                    send_welcome_comms(user_info)
                    st.success(f"Invite resent. New Temp PW: **{new_pw}**")
                except Exception as e:
                    st.error(f"Error resending credentials: {e}")

        with tab_activity:
            st.subheader("Recent Performance Snapshot")

            st.markdown("#### 🤖 Last 5 AI Submissions")
            subs_df = pd.read_sql_query(
                "SELECT timestamp as \"Date\", (data_json->>'safety_score') as \"Safety\", processed FROM submissions WHERE employee_id = %s ORDER BY timestamp DESC LIMIT 5",
                conn, params=(sel,)
            )
            if subs_df.empty:
                st.info("No submission history found.")
            else:
                st.dataframe(subs_df, use_container_width=True, hide_index=True)
