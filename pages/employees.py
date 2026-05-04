import streamlit as st
import pandas as pd
import secrets
from psycopg2 import IntegrityError
from core.activity_logger import log_activity
from core.auth import (
    create_user,
    hash_password as hash_password_bcrypt,
)  # Use bcrypt for all passwords
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

    # --- PRE-FETCH DATA FOR DROPDOWNS ---
    stations_df = pd.read_sql_query("SELECT id, name FROM stations ORDER BY name", conn)
    station_options = [(row["name"], row["id"]) for _, row in stations_df.iterrows()]

    regions_df = pd.read_sql_query("SELECT id, name FROM regions ORDER BY name", conn)
    region_options = [(row["name"], row["id"]) for _, row in regions_df.iterrows()]

    # --- 1. REGISTER NEW EMPLOYEE ---
    with st.expander("➕ Register New Employee"):
        role_options = [
            "Employee",
            "Gas Station Supervisor",
            "Gas Station Manager",
            "Region Manager",
            "General Manager",
        ]
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
            if role in ["Employee", "Gas Station Supervisor", "Gas Station Manager"]:
                assign_station = st.selectbox(
                    "Assign Station (Required)",
                    options=[(None, None)] + station_options,
                    format_func=lambda x: x[0] if x[0] else "Select a station...",
                )
                if assign_station:
                    assign_station_id = assign_station[1]

            elif role == "Region Manager":
                assign_region = st.selectbox(
                    "Assign Region (Required)",
                    options=[(None, None)] + region_options,
                    format_func=lambda x: x[0] if x[0] else "Select a region...",
                )
                if assign_region:
                    assign_region_id = assign_region[1]

            if st.form_submit_button("Create Employee & Send Invites"):
                if not first.strip() or not email.strip():
                    st.error("Name and email are required.")
                elif (
                    role
                    in ["Employee", "Gas Station Supervisor", "Gas Station Manager"]
                    and not assign_station_id
                ):
                    st.error("A station MUST be selected for this role.")
                elif role == "Region Manager" and not assign_region_id:
                    st.error("A region MUST be selected for this role.")
                else:
                    # Generate Credentials
                    temp_pw = generate_temp_password()  # Plain text for email

                    try:
                        # Create user directly in the unified 'users' table
                        user_data = create_user(
                            username=email.strip(),
                            password=temp_pw,  # create_user hashes it
                            email=email.strip(),
                            role=role,
                            name=first.strip(),
                            surname=last.strip(),
                            station_id=assign_station_id,
                            region_id=assign_region_id,
                        )
                        new_id = user_data["id"]

                        conn.commit()  # Commit after all inserts

                        log_activity(
                            conn, "CREATE_EMPLOYEE", f"Created {first} {last} ({role})"
                        )

                        # --- START LIFECYCLE: EMAIL & TELEGRAM ---
                        user_info = {
                            "id": new_id,
                            "name": f"{first} {last}",
                            "email": email.strip(),
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

    # --- 2. EMPLOYEE DIRECTORY ---
    st.subheader("Employee Directory")

    c_filter_1, c_filter_2 = st.columns([1, 2])
    with c_filter_1:
        # Filter by Region
        sel_region_filter = st.selectbox(
            "Filter by Region", ["All"] + [opt[0] for opt in region_options]
        )
    with c_filter_2:
        search_text = st.text_input(
            "Search (Name or Email)", placeholder="Type to filter..."
        )

    dir_query = """
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
    dir_params = []

    if sel_region_filter != "All":
        rid_filter = next(
            (opt[1] for opt in region_options if opt[0] == sel_region_filter), None
        )
        if rid_filter:
            dir_query += " AND (u.region_id = %s OR s.region_id = %s)"
            dir_params.extend([rid_filter, rid_filter])

    if search_text:
        like_pattern = f"%{search_text}%"
        dir_query += " AND (COALESCE(u.name,'') || ' ' || COALESCE(u.surname,'') LIKE %s OR u.email LIKE %s)"
        dir_params.extend([like_pattern, like_pattern])

    dir_query += " ORDER BY u.id"
    df = pd.read_sql_query(dir_query, conn, params=dir_params)

    if df.empty:
        st.info("No employees found.")
    else:
        # Displaying Telegram status visually
        df["TG Status"] = df["telegram_chat_id"].apply(
            lambda x: "🔗 Linked" if x else "❌ Unlinked"
        )

        # Custom Grid Layout for Directory
        cols = st.columns([0.5, 2, 2, 1.5, 1.5, 1, 0.8])
        fields = ["ID", "Name", "Email", "Role", "Station", "TG", "Action"]
        for col, field in zip(cols, fields):
            col.markdown(f"**{field}**")

        for _, row in df.iterrows():
            c1, c2, c3, c4, c5, c6, c7 = st.columns([0.5, 2, 2, 1.5, 1.5, 1, 0.8])
            c1.write(str(row["id"]))
            c2.write(row["fullname"])
            c3.write(row["email"])
            c4.write(row["role"])
            c5.write(row["station_name"] if row["station_name"] else "-")
            c6.write(row["TG Status"])

            if row["station_id"] and not pd.isna(row["station_id"]):
                if c7.button(
                    "⛽",
                    key=f"jump_st_{row['id']}",
                    help=f"Go to {row['station_name']}",
                ):
                    st.session_state["active_page"] = "Stations"
                    st.session_state["target_station_id"] = int(row["station_id"])
                    st.rerun()
            else:
                c7.write("-")

            if c7.button(
                "🕒", key=f"jump_shift_emp_{row['id']}", help="Open shift schedule"
            ):
                st.session_state["active_page"] = "Shifts"
                st.session_state["target_shift_employee_id"] = int(row["id"])
                st.rerun()

    # --- 3. EDIT / DELETE SECTION ---
    st.divider()
    st.subheader("✏️ Edit / Delete Employee")
    emp_ids = df["id"].tolist() if not df.empty else []

    # Handle navigation from other pages (persisting selection)
    sb_key = "emp_selector_main"
    if "target_employee_id" in st.session_state:
        tgt = st.session_state.pop("target_employee_id")
        if tgt in emp_ids:
            st.session_state[sb_key] = tgt

    if emp_ids:
        sel = st.selectbox(
            "Select employee",
            emp_ids,
            key=sb_key,
            format_func=lambda x: f"ID {x}: {df[df['id']==x]['fullname'].values[0]}",
        )
        rec = pd.read_sql_query(
            "SELECT * FROM users WHERE id = %s", conn, params=(sel,)
        ).iloc[0]

        with st.form(f"edit_emp_{sel}"):
            e_name = st.text_input("First name", value=rec["name"])
            e_surname = st.text_input("Surname", value=rec["surname"])
            e_email = st.text_input("Email", value=rec["email"])
            e_role = st.selectbox(
                "Role",
                role_options,
                index=(
                    role_options.index(rec["role"])
                    if rec["role"] in role_options
                    else 0
                ),
            )

            # --- Conditional Assignment Widgets for Edit Form ---
            e_station_id = None
            e_region_id = None

            if e_role in ["Employee", "Gas Station Supervisor", "Gas Station Manager"]:
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
                )
                if e_stat:
                    e_station_id = e_stat[1]

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
                )
                if e_reg:
                    e_region_id = e_reg[1]

            e_tg = st.text_input(
                "Telegram Chat ID (Manual Edit)", value=rec["telegram_chat_id"] or ""
            )

            if st.form_submit_button("Save Changes"):
                # Validation
                if (
                    e_role
                    in ["Employee", "Gas Station Supervisor", "Gas Station Manager"]
                    and not e_station_id
                ):
                    st.error("A station MUST be selected for this role.")
                elif e_role == "Region Manager" and not e_region_id:
                    st.error("A region MUST be selected for this role.")
                else:
                    try:
                        # For roles that don't use a field, set it to NULL
                        if e_role in [
                            "Employee",
                            "Gas Station Supervisor",
                            "Gas Station Manager",
                        ]:
                            region_row = conn.execute(
                                "SELECT region_id FROM stations WHERE id = %s",
                                (e_station_id,),
                            ).fetchone()
                            if not region_row or region_row[0] is None:
                                st.error(
                                    "Selected station must belong to a region before assigning this role."
                                )
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
                            "UPDATE users SET name=%s, surname=%s, email=%s, role=%s, station_id=%s, region_id=%s, telegram_chat_id=%s, username=%s WHERE id=%s",
                            (
                                e_name.strip(),
                                e_surname.strip(),
                                e_email.strip(),
                                e_role,
                                final_station_id,
                                final_region_id,
                                e_tg.strip() if e_tg.strip() else None,
                                e_email.strip(),
                                sel,
                            ),
                        )

                        conn.commit()
                        st.success("Changes saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        # Resend credentials / Invite to Telegram
        col_resend, col_del = st.columns(2)
        with col_resend:
            if st.button("🔄 Resend Invite / Reset PW"):
                try:
                    new_pw = generate_temp_password()

                    # Update the system user password (users table)
                    new_bcrypt = hash_password_bcrypt(new_pw)
                    conn.execute(
                        "UPDATE users SET password_hash = %s WHERE id = %s",
                        (new_bcrypt, sel),
                    )

                    conn.commit()

                    # Resend the welcome cycle
                    user_info = {
                        "id": sel,
                        "name": f"{rec['name']} {rec['surname']}",
                        "email": rec["email"],
                        "role": rec["role"],
                        "password_plain": new_pw,
                    }
                    send_welcome_comms(user_info)

                    st.success(f"Invite resent. New Temp PW: {new_pw}")
                except Exception as e:
                    st.error(f"Error resending invite: {e}")

        with col_del:
            if st.button("🗑️ Delete Employee Record"):
                try:
                    # Delete from users table
                    conn.execute("DELETE FROM users WHERE id = %s", (sel,))
                    conn.commit()
                    log_activity(conn, "DELETE_EMPLOYEE", f"Deleted ID {sel}")
                    st.success(f"Employee ID {sel} was successfully deleted.")
                    st.rerun()
                except IntegrityError:
                    st.error(
                        "Cannot delete employee: They are linked to existing submissions. Please reassign or remove linked records first."
                    )
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
