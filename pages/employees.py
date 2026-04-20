import streamlit as st
import pandas as pd
import hashlib
import secrets
from psycopg2 import IntegrityError
from core.activity_logger import log_activity
from core.auth import create_user, hash_password as hash_password_bcrypt
from ui.header import render_page_header
# Import the communication service logic
try:
    from core.comm_service import send_welcome_comms
except ImportError:
    # Fallback if service isn't created yet
    def send_welcome_comms(data): return None

def hash_password(password: str) -> str:
    """Legacy SHA256 hash for the 'employees' table password column."""
    return hashlib.sha256(password.encode()).hexdigest()

def generate_temp_password(n: int = 10) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(secrets.choice(alphabet) for _ in range(n))

def render(conn):
    render_page_header("👥 Employees")

    # --- PRE-FETCH DATA FOR DROPDOWNS ---
    stations_df = pd.read_sql_query("SELECT id, name FROM stations ORDER BY name", conn)
    station_options = [(row['name'], row['id']) for _, row in stations_df.iterrows()]

    regions_df = pd.read_sql_query("SELECT id, name FROM regions ORDER BY name", conn)
    region_options = [(row['name'], row['id']) for _, row in regions_df.iterrows()]

    # --- 1. REGISTER NEW EMPLOYEE ---
    with st.expander("➕ Register New Employee"):
        with st.form("add_emp", clear_on_submit=True):
            col1, col2 = st.columns(2)
            first = col1.text_input("First name")
            last = col2.text_input("Surname")
            email = st.text_input("Email")
            
            role_options = ["Employee", "Gas Station Supervisor", "Gas Station Manager", 
                            "Region Manager", "Region Director", "General Manager"]
            role = st.selectbox("Role", role_options)
            
            # --- Conditional Assignment Widgets ---
            assign_station_id = None
            assign_region_id = None
            assign_region_ids = [] # For Region Director

            if role in ["Employee", "Gas Station Supervisor", "Gas Station Manager"]:
                assign_station = st.selectbox(
                    "Assign Station (Required)",
                    options=[(None, None)] + station_options,
                    format_func=lambda x: x[0] if x[0] else "Select a station..."
                )
                if assign_station:
                    assign_station_id = assign_station[1]
            
            elif role == "Region Manager":
                assign_region = st.selectbox(
                    "Assign Region (Required)",
                    options=[(None, None)] + region_options,
                    format_func=lambda x: x[0] if x[0] else "Select a region..."
                )
                if assign_region:
                    assign_region_id = assign_region[1]

            elif role == "Region Director":
                assign_region_ids = st.multiselect(
                    "Assign Regions (Required)",
                    options=[opt[1] for opt in region_options],
                    format_func=lambda x: next((name for name, rid in region_options if rid == x), "Unknown")
                )
            
            if st.form_submit_button("Create Employee & Send Invites"):
                if not first.strip() or not email.strip():
                    st.error("Name and email are required.")
                elif role in ["Employee", "Gas Station Supervisor", "Gas Station Manager"] and not assign_station_id:
                    st.error("A station MUST be selected for this role.")
                elif role == "Region Manager" and not assign_region_id:
                    st.error("A region MUST be selected for this role.")
                elif role == "Region Director" and not assign_region_ids:
                    st.error("At least one region MUST be selected for this role.")
                else:
                    # Generate Credentials
                    temp_pw = generate_temp_password()
                    hashed = hash_password(temp_pw)
                    
                    try:
                        # 1. Create System User (for Login)
                        try:
                            # Use email as username to ensure uniqueness and simplicity
                            create_user(username=email.strip(), password=temp_pw, email=email.strip(), role=role)
                        except IntegrityError:
                            st.warning(f"Note: A user account for '{email.strip()}' already exists. Linking to new employee record.")
                        except Exception as e:
                            st.error(f"Failed to create login account: {e}")
                            st.stop()

                        cursor = conn.execute(
                            "INSERT INTO employees (name, surname, email, password, role, station_id, region_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                            (first.strip(), last.strip(), email.strip(), hashed, role, assign_station_id, assign_region_id)
                        )
                        new_id = cursor.fetchone()[0]

                        # Handle Region Director M2M relationship
                        if role == "Region Director" and assign_region_ids:
                            for region_id in assign_region_ids:
                                conn.execute(
                                    "INSERT INTO director_regions (employee_id, region_id) VALUES (%s, %s)",
                                    (new_id, region_id)
                                )
                        conn.commit() # Commit after all inserts
                        
                        log_activity(conn, "CREATE_EMPLOYEE", f"Created {first} {last} ({role})")

                        # --- START LIFECYCLE: EMAIL & TELEGRAM ---
                        user_info = {
                            "id": new_id,
                            "name": f"{first} {last}",
                            "email": email.strip(),
                            "role": role,
                            "password_plain": temp_pw
                        }
                        
                        # This function handles the Email + Telegram logic
                        tg_link = send_welcome_comms(user_info)
                        
                        st.success(f"✅ {first} {last} registered successfully!")
                        st.info(f"🔑 Temporary Password: **{temp_pw}** (Sent via Email)")
                        
                        if tg_link:
                            st.warning(f"📲 Telegram Registration Required: [Register Bot]({tg_link})")
                            st.toast("Telegram invitation generated.", icon="🤖")
                        
                        st.balloons()
                    except Exception as e:
                        st.error(f"Database error: {e}")

    # --- 2. EMPLOYEE DIRECTORY ---
    st.subheader("Employee Directory")

    c_filter_1, c_filter_2 = st.columns([1, 2])
    with c_filter_1:
        # Filter by Region
        sel_region_filter = st.selectbox("Filter by Region", ["All"] + [opt[0] for opt in region_options])
    with c_filter_2:
        search_text = st.text_input("Search (Name or Email)", placeholder="Type to filter...")

    dir_query = """
        SELECT e.id, e.name || ' ' || e.surname as fullname, e.email, e.role, 
               s.name as station_name, e.station_id, COALESCE(r.name, rs.name) as region_name, e.telegram_chat_id
        FROM employees e
        LEFT JOIN stations s ON e.station_id = s.id
        LEFT JOIN regions r ON e.region_id = r.id
        LEFT JOIN regions rs ON s.region_id = rs.id
        WHERE 1=1
    """
    dir_params = []

    if sel_region_filter != "All":
        rid_filter = next((opt[1] for opt in region_options if opt[0] == sel_region_filter), None)
        if rid_filter:
            dir_query += " AND (e.region_id = ? OR s.region_id = ? OR e.id IN (SELECT employee_id FROM director_regions WHERE region_id = ?))"
            dir_params.extend([rid_filter, rid_filter, rid_filter])

    if search_text:
        like_pattern = f"%{search_text}%"
        dir_query += " AND (e.name || ' ' || e.surname LIKE ? OR e.email LIKE ?)"
        dir_params.extend([like_pattern, like_pattern])

    dir_query += " ORDER BY e.id"
    df = pd.read_sql_query(dir_query, conn, params=dir_params)

    if df.empty:
        st.info("No employees found.")
    else:
        # Displaying Telegram status visually
        df['TG Status'] = df['telegram_chat_id'].apply(lambda x: "🔗 Linked" if x else "❌ Unlinked")
        
        # Custom Grid Layout for Directory
        cols = st.columns([0.5, 2, 2, 1.5, 1.5, 1, 0.8])
        fields = ["ID", "Name", "Email", "Role", "Station", "TG", "Action"]
        for col, field in zip(cols, fields):
            col.markdown(f"**{field}**")
            
        for _, row in df.iterrows():
            c1, c2, c3, c4, c5, c6, c7 = st.columns([0.5, 2, 2, 1.5, 1.5, 1, 0.8])
            c1.write(str(row['id']))
            c2.write(row['fullname'])
            c3.write(row['email'])
            c4.write(row['role'])
            c5.write(row['station_name'] if row['station_name'] else "-")
            c6.write(row['TG Status'])
            
            if row['station_id'] and not pd.isna(row['station_id']):
                if c7.button("⛽", key=f"jump_st_{row['id']}", help=f"Go to {row['station_name']}"):
                    st.session_state["active_page"] = "Stations"
                    st.session_state["target_station_id"] = int(row['station_id'])
                    st.rerun()
            else:
                c7.write("-")

            if c7.button("🕒", key=f"jump_shift_emp_{row['id']}", help="Open shift schedule"):
                st.session_state["active_page"] = "Shifts"
                st.session_state["target_shift_employee_id"] = int(row['id'])
                st.rerun()

    # --- 3. EDIT / DELETE SECTION ---
    st.divider()
    st.subheader("✏️ Edit / Delete Employee")
    emp_ids = df['id'].tolist() if not df.empty else []
    
    # Handle navigation from other pages (persisting selection)
    sb_key = "emp_selector_main"
    if "target_employee_id" in st.session_state:
        tgt = st.session_state.pop("target_employee_id")
        if tgt in emp_ids:
            st.session_state[sb_key] = tgt

    if emp_ids:
        sel = st.selectbox("Select employee", emp_ids, key=sb_key,
                           format_func=lambda x: f"ID {x}: {df[df['id']==x]['fullname'].values[0]}")
        rec = pd.read_sql_query("SELECT * FROM employees WHERE id = %s", conn, params=(sel,)).iloc[0]
        
        with st.form(f"edit_emp_{sel}"):
            e_name = st.text_input("First name", value=rec['name'])
            e_surname = st.text_input("Surname", value=rec['surname'])
            e_email = st.text_input("Email", value=rec['email'])
            e_role = st.selectbox("Role", role_options, index=role_options.index(rec['role']) if rec['role'] in role_options else 0)

            # --- Conditional Assignment Widgets for Edit Form ---
            e_station_id = None
            e_region_id = None
            e_region_ids = []

            if e_role in ["Employee", "Gas Station Supervisor", "Gas Station Manager"]:
                curr_stat_idx = next((i + 1 for i, opt in enumerate(station_options) if opt[1] == rec['station_id']), 0)
                e_stat = st.selectbox("Station (Required)", options=[(None, None)] + station_options, index=curr_stat_idx, format_func=lambda x: x[0] if x[0] else "Select a station...")
                if e_stat: e_station_id = e_stat[1]

            elif e_role == "Region Manager":
                curr_reg_idx = next((i + 1 for i, opt in enumerate(region_options) if opt[1] == rec['region_id']), 0)
                e_reg = st.selectbox("Region (Required)", options=[(None, None)] + region_options, index=curr_reg_idx, format_func=lambda x: x[0] if x[0] else "Select a region...")
                if e_reg: e_region_id = e_reg[1]

            elif e_role == "Region Director":
                current_director_regions = pd.read_sql_query(
                    "SELECT region_id FROM director_regions WHERE employee_id = %s", conn, params=(sel,)
                )['region_id'].tolist()
                
                e_region_ids = st.multiselect(
                    "Regions (Required)",
                    options=[opt[1] for opt in region_options],
                    default=current_director_regions,
                    format_func=lambda x: next((name for name, rid in region_options if rid == x), "Unknown")
                )
            
            e_tg = st.text_input("Telegram Chat ID (Manual Edit)", value=rec['telegram_chat_id'] or "")
            
            if st.form_submit_button("Save Changes"):
                # Validation
                if e_role in ["Employee", "Gas Station Supervisor", "Gas Station Manager"] and not e_station_id:
                    st.error("A station MUST be selected for this role.")
                elif e_role == "Region Manager" and not e_region_id:
                    st.error("A region MUST be selected for this role.")
                elif e_role == "Region Director" and not e_region_ids:
                    st.error("At least one region MUST be selected for this role.")
                else:
                    try:
                        # For roles that don't use a field, set it to NULL
                        final_station_id = e_station_id if e_role in ["Employee", "Gas Station Supervisor", "Gas Station Manager"] else None
                        final_region_id = e_region_id if e_role == "Region Manager" else None

                        conn.execute("UPDATE employees SET name=%s, surname=%s, email=%s, role=%s, station_id=%s, region_id=%s, telegram_chat_id=%s WHERE id=%s", (e_name.strip(), e_surname.strip(), e_email.strip(), e_role, final_station_id, final_region_id, e_tg.strip() if e_tg.strip() else None, sel))
                        
                        # Handle Region Director M2M relationship by clearing and re-inserting
                        conn.execute("DELETE FROM director_regions WHERE employee_id = %s", (sel,))
                        if e_role == "Region Director" and e_region_ids:
                            for region_id in e_region_ids:
                                conn.execute("INSERT INTO director_regions (employee_id, region_id) VALUES (%s, %s)", (sel, region_id))
                        
                        conn.execute("UPDATE users SET role=%s, email=%s, username=%s WHERE email=%s", (e_role, e_email.strip(), e_email.strip(), rec['email']))
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
                    conn.execute("UPDATE employees SET password = %s WHERE id = %s", (hash_password(new_pw), sel))
                    
                    # Also update the system user password (users table)
                    new_bcrypt = hash_password_bcrypt(new_pw)
                    conn.execute("UPDATE users SET password_hash = %s WHERE email = %s", (new_bcrypt, rec['email']))
                    
                    conn.commit()
                    
                    # Resend the welcome cycle
                    user_info = {"id": sel, "name": f"{rec['name']} {rec['surname']}", "email": rec['email'], "role": rec['role'], "password_plain": new_pw}
                    send_welcome_comms(user_info)
                    
                    st.success(f"Invite resent. New Temp PW: {new_pw}")
                except Exception as e:
                    st.error(f"Error resending invite: {e}")
        
        with col_del:
            if st.button("🗑️ Delete Employee Record"):
                try:
                    conn.execute("DELETE FROM employees WHERE id = %s", (sel,))
                    conn.commit()
                    log_activity(conn, "DELETE_EMPLOYEE", f"Deleted ID {sel}")
                    st.success(f"Employee ID {sel} was successfully deleted.")
                    st.rerun()
                except IntegrityError:
                    st.error("Cannot delete employee: They are linked to existing submissions. Please reassign or remove linked records first.")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
