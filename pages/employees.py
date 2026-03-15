import streamlit as st
import pandas as pd
import hashlib
import sqlite3
import secrets
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
            
            c3, c4 = st.columns(2)
            assign_station = c3.selectbox(
                "Assign station (optional)", 
                options=[(None, None)] + station_options,
                format_func=lambda x: x[0] if x[0] else "None"
            )
            assign_region = c4.selectbox(
                "Assign region (optional)", 
                options=[(None, None)] + region_options,
                format_func=lambda x: x[0] if x[0] else "None"
            )
            
            if st.form_submit_button("Create Employee & Send Invites"):
                if not first.strip() or not email.strip():
                    st.error("Name and email are required.")
                else:
                    # Generate Credentials
                    temp_pw = generate_temp_password()
                    hashed = hash_password(temp_pw)
                    
                    try:
                        # 1. Create System User (for Login)
                        try:
                            # Use email as username to ensure uniqueness and simplicity
                            create_user(username=email.strip(), password=temp_pw, email=email.strip(), role=role)
                        except sqlite3.IntegrityError:
                            st.warning(f"Note: A user account for '{email.strip()}' already exists. Linking to new employee record.")
                        except Exception as e:
                            st.error(f"Failed to create login account: {e}")
                            st.stop()

                        cursor = conn.execute(
                            "INSERT INTO employees (name, surname, email, password, role, station_id, region_id) VALUES (?,?,?,?,?,?,?)",
                            (first.strip(), last.strip(), email.strip(), hashed, role, assign_station[1], assign_region[1])
                        )
                        new_id = cursor.lastrowid
                        conn.commit()
                        
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
    df = pd.read_sql_query("""
        SELECT e.id, e.name || ' ' || e.surname as fullname, e.email, e.role, 
               s.name as station_name, r.name as region_name, e.telegram_chat_id
        FROM employees e
        LEFT JOIN stations s ON e.station_id = s.id
        LEFT JOIN regions r ON e.region_id = r.id
        ORDER BY e.id
    """, conn)

    st.subheader("Employee Directory")
    if df.empty:
        st.info("No employees found.")
    else:
        # Displaying Telegram status visually
        df['TG Status'] = df['telegram_chat_id'].apply(lambda x: "🔗 Linked" if x else "❌ Unlinked")
        st.dataframe(df[['id', 'fullname', 'role', 'station_name', 'TG Status', 'email']], 
                     use_container_width=True, hide_index=True)

    # --- 3. EDIT / DELETE SECTION ---
    st.divider()
    st.subheader("✏️ Edit / Delete Employee")
    emp_ids = df['id'].tolist() if not df.empty else []
    
    if emp_ids:
        sel = st.selectbox("Select employee", emp_ids, 
                           format_func=lambda x: f"ID {x}: {df[df['id']==x]['fullname'].values[0]}")
        rec = pd.read_sql_query("SELECT * FROM employees WHERE id = ?", conn, params=(sel,)).iloc[0]
        
        with st.form(f"edit_emp_{sel}"):
            e_name = st.text_input("First name", value=rec['name'])
            e_surname = st.text_input("Surname", value=rec['surname'])
            e_email = st.text_input("Email", value=rec['email'])
            e_role = st.selectbox("Role", role_options, index=role_options.index(rec['role']) if rec['role'] in role_options else 0)
            
            # Helper to find index of current selection
            curr_stat_idx = 0
            if rec['station_id']:
                for i, opt in enumerate(station_options):
                    if opt[1] == rec['station_id']:
                        curr_stat_idx = i + 1 # +1 because of None option
            
            curr_reg_idx = 0
            if rec['region_id']:
                for i, opt in enumerate(region_options):
                    if opt[1] == rec['region_id']:
                        curr_reg_idx = i + 1

            e_stat = st.selectbox("Station", options=[(None, None)] + station_options, index=curr_stat_idx, format_func=lambda x: x[0] if x[0] else "None")
            e_reg = st.selectbox("Region", options=[(None, None)] + region_options, index=curr_reg_idx, format_func=lambda x: x[0] if x[0] else "None")
            
            e_tg = st.text_input("Telegram Chat ID (Manual Edit)", value=rec['telegram_chat_id'] or "")
            
            if st.form_submit_button("Save Changes"):
                try:
                    conn.execute("""
                        UPDATE employees SET name=?, surname=?, email=?, role=?, station_id=?, region_id=?, telegram_chat_id=? 
                        WHERE id=?
                    """, (e_name.strip(), e_surname.strip(), e_email.strip(), e_role, 
                          e_stat[1], e_reg[1], 
                          e_tg.strip() if e_tg.strip() else None, sel))
                    
                    # Sync changes to users table (permissions & login username)
                    conn.execute("UPDATE users SET role=?, email=?, username=? WHERE email=?", 
                                 (e_role, e_email.strip(), e_email.strip(), rec['email']))

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
                    conn.execute("UPDATE employees SET password = ? WHERE id = ?", (hash_password(new_pw), sel))
                    
                    # Also update the system user password (users table)
                    new_bcrypt = hash_password_bcrypt(new_pw)
                    conn.execute("UPDATE users SET password_hash = ? WHERE email = ?", (new_bcrypt, rec['email']))
                    
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
                    conn.execute("DELETE FROM employees WHERE id = ?", (sel,))
                    conn.commit()
                    log_activity(conn, "DELETE_EMPLOYEE", f"Deleted ID {sel}")
                    st.success(f"Employee ID {sel} was successfully deleted.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Cannot delete employee: They are linked to existing submissions. Please reassign or remove linked records first.")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")