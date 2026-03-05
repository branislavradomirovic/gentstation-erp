import streamlit as st
import pandas as pd
import sqlite3
import folium
from streamlit_folium import st_folium
import hashlib
import secrets
import string
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# --- INITIALIZATION ---
load_dotenv()
st.set_page_config(page_title="GentStation ERP", layout="wide")
conn = sqlite3.connect('company.db', check_same_thread=False)
conn.execute("PRAGMA foreign_keys = ON;")

# --- AUTHENTICATION & SECURITY ---
if 'auth_status' not in st.session_state:
    st.session_state.auth_status = False
    st.session_state.user_email = None
    st.session_state.user_role = None
    st.session_state.user_id = None
    st.session_state.user_name = None

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def generate_temp_password():
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(10))

# --- MAILER LOGIC ---
def send_invitation_email(recipient_email, name, temp_pw, role, station_id=None):
    sender = os.getenv("SENDER_EMAIL")
    password = os.getenv("SENDER_PASSWORD")
    app_url = os.getenv("APP_URL", "http://localhost:8501")
    telegram_url = os.getenv("TELEGRAM_BOT_URL", "https://t.me/YourGentStationBot") # Add to .env

    if not sender or not password:
        st.error("Environment variables SENDER_EMAIL or SENDER_PASSWORD missing.")
        return False
    
    if station_id:
        telegram_link = f"{os.getenv('TELEGRAM_BOT_URL')}?start={station_id}"
    else:
        telegram_link = os.getenv('TELEGRAM_BOT_URL')

    msg = MIMEMultipart()
    msg['From'] = f"GentStation Administration <{sender}>"
    msg['To'] = recipient_email
    msg['Subject'] = f"Welcome to GentStation, {name}! | Credentials"
# Role-based Telegram instructions
    telegram_section = ""
    if role in ["Employee", "Gas Station Supervisor"]:
        telegram_section = f"""
        <div style="margin-top: 20px; padding: 15px; border: 2px dashed #0088cc; border-radius: 10px; background-color: #f0f9ff;">
            <h3 style="color: #0088cc; margin-top: 0;">📹 Video Reporting Active</h3>
            <p>To register this device for reporting, click the button below and then press <b>START</b> in Telegram:</p>
            <p style="text-align: center;">
                <a href="{telegram_link}" style="display: inline-block; padding: 10px 25px; background-color: #0088cc; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">🚀 Register Device on Telegram</a>
            </p>
        </div>
        """

    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #eee; padding: 20px;">
            <h2 style="color: #1f77b4;">Account Created</h2>
            <p>Hello <b>{name}</b>, you have been registered as <b>{role}</b>.</p>
            <p><b>Login:</b> {recipient_email}<br>
            <b>Password:</b> <code>{temp_pw}</code></p>
            <p style="text-align: center; margin: 20px 0;">
                <a href="{app_url}" style="padding: 10px 20px; background-color: #1f77b4; color: white; text-decoration: none; border-radius: 5px;">Access Portal</a>
            </p>
            {telegram_section}
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(body, 'html'))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls() 
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Gmail Error: {e}")
        return False

# --- CRUD HELPERS ---
def delete_item(table, item_id):
    try:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
        conn.commit()
        st.success(f"Item {item_id} deleted.")
        st.rerun()
    except Exception as e:
        st.error(f"Cannot delete: Item is linked to other records.")

# --- LOGIN SCREEN ---
def login_screen():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("⛽ GentStation Portal")
        with st.container(border=True):
            email = st.text_input("Email / Username")
            pw = st.text_input("Password", type="password")
            if st.button("Log In", use_container_width=True):
                user = conn.execute(
                    "SELECT id, name, role FROM employees WHERE email = ? AND password = ?", 
                    (email, hash_password(pw))
                ).fetchone()
                if user:
                    st.session_state.auth_status = True
                    st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = user
                    st.rerun()
                else:
                    st.error("Invalid credentials.")

# --- MAIN APP GATE ---
if not st.session_state.auth_status:
    login_screen()
else:
    # Sidebar
    with st.sidebar:
        st.title("🛡️ GentStation ERP")
        st.write(f"Logged in as: **{st.session_state.user_name}**")
        st.caption(f"Role: {st.session_state.user_role}")
        if st.button("🚪 Logout"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    # RBAC Tab Filtering
    role = st.session_state.user_role
    if role == "General Manager":
        tab_list = ["📊 Dashboard", "🌍 Regions", "⛽ Stations", "👥 Employees"]
    elif role in ["Region Director", "Region Manager"]:
        tab_list = ["📊 Dashboard", "⛽ Stations", "👥 Employees"]
    else:
        tab_list = ["📊 My Dashboard"]
    
    tabs = st.tabs(tab_list)

    # --- 1. DASHBOARD ---
    with tabs[0]:
        st.subheader("📊 Network Oversight")
        c1, c2, c3 = st.columns(3)
        c1.metric("Regions", conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0])
        c2.metric("Stations", conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0])
        c3.metric("Total Staff", conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0])
        
        m = folium.Map(location=[44.7866, 20.4489], zoom_start=6)
        stations_df = pd.read_sql_query("SELECT name, lat, lon, category FROM stations", conn)
        for _, s in stations_df.iterrows():
            folium.Marker([s['lat'], s['lon']], tooltip=s['name']).add_to(m)
        st_folium(m, width="100%", height=400)

    # --- 2. REGIONS (GM ONLY) ---
    if role == "General Manager":
        with tabs[1]:
            st.subheader("🌍 Region Management")
            with st.expander("➕ Add New Region"):
                with st.form("reg_add"):
                    r_name, r_mail = st.text_input("Region Name"), st.text_input("Group Email")
                    if st.form_submit_button("Save Region"):
                        conn.execute("INSERT INTO regions (name, email) VALUES (?,?)", (r_name, r_mail))
                        conn.commit()
                        st.rerun()
            df_reg = pd.read_sql_query("SELECT * FROM regions", conn)
            st.dataframe(df_reg, use_container_width=True)

    # --- 3. STATIONS ---
    if role in ["General Manager", "Region Director", "Region Manager"]:
        idx = 2 if role == "General Manager" else 1
        with tabs[idx]:
            st.subheader("⛽ Gas Station Management")
            df_stat = pd.read_sql_query("SELECT s.*, r.name as region FROM stations s JOIN regions r ON s.region_id = r.id", conn)
            st.dataframe(df_stat, use_container_width=True)

    # --- 4. EMPLOYEES ---
    if role in ["General Manager", "Region Director", "Region Manager"]:
        idx = 3 if role == "General Manager" else 2
        with tabs[idx]:
            st.subheader("👥 Workforce Management")
            
            # --- CREATE SECTION ---
            with st.expander("➕ Register New Employee"):
                role_new = st.selectbox("Role", [
                 "Employee", "Gas Station Supervisor", "Gas Station Manager", 
                 "Region Manager", "Region Director", "General Manager"
                ], key="new_role_sel")

                s_id_new = None
                r_id_new = None
                director_reg_ids_new = []

                with st.form("emp_add"):
                    col1, col2 = st.columns(2)
                    e_name = col1.text_input("First Name")
                    e_sur = col2.text_input("Surname")
                    e_mail = st.text_input("Email")
            
                    if role_new in ["Employee", "Gas Station Supervisor", "Gas Station Manager"]:
                        stats = {s[1]: s[0] for s in conn.execute("SELECT id, name FROM stations").fetchall()}
                        if stats:
                            s_choice = st.selectbox("Assign to Station", list(stats.keys()))
                            s_id_new = stats[s_choice]
            
                    elif role_new == "Region Manager":
                        regs = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM regions").fetchall()}
                        if regs:
                            r_choice = st.selectbox("Assign to Region", list(regs.keys()))
                            r_id_new = regs[r_choice]

                    elif role_new == "Region Director":
                        regs = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM regions").fetchall()}
                        if regs:
                            u_choices = st.multiselect("Region Oversight", list(regs.keys()))
                            director_reg_ids_new = [regs[name] for name in u_choices]

                    if st.form_submit_button("Create & Send Invitation"):
                        if not e_mail or not e_name:
                            st.error("Please fill in Name and Email.")
                        else:
                            pw = generate_temp_password()
                            cursor = conn.execute("""
                                INSERT INTO employees (name, surname, email, password, role, station_id, region_id) 
                                VALUES (?,?,?,?,?,?,?)
                                """, (e_name, e_sur, e_mail, hash_password(pw), role_new, s_id_new, r_id_new))
                            new_id = cursor.lastrowid
                            if role_new == "Region Director":
                                for rid in director_reg_ids_new:
                                    conn.execute("INSERT INTO director_regions (employee_id, region_id) VALUES (?,?)", (new_id, rid))
                            conn.commit()
                            if send_invitation_email(e_mail, e_name, pw, role_new,s_id_new):
                                st.success(f"✅ Created! PW: {pw}")
                            st.rerun()

            # --- VIEW & SEARCH SECTION ---
            st.divider()
            search_query = st.text_input("🔍 Search Employees (Name, Email, or Role)", "").lower()
            
            df_emp = pd.read_sql_query("""
                SELECT e.id, e.name, e.surname, e.email, e.role, s.name as assigned_station,
                COALESCE(rd.name, ri.name) as region_assigned
                FROM employees e
                LEFT JOIN stations s ON e.station_id = s.id
                LEFT JOIN regions rd ON e.region_id = rd.id
                LEFT JOIN regions ri ON s.region_id = ri.id
            """, conn)

            # Apply Search Filter
            if search_query:
                mask = df_emp.apply(lambda row: search_query in str(row['name']).lower() or 
                                               search_query in str(row['surname']).lower() or 
                                               search_query in str(row['email']).lower() or 
                                               search_query in str(row['role']).lower(), axis=1)
                filtered_df = df_emp[mask]
            else:
                filtered_df = df_emp

            st.dataframe(filtered_df, use_container_width=True)
                
            # --- EDIT / DELETE / RESEND SECTION ---
            if not df_emp.empty:
                st.divider()
                st.write("### ✏️ Manage Existing Staff")
    
                target_e = st.selectbox(
                    "Select ID to Edit", 
                    df_emp['id'], 
                    format_func=lambda x: f"ID {x}: {df_emp[df_emp['id']==x]['email'].values[0]}", 
                    key="staff_manage_selectbox"
                )
    
                if "last_target_e" not in st.session_state or st.session_state.last_target_e != target_e:
                    st.session_state.last_target_e = target_e
                    st.session_state.resend_msg = None

                curr = pd.read_sql_query(f"SELECT * FROM employees WHERE id={target_e}", conn).iloc[0]
    
                if st.session_state.get('resend_msg'):
                    st.success(st.session_state.resend_msg)

                c_actions, _ = st.columns([2, 2])
                with c_actions:
                    c_del, c_resend = st.columns(2)
        
                    if c_del.button("🗑️ Delete staff", use_container_width=True, key=f"del_btn_{target_e}"):
                        delete_item("employees", target_e)
                    
                    if c_resend.button("📧 Resend Mail", use_container_width=True, key=f"resend_btn_{target_e}"):
                        with st.spinner("🔄 Updating & Sending..."):
                            new_pw = generate_temp_password()
                            conn.execute("UPDATE employees SET password=? WHERE id=?", (hash_password(new_pw), int(target_e)))
                            conn.commit()
                            
                            success = send_invitation_email(curr['email'], curr['name'], new_pw, curr['role'], curr['station_id'])
                            if success:
                                st.session_state.resend_msg = f"✅ New credentials sent to {curr['email']}! (PW: {new_pw})"
                            else:
                                st.session_state.resend_msg = "❌ SMTP Error: Check your .env credentials."
                            st.rerun()

                # --- THE FULL EDIT FORM ---
                with st.expander("📝 Edit Full Profile Details", expanded=True):
                    with st.form(key=f"full_edit_form_v5_{target_e}"):
                        col1, col2 = st.columns(2)
                        u_n = col1.text_input("Name", value=str(curr['name']))
                        u_s = col2.text_input("Surname", value=str(curr['surname']))
                        u_m = st.text_input("Email", value=str(curr['email']))
                        
                        roles_list = ["Employee", "Gas Station Supervisor", "Gas Station Manager", 
                                      "Region Manager", "Region Director", "General Manager"]
                        u_role = st.selectbox("Update Role", roles_list, index=roles_list.index(curr['role']))

                        u_s_id, u_r_id = curr['station_id'], curr['region_id']
                        u_dir_reg_ids = []

                        if u_role in ["Employee", "Gas Station Supervisor", "Gas Station Manager"]:
                            stats = {s[1]: s[0] for s in conn.execute("SELECT id, name FROM stations").fetchall()}
                            if stats:
                                stat_names = list(stats.keys())
                                curr_stat_match = [n for n, id in stats.items() if id == curr['station_id']]
                                idx_s = stat_names.index(curr_stat_match[0]) if curr_stat_match else 0
                                u_s_choice = st.selectbox("Station", stat_names, index=idx_s)
                                u_s_id, u_r_id = stats[u_s_choice], None

                        elif u_role == "Region Manager":
                            regs = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM regions").fetchall()}
                            if regs:
                                reg_names = list(regs.keys())
                                curr_reg_match = [n for n, id in regs.items() if id == curr['region_id']]
                                idx_r = reg_names.index(curr_reg_match[0]) if curr_reg_match else 0
                                u_r_choice = st.selectbox("Region", reg_names, index=idx_r)
                                u_r_id, u_s_id = regs[u_r_choice], None

                        elif u_role == "Region Director":
                            regs = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM regions").fetchall()}
                            existing = [r[0] for r in conn.execute("SELECT region_id FROM director_regions WHERE employee_id=?", (int(target_e),)).fetchall()]
                            defaults = [name for name, id in regs.items() if id in existing]
                            u_choices = st.multiselect("Region Oversight", list(regs.keys()), default=defaults)
                            u_dir_reg_ids = [regs[name] for name in u_choices]
                            u_s_id, u_r_id = None, None

                        if st.form_submit_button("💾 Save Changes"):
                            conn.execute("""
                                UPDATE employees SET name=?, surname=?, email=?, role=?, station_id=?, region_id=? WHERE id=?
                            """, (u_n, u_s, u_m, u_role, u_s_id, u_r_id, int(target_e)))
                            if u_role == "Region Director":
                                conn.execute("DELETE FROM director_regions WHERE employee_id=?", (int(target_e),))
                                for rid in u_dir_reg_ids:
                                    conn.execute("INSERT INTO director_regions (employee_id, region_id) VALUES (?,?)", (int(target_e), rid))
                            conn.commit()
                            st.session_state.resend_msg = "✅ Record updated successfully!"
                            st.rerun()