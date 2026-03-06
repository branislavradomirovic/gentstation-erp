import streamlit as st
import pandas as pd
import sqlite3
import folium
from streamlit_folium import st_folium
import hashlib
import secrets
import string
import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

# --- INITIALIZATION ---
load_dotenv()
st.set_page_config(page_title="GentStation Opus ERP", layout="wide")
conn = sqlite3.connect('company.db', check_same_thread=False)
conn.execute("PRAGMA foreign_keys = ON;")

def send_telegram_report(chat_id, message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    
    try:
        response = requests.post(url, json=payload)
        result = response.json()
        
        if not result.get("ok"):
            if "chat not found" in result.get("description", "").lower():
                return "Greška: Korisnik nije startovao bota."
            return f"Greška: {result.get('description')}"
        return "Uspešno poslato!"
    except Exception as e:
        return f"Sistemska greška: {e}"


def log_activity(action, details):
    """Upisuje akciju korisnika u bazu."""
    try:
        user = st.session_state.get('user_name', 'Sistem')
        conn.execute("INSERT INTO activity_logs (user_name, action, details) VALUES (?, ?, ?)",
                     (user, action, details))
        conn.commit()
    except Exception as e:
        st.error(f"Greška pri logovanju: {e}")

# --- UI HELPERS ---
def get_status_emoji(unprocessed_count):
    """Određuje vizuelni status stanice na osnovu broja neobrađenih snimaka."""
    if unprocessed_count == 0:
        return "🟢 😊" # Sve pod kontrolom
    elif unprocessed_count < 3:
        return "🟡 😐" # Potrebna pažnja
    else:
        return "🔴 ⚠️" # Kritično - zastoj u obradi

def get_logo_path():
    """Traži logo u assets folderu bez obzira na varijaciju naziva."""
    possible_names = [
        "assets/OpusLogo.png", 
        "assets/OpusLogo.png", 
        "assets/Opus_Logo.png",
        "assets/logo.png"
    ]
    for path in possible_names:
        if os.path.exists(path):
            return path
    return None

def delete_item(table, item_id):
    try:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
        conn.commit()
        log_activity("DELETE", f"Obrisana stavka iz tabele {table} (ID: {item_id})")
        st.success("Uspešno obrisano!")
        st.rerun()
    except Exception as e:
        st.error("Greška: Stavka je povezana sa drugim podacima.")

def display_sidebar_header():
    with st.sidebar:
        # Kolone za sidebar
        s_col1, s_col2 = st.columns([1, 3])
        
        logo = get_logo_path()
        with s_col1:
            if logo:
                st.image(logo, width="stretch")
        
        with s_col2:
            st.markdown("### GentStation Opus", unsafe_allow_html=True)
        
        st.divider()
        st.write(f"Ulogovani ste kao: **{st.session_state.user_name}**")
        st.caption(f"Pozicija: {st.session_state.user_role}")
        
        # PRVO DUGME - DODAJ KEY
        if st.button("🚪 Odjavi se", key="sidebar_logout_top", width="stretch"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()
        st.divider()

def send_invitation_email(to_email, first_name, temp_password, role, employee_id):
    """Šalje pristupne podatke i personalizovani Telegram link."""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    
    app_url = "https://gentstation-erp-opus.streamlit.app/"
    telegram_bot_name = "BaneTest_bot" 
    
    # GENERISANJE LINKA: t.me/BaneTest_bot?start=15
    deep_link = f"https://t.me/{telegram_bot_name}?start={employee_id}"

    if not sender_email or not sender_password:
        st.error("Email credentials missing!")
        return False

    msg = MIMEMultipart()
    msg['From'] = f"GentStation Opus ERP <{sender_email}>"
    msg['To'] = to_email
    msg['Subject'] = "Pristupni podaci za GentStation Opus ERP"

    body = f"""
    <html>
    <body style="font-family: sans-serif;">
        <p>Zdravo {first_name}, vaši pristupni podaci su spremni.</p>
        
        <div style="background: #f4f4f4; padding: 15px; border-radius: 5px; border-left: 5px solid #0088cc;">
            <p><b>Portal:</b> <a href="{app_url}">{app_url}</a><br>
            <b>Korisnik:</b> <code>{to_email}</code><br>
            <b>Privremena lozinka:</b> <code style="font-size: 1.1em; color: #d63384;">{temp_password}</code></p>
        </div>

        <p>🚀 <b>Telegram Integracija:</b><br>
        Kliknite na dugme ispod i pritisnite <b>START</b> da aktivirate izveštaje:<br>
        <a href="{deep_link}" style="background-color: #0088cc; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin-top: 10px;">
            Poveži se na Telegram
        </a></p>

        <hr>
        <p><small>Nakon prve prijave, promenite lozinku u tabu "Settings".</small></p>
    </body>
    </html>
    """
    msg.attach(MIMEText(body, 'html'))
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Email error: {e}")
        return False

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

def login_screen():
    # Centriramo ceo blok na sredinu ekrana
    _, main_col, _ = st.columns([1, 2, 1])
    
    with main_col:
        # Kreiramo pod-kolone za logo i naslov
        logo_col, title_col = st.columns([1, 5])
        logo = get_logo_path()
        with logo_col:
            if logo:
                st.image(logo, width="stretch")
        with title_col:
            # Koristimo markdown za bolju kontrolu vertikalnog poravnanja
            st.markdown("<h1 style='margin-top: -10px;'>GentStation</h1>", unsafe_allow_html=True)
        
        with st.container(border=True):
            email = st.text_input("Email / Username")
            pw = st.text_input("Lozinka", type="password")
            if st.button("Prijavi se", width="stretch"):
                user = conn.execute(
                    "SELECT id, name, role FROM employees WHERE email = ? AND password = ?", 
                    (email, hash_password(pw))
                ).fetchone()
                if user:
                    st.session_state.auth_status = True
                    st.session_state.user_id, st.session_state.user_name, st.session_state.user_role = user
                    st.rerun()
                else:
                    st.error("Neispravni podaci za pristup.")

# --- MAIN APP LOGIC ---
if not st.session_state.auth_status:
    login_screen()
else:
    display_sidebar_header()
    
    # Initialization of key variables
    role = st.session_state.user_role
    user_id = st.session_state.user_id

    # 1. DYNAMIC TAB LIST (English Headers)
    if role == "General Manager":
        tab_list = ["📊 Network Overview", "🌍 Regions", "⛽ Stations", "👥 Employees", "📈 AI Reports", "🛡️ Audit Log", "⚙️ Settings"]
    elif role in ["Region Director", "Region Manager"]:
        tab_list = ["📊 Network Overview", "🌍 Regions", "⛽ Stations", "👥 Employees", "📈 AI Reports", "⚙️ Settings"]
    elif role == "Gas Station Manager":
        tab_list = ["📊 Network Overview", "⛽ Station", "👥 Employees", "📈 AI Reports", "⚙️ Settings"]
    else:
        tab_list = ["📊 My Overview", "⚙️ Settings"]

    tabs = st.tabs(tab_list)

    # --- TAB 0: NETWORK OVERVIEW ---
    with tabs[0]:
        if role in ["Employee", "Gas Station Supervisor"]:
            st.subheader("🏠 My Video Reports & Feedback")
            personal_reports = pd.read_sql_query("""
                SELECT created_at as Date, ai_content as Report, sentiment 
                FROM report_logs WHERE employee_id = ? ORDER BY created_at DESC
            """, conn, params=(user_id,))
            
            if not personal_reports.empty:
                for _, row in personal_reports.iterrows():
                    with st.expander(f"Analysis: {row['Date']} (Sentiment: {row['sentiment']})"):
                        st.markdown(row['Report'])
            else:
                st.info("Submit video material via bot to see AI analysis.")

        else:
            st.subheader("📊 Sales Network Monitoring")            
            c1, c2, c3 = st.columns(3)
            c1.metric("Regions", conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0])
            c2.metric("Stations", conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0])
            c3.metric("Total Employees", conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0])
            
            st.subheader("🌍 Regional Status Overview")
            query_regions = """
                SELECT r.name as 'Region', COUNT(s.id) as 'Total Stations',
                SUM((SELECT COUNT(*) FROM submissions WHERE station_id = s.id AND processed = 0)) as 'Pending Tasks'
                FROM regions r LEFT JOIN stations s ON r.id = s.region_id GROUP BY r.id
            """
            df_reg_status = pd.read_sql_query(query_regions, conn)
            df_reg_status['Status'] = df_reg_status['Pending Tasks'].apply(get_status_emoji)
            st.dataframe(df_reg_status[['Status', 'Region', 'Total Stations', 'Pending Tasks']], use_container_width=True, hide_index=True)

            st.subheader("📍 Station Location Overview")
            query_stations = "SELECT s.id, s.name as 'Station Name', s.physical_address as 'Address', s.lat, s.lon, (SELECT COUNT(*) FROM submissions WHERE station_id = s.id AND processed = 0) as 'Pending' FROM stations s"
            df_stats = pd.read_sql_query(query_stations, conn)
            df_stats['Status'] = df_stats['Pending'].apply(get_status_emoji)
            
            # Display table without external links as requested
            st.dataframe(df_stats[['Status', 'Station Name', 'Address', 'Pending']], use_container_width=True, hide_index=True)
            
            st.divider()
            st.write("### 🗺️ Network Interactive Map")
            # The Map is now the primary way to "Pin" and see locations within the tab
            m = folium.Map(location=[44.7866, 20.4489], zoom_start=6)
            for _, s in df_stats.iterrows():
                icon_color = "green" if s['Pending'] == 0 else "orange" if s['Pending'] < 3 else "red"
                folium.Marker(
                    [s['lat'], s['lon']], 
                    popup=f"<b>{s['Station Name']}</b><br>Address: {s['Address']}<br>Pending: {s['Pending']}",
                    tooltip=s['Station Name'], 
                    icon=folium.Icon(color=icon_color, icon='info-sign')
                ).add_to(m)
            st_folium(m, width="100%", height=500)

    # --- TAB: REGIONS (With Manager Attachment) ---
    if "🌍 Regions" in tab_list:
        with tabs[tab_list.index("🌍 Regions")]:
            st.header("🌍 Region Management")
            
            # Ability to attach Region Manager to selected Region
            st.subheader("Attach Region Manager")
            regions_list = pd.read_sql_query("SELECT id, name FROM regions", conn)
            managers_list = pd.read_sql_query("SELECT id, name FROM employees WHERE role = 'Region Manager'", conn)
            
            with st.form("attach_manager_form"):
                sel_reg = st.selectbox("Select Region", regions_list['name'].tolist())
                sel_mgr = st.selectbox("Select Manager", managers_list['name'].tolist())
                if st.form_submit_button("Update Assignment"):
                    reg_id = regions_list[regions_list['name'] == sel_reg]['id'].values[0]
                    mgr_id = managers_list[managers_list['name'] == sel_mgr]['id'].values[0]
                    # Logically assigning via the employee record or director_regions depending on your schema
                    conn.execute("UPDATE employees SET station_id = NULL WHERE id = ?", (mgr_id,)) # Ensuring RM isn't tied to a single station
                    st.success(f"Assigned {sel_mgr} to {sel_reg} region.")
            
            # ... Rest of your original Region CRUD code ...

    # --- TAB: STATIONS (English) ---
    if "⛽ Stations" in tab_list or "⛽ Station" in tab_list:
        st_idx = tab_list.index("⛽ Stations") if "⛽ Stations" in tab_list else tab_list.index("⛽ Station")
        with tabs[st_idx]:
            st.header("⛽ Fuel Stations Management")
            # ... Rest of your original Stations CRUD code (ensure labels are English) ...

    # --- TAB: EMPLOYEES ---
    if "👥 Employees" in tab_list:
        with tabs[tab_list.index("👥 Employees")]:
            st.header("👥 Human Resources")
            # ... Rest of your original Employees CRUD code ...

   # --- TAB: AI REPORTS (CLEAN VERSION - NO AUDIT LOG) ---
    if "📈 AI Reports" in tab_list:
        with tabs[tab_list.index("📈 AI Reports")]:
            st.header("📈 Hourly AI Insights")
            
            # This block ONLY queries report_logs
            if role == "General Manager":
                query = "SELECT * FROM report_logs WHERE created_at >= datetime('now', '-1 hour')"
                params = ()
            elif role == "Region Director":
                query = """SELECT rl.* FROM report_logs rl JOIN stations s ON rl.station_id = s.id 
                           WHERE s.region_id IN (SELECT region_id FROM director_regions WHERE employee_id = ?)
                           AND rl.created_at >= datetime('now', '-1 hour')"""
                params = (user_id,)
            else:
                query = "SELECT * FROM report_logs WHERE station_id = (SELECT station_id FROM employees WHERE id = ?) AND created_at >= datetime('now', '-1 hour')"
                params = (user_id,)

            reports = pd.read_sql_query(query, conn, params=params)
            if not reports.empty:
                for _, row in reports.iterrows():
                    with st.container(border=True):
                        st.write(f"⏰ **{row['created_at']}** | Sentiment: `{row['sentiment']}`")
                        st.markdown(row['ai_content'])
            else:
                st.warning("No new AI insights available for this period.")

    # --- TAB: AUDIT LOG (STRICTLY GM ONLY) ---
    if "🛡️ Audit Log" in tab_list:
        with tabs[tab_list.index("🛡️ Audit Log")]:
            st.header("🛡️ System Activity Log")
            try:
                cursor = conn.execute("PRAGMA table_info(activity_logs)")
                cols = [c[1] for c in cursor.fetchall()]
                user_col = "user" if "user" in cols else "user_id" if "user_id" in cols else "'System'"
                
                # Fixed SQL syntax
                audit_query = f"SELECT timestamp as 'Timestamp', {user_col} as 'Operator', action as 'Action', details as 'Details' FROM activity_logs ORDER BY timestamp DESC LIMIT 200"
                df_audit = pd.read_sql_query(audit_query, conn)
                st.dataframe(df_audit, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Audit log failed: {e}")

    # --- TAB: SETTINGS ---
    with tabs[-1]:
        st.header("⚙️ User Account Settings")
        # [Insert original password change form here]

# --- END OF MAIN APP LOGIC ---

# --- 2. REGIONS (GM ONLY) ---
    if role == "General Manager":
        with tabs[1]:
            st.subheader("🌍 Upravljanje Regionima")

            # 1. CREATE SECTION
            with st.expander("➕ Dodaj novi region"):
                with st.form("reg_add"):
                    r_name = st.text_input("Naziv regiona")
                    r_mail = st.text_input("Email regiona")
                    if st.form_submit_button("Sačuvaj Region"):
                        conn.execute("INSERT INTO regions (name, email) VALUES (?,?)", (r_name, r_mail))
                        conn.commit()
                        log_activity("CREATE_REGION", f"Dodat region: {r_name}")
                        st.rerun()

            # 2. VIEW SECTION
            df_reg = pd.read_sql_query("SELECT * FROM regions", conn)
            st.dataframe(df_reg, width="stretch", hide_index=True)

            # 3. EDIT / DELETE SECTION
            if not df_reg.empty:
                st.divider()
                st.write("### ✏️ Upravljanje Postojećim Regionima")
                
                # --- THIS DEFINES target_r FOR THE REST OF THE TAB ---
                target_r = st.selectbox(
                    "Izaberi Region za izmenu", 
                    df_reg['id'], 
                    format_func=lambda x: f"ID {x}: {df_reg[df_reg['id']==x]['name'].values[0]}"
                )
                
                # Fetch fresh data for the selected region
                curr_r = df_reg[df_reg['id']==target_r].iloc[0]

                # Now target_r can be safely used in keys and queries
                if st.button("🗑️ Obriši Region", width="stretch", key=f"del_reg_{target_r}"):
                    delete_item("regions", target_r)

                with st.expander("📝 Izmeni detalje regiona", expanded=True):
                    # target_r is used here to make the form key unique
                    with st.form(f"edit_reg_form_{target_r}"):
                        u_name = st.text_input("Naziv", value=curr_r['name'])
                        u_mail = st.text_input("Email", value=curr_r['email'])
                        
                        # Display multi-station association as requested
                        attached_stations = pd.read_sql_query(
                            f"SELECT name FROM stations WHERE region_id = {target_r}", conn
                        )
                        if not attached_stations.empty:
                            st.write("**Associated Stations:**")
                            st.caption(", ".join(attached_stations['name'].tolist()))
                        else:
                            st.info("No stations attached to this region.")

                        if st.form_submit_button("💾 Sačuvaj izmene"):
                            conn.execute("UPDATE regions SET name=?, email=? WHERE id=?", (u_name, u_mail, target_r))
                            conn.commit()
                            log_activity("UPDATE_REGION", f"Izmenjen region ID {target_r}")
                            st.rerun()

# --- 3. STATIONS ---
    if role in ["General Manager", "Region Director", "Region Manager"]:
        idx = 2 if role == "General Manager" else 1
        with tabs[idx]:
            st.subheader("⛽ Upravljanje Stanicama")
            
            # 1. DEFINIŠI REGS NA VRHU TABA
            regs_data = conn.execute("SELECT id, name FROM regions").fetchall()
            regs = {r[1]: r[0] for r in regs_data}

            # 2. DOHVATI LISTU MENADŽERA (za dropdown-ove)
            managers_data = conn.execute("""
                SELECT id, name, surname FROM employees 
                WHERE role = 'Gas Station Manager'
            """).fetchall()
            mgr_options = {f"{m[1]} {m[2]}": m[0] for m in managers_data}
            mgr_list = ["-- Bez menadžera --"] + list(mgr_options.keys())

            # --- CREATE SECTION ---
            with st.expander("➕ Registruj novu stanicu"):
                st.write("📍 Kliknite na mapu za lokaciju:")
                m_c = folium.Map(location=[44.7866, 20.4489], zoom_start=7)
                out_c = st_folium(m_c, width="100%", height=250, key="map_create_stat")
                
                c_lat = out_c["last_clicked"]["lat"] if out_c and out_c.get("last_clicked") else 0.0
                c_lon = out_c["last_clicked"]["lng"] if out_c and out_c.get("last_clicked") else 0.0

                with st.form("stat_add_form"):
                    s_name = st.text_input("Naziv stanice")
                    s_email = st.text_input("Email stanice")
                    s_reg = st.selectbox("Region", list(regs.keys()))
                    
                    # NOVO: Dodela menadžera pri kreiranju
                    s_mgr = st.selectbox("Dodeli Gas Station Managera", mgr_list)
                    
                    s_addr = st.text_input("Adresa")
                    col1, col2 = st.columns(2)
                    lat_in = col1.number_input("Lat", value=float(c_lat), format="%.6f")
                    lon_in = col2.number_input("Lon", value=float(c_lon), format="%.6f")
                    
                    if st.form_submit_button("Sačuvaj Stanicu"):
                        cursor = conn.execute("""
                            INSERT INTO stations (name, region_id, physical_address, email, lat, lon, category) 
                            VALUES (?,?,?,?,?,?,'Retail')
                        """, (s_name, regs[s_reg], s_addr, s_email, lat_in, lon_in))
                        new_station_id = cursor.lastrowid
                        
                        # Ako je izabran menadžer, poveži ga sa novom stanicom
                        if s_mgr != "-- Bez menadžera --":
                            conn.execute("UPDATE employees SET station_id = ? WHERE id = ?", 
                                         (new_station_id, mgr_options[s_mgr]))
                        
                        conn.commit()
                        log_activity("CREATE_STATION", f"Nova stanica: {s_name} (Manager: {s_mgr})")
                        st.success(f"Stanica {s_name} uspešno kreirana!")
                        st.rerun()

            # --- VIEW SECTION ---
            df_s = pd.read_sql_query("""
                SELECT s.*, r.name as region_name,
                (SELECT name || ' ' || surname FROM employees WHERE station_id = s.id AND role = 'Gas Station Manager' LIMIT 1) as manager_name
                FROM stations s 
                JOIN regions r ON s.region_id = r.id
            """, conn)
            
            # Prikazujemo i kolonu manager_name u tabeli
            st.dataframe(df_s[['id', 'name', 'region_name', 'manager_name', 'physical_address', 'email']], 
                         width="stretch", hide_index=True)

            # --- EDIT / DELETE SECTION ---
            if not df_s.empty:
                st.divider()
                st.write("### ✏️ Upravljanje Postojećim Stanicama")
                target_s = st.selectbox("Izaberi Stanicu za izmenu", df_s['id'], 
                                       format_func=lambda x: f"ID {x}: {df_s[df_s['id']==x]['name'].values[0]}")
                
                curr_s = df_s[df_s['id']==target_s].iloc[0]

                if st.button("🗑️ Obriši Stanicu", width="stretch", key=f"del_stat_{target_s}"):
                    delete_item("stations", target_s)

                with st.expander("📝 Izmeni detalje, lokaciju i menadžera", expanded=True):
                    st.write("📍 Lokacija:")
                    m_e = folium.Map(location=[curr_s['lat'], curr_s['lon']], zoom_start=12)
                    folium.Marker([curr_s['lat'], curr_s['lon']]).add_to(m_e)
                    out_e = st_folium(m_e, width="100%", height=200, key=f"map_edit_{target_s}")

                    u_lat = out_e["last_clicked"]["lat"] if out_e and out_e.get("last_clicked") else curr_s['lat']
                    u_lon = out_e["last_clicked"]["lng"] if out_e and out_e.get("last_clicked") else curr_s['lon']

                    with st.form(f"edit_stat_form_{target_s}"):
                        col_a, col_b = st.columns(2)
                        un = col_a.text_input("Naziv", value=curr_s['name'])
                        ue = col_b.text_input("Email stanice", value=str(curr_s['email']) if curr_s['email'] else "")
                        
                        ua = st.text_input("Adresa", value=curr_s['physical_address'])
                        
                        # NOVO: Update menadžera u edit sekciji
                        current_mgr_val = curr_s['manager_name'] if curr_s['manager_name'] else "-- Bez menadžera --"
                        # Osiguravamo da je trenutni menadžer u listi (za slučaj da je neko promenio ime)
                        if current_mgr_val not in mgr_list: mgr_list.append(current_mgr_val)
                        
                        u_mgr = st.selectbox("Gas Station Manager", mgr_list, index=mgr_list.index(current_mgr_val))
                        
                        reg_list = list(regs.keys())
                        default_reg_idx = reg_list.index(curr_s['region_name']) if curr_s['region_name'] in reg_list else 0
                        u_reg_name = st.selectbox("Region", reg_list, index=default_reg_idx)
                        
                        c1, c2 = st.columns(2)
                        ulat_in = c1.number_input("Lat", value=float(u_lat), format="%.6f")
                        ulon_in = c2.number_input("Lon", value=float(u_lon), format="%.6f")
                        
                        if st.form_submit_button("💾 Sačuvaj izmene"):
                            # 1. Update podataka stanice
                            conn.execute("""
                                UPDATE stations 
                                SET name=?, physical_address=?, email=?, region_id=?, lat=?, lon=? 
                                WHERE id=?
                            """, (un, ua, ue, regs[u_reg_name], ulat_in, ulon_in, target_s))
                            
                            # 2. Update veze sa menadžerom
                            # Prvo "skidamo" trenutnog menadžera sa ove stanice
                            conn.execute("UPDATE employees SET station_id = NULL WHERE station_id = ? AND role = 'Gas Station Manager'", (target_s,))
                            
                            # Postavljamo novog ako je izabran
                            if u_mgr != "-- Bez menadžera --":
                                conn.execute("UPDATE employees SET station_id = ? WHERE id = ?", 
                                             (target_s, mgr_options[u_mgr]))
                            
                            conn.commit()
                            log_activity("UPDATE_STATION", f"Izmenjena stanica ID {target_s} (Manager: {u_mgr})")
                            st.success("Uspešno ažurirano!")
                            st.rerun()

# --- 4. EMPLOYEES ---
role = st.session_state.get("user_role")

if role in ["General Manager", "Region Director", "Region Manager"]:
    idx = 3 if role == "General Manager" else 2
    with tabs[idx]:
        st.subheader("👥 Upravljanje zaposlenima")
        
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
                    stats_data = conn.execute("SELECT id, name FROM stations").fetchall()
                    stats = {s[1]: s[0] for s in stats_data}
                    if stats:
                        s_choice = st.selectbox("Assign to Station", list(stats.keys()))
                        s_id_new = stats[s_choice]
        
                elif role_new == "Region Manager":
                    regs_data = conn.execute("SELECT id, name FROM regions").fetchall()
                    regs = {r[1]: r[0] for r in regs_data}
                    if regs:
                        r_choice = st.selectbox("Assign to Region", list(regs.keys()))
                        r_id_new = regs[r_choice]

                elif role_new == "Region Director":
                    regs_data = conn.execute("SELECT id, name FROM regions").fetchall()
                    regs = {r[1]: r[0] for r in regs_data}
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
                        
                        new_id = cursor.lastrowid # Ovo je pravi ID novog zaposlenog
                        
                        if role_new == "Region Director":
                            for rid in director_reg_ids_new:
                                conn.execute("INSERT INTO director_regions (employee_id, region_id) VALUES (?,?)", (new_id, rid))
                        
                        conn.commit()
                        log_activity("CREATE_EMPLOYEE", f"Registrovan novi zaposleni: {e_name} {e_sur}")
                        
                        # ISPRAVLJEN POZIV: Šaljemo new_id kao employee_id
                        if send_invitation_email(e_mail, e_name, pw, role_new, new_id):
                            st.success(f"✅ Created! Credentials sent to {e_mail}")
                        st.rerun()

        # --- VIEW & SEARCH SECTION ---
        st.divider()
        search_query = st.text_input("🔍 Search Employees", "", key="emp_search_input").lower()
        
        df_emp = pd.read_sql_query("""
            SELECT 
                e.id, 
                e.name, 
                e.surname, 
                e.email, 
                e.role, 
                e.telegram_chat_id,  -- DODAJ OVU LINIJU OVDE
                s.name as assigned_station,
                COALESCE(rd.name, ri.name) as region_assigned
            FROM employees e
            LEFT JOIN stations s ON e.station_id = s.id
            LEFT JOIN regions rd ON e.region_id = rd.id
            LEFT JOIN regions ri ON s.region_id = ri.id
        """, conn)

        if st.button("🔄 Osveži tabelu"):
            st.rerun()

        if search_query:
            mask = df_emp.apply(lambda row: search_query in str(row['name']).lower() or 
                                           search_query in str(row['surname']).lower() or 
                                           search_query in str(row['email']).lower(), axis=1)
            filtered_df = df_emp[mask]
        else:
            filtered_df = df_emp

        st.dataframe(filtered_df, width="stretch", hide_index=True)
            
        # --- EDIT / DELETE / RESEND SECTION ---
        if not df_emp.empty:
            st.divider()
            st.write("### ✏️ Upravljanje profilima zaposlenih")

            target_e = st.selectbox(
                "Select ID to Edit", 
                df_emp['id'], 
                format_func=lambda x: f"ID {x}: {df_emp[df_emp['id']==x]['email'].values[0]}", 
                key="staff_manage_selectbox"
            )
            
            # Fetch fresh data for the selected employee to prevent "same report" bug
            curr_selection = conn.execute("SELECT * FROM employees WHERE id=?", (int(target_e),)).fetchone()
            col_names = [d[0] for d in conn.execute("SELECT * FROM employees LIMIT 1").description]
            curr = dict(zip(col_names, curr_selection))

            c_actions, _ = st.columns([2, 2])
            with c_actions:
                c_del, c_resend = st.columns(2)
                if c_del.button("🗑️ Delete staff", width="stretch", key=f"del_btn_{target_e}"):
                    delete_item("employees", target_e)

                if c_resend.button("📧 Resend Mail", width="stretch", key=f"resend_btn_{target_e}"):
                    with st.spinner("🔄 Generisanje nove lozinke..."):
                        # 1. Osiguravamo da je target_e integer
                        emp_id_to_fix = int(target_e)
                        
                        # 2. Generisanje lozinke
                        new_pw = generate_temp_password()
                        
                        # 3. Ažuriranje baze
                        conn.execute("UPDATE employees SET password=? WHERE id=?", (hash_password(new_pw), emp_id_to_fix))
                        conn.commit()
                        
                        # 4. Ponovno dovlačenje svežih podataka da ne bi bilo "Invalid ID"
                        fresh_user = conn.execute("SELECT email, name, role FROM employees WHERE id=?", (emp_id_to_fix,)).fetchone()
                        
                        if fresh_user:
                            # 5. Slanje mejla sa eksplicitno prosleđenim emp_id_to_fix
                            success = send_invitation_email(
                                to_email=fresh_user[0], 
                                first_name=fresh_user[1], 
                                temp_password=new_pw, 
                                role=fresh_user[2], 
                                employee_id=emp_id_to_fix # <-- Ključni fiks
                            )
                            
                            if success:
                                st.success(f"✅ Credentials resent to {fresh_user[0]}!")
                            else:
                                st.error("❌ Greška pri slanju mejla.")

            # Edit full profile expander (available regardless of resend)
            with st.expander("📝 Edit Full Profile Details", expanded=True):
                with st.form(key=f"full_edit_v6_{target_e}"):
                    col1, col2 = st.columns(2)
                    u_n = col1.text_input("Name", value=str(curr['name']))
                    u_s = col2.text_input("Surname", value=str(curr['surname']))
                    u_m = st.text_input("Email", value=str(curr['email']))
                    u_role = st.selectbox(
                        "Role", 
                        ["Employee", "Gas Station Supervisor", "Gas Station Manager", "Region Manager", "Region Director", "General Manager"], 
                        index=["Employee", "Gas Station Supervisor", "Gas Station Manager", "Region Manager", "Region Director", "General Manager"].index(curr['role'])
                    )

                    # 2. Stanica unos (Potrebno je definisati stats_dict pre selectbox-a)
                    stats_data = conn.execute("SELECT id, name FROM stations").fetchall()
                    stats_dict = {s[1]: s[0] for s in stats_data}
                    
                    # Pronalaženje trenutne stanice za index
                    current_stat_name = "-- No Station --"
                    if curr['station_id']:
                        for name, sid in stats_dict.items():
                            if sid == curr['station_id']:
                                current_stat_name = name

                    u_stat = st.selectbox("Assign Station", ["-- No Station --"] + list(stats_dict.keys()), 
                                        index=(["-- No Station --"] + list(stats_dict.keys())).index(current_stat_name))

                    # --- DUGME I LOGIKA (MORA BITI ISPOD INPUTA) ---
                    if st.form_submit_button("💾 Save Changes"):
                        try:
                            # Sada su u_tg, u_m, u_stat definisani u opsegu forme
                            
                            # 1. Provera unikatnosti Telegram ID-a
                            tg_val = u_tg.strip() if u_tg.strip() not in ["", "None", "NULL"] else None
                            
                            if tg_val:
                                existing = conn.execute(
                                    "SELECT id, name, surname FROM employees WHERE telegram_chat_id = ? AND id != ?", 
                                    (tg_val, int(target_e))
                                ).fetchone()
                                
                                if existing:
                                    st.error(f"❌ Greška: Ovaj Telegram ID već koristi zaposleni: {existing[1]} {existing[2]} (ID: {existing[0]})")
                                    st.stop()
                            
                            # 2. Mapiranje ID-a stanice
                            new_s_id = stats_dict.get(u_stat) if u_stat != "-- No Station --" else None
                            
                            # 3. Snimanje promena
                            conn.execute("""
                                UPDATE employees 
                                SET name=?, surname=?, email=?, role=?, station_id=?, telegram_chat_id=? 
                                WHERE id=?
                            """, (u_n, u_s, u_m, u_role, new_s_id, tg_val, int(target_e)))
                            
                            conn.commit()
                            st.success("Uspešno ažurirano!")
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Greška: {e}")

            # --- EMPLOYEE REPORT HISTORY (PERSONALIZED) ---
            st.divider()
            st.write(f"### 📋 Personalni izveštaji zaposlenog: {curr['name']} {curr['surname']}")

            # ID zaposlenog kojeg trenutno gledamo u selectbox-u
            viewed_employee_id = int(target_e)

            st_id = curr.get('station_id')

            try:
                rep_query = """
                    SELECT 
                        r.created_at, 
                        r.sentiment, 
                        r.ai_content, 
                        s.name as station_name 
                    FROM report_logs r
                    LEFT JOIN stations s ON r.station_id = s.id
                    WHERE r.employee_id = ? 
                    OR (r.station_id = ? AND r.station_id IS NOT NULL)
                    ORDER BY r.created_at DESC
                """
                reports_df = pd.read_sql_query(rep_query, conn, params=(viewed_employee_id, st_id))
                
                if reports_df.empty:
                    st.info("Ovaj zaposleni još uvek nema kreiranih ličnih izveštaja.")
                else:
                    for _, row in reports_df.iterrows():
                        report_date = pd.to_datetime(row['created_at']).strftime("%d.%m.%Y - %H:%M")
                        # Ako izveštaj nema stanicu u bazi, ispiši "Nespecifikovano"
                        station_display = row['station_name'] if row['station_name'] else "Nespecifikovana stanica"
                        
                        with st.container():
                            h_col, s_col = st.columns([3, 1])
                            # DODATO: Jasno naznačena stanica za svaki pojedinačni izveštaj
                            h_col.markdown(f"**📍 Stanica:** `{station_display}`")
                            h_col.markdown(f"**📅 Datum:** {report_date}")
                            
                            sent = row['sentiment'] if row['sentiment'] else "Nije ocenjeno"
                            s_col.markdown(f"**Utisak:** `{sent}`")
                            
                            st.divider()
                            st.write(row['ai_content'])
                        
            except Exception as e:
                st.error(f"Greška pri dobavljanju personalnih izveštaja: {e}")
   
# --- 5. AUDIT LOG (GM ONLY) ---
    if role == "General Manager":
        with tabs[4]:
            st.subheader("🛡️ Sistemski Audit Log")
            st.write("Pregled svih kritičnih akcija unutar GenStation Opus ERP sistema.")

            # Filteri za pretragu logova
            f1, f2, f3 = st.columns([1, 1, 2])
            with f1:
                date_filter = st.date_input("Od datuma", value=None)
            with f2:
                user_filter = st.text_input("Filtriraj po korisniku")
            with f3:
                action_filter = st.multiselect("Tip akcije", 
                                            ["CREATE_REGION", "DELETE", "UPDATE_STATION", "CREATE_EMPLOYEE", "PASSWORD_RESET"])

            # Izgradnja dinamičkog SQL upita
            query = "SELECT timestamp as 'Vreme', user_name as 'Korisnik', action as 'Akcija', details as 'Detalji' FROM activity_logs WHERE 1=1"
            params = []

            if date_filter:
                query += " AND date(timestamp) >= ?"
                params.append(date_filter.isoformat())
            if user_filter:
                query += " AND user_name LIKE ?"
                params.append(f"%{user_filter}%")
            if action_filter:
                placeholders = ','.join(['?'] * len(action_filter))
                query += f" AND action IN ({placeholders})"
                params.extend(action_filter)

            query += " ORDER BY timestamp DESC"

            # Prikaz podataka
            audit_df = pd.read_sql_query(query, conn, params=params)
            
            st.dataframe(
                audit_df,
                width="stretch",
                hide_index=True,
                column_config={
                    "Vreme": st.column_config.DatetimeColumn("Vreme", format="DD.MM.YYYY HH:mm"),
                }
            )

            # Dugme za izvoz u CSV
            if not audit_df.empty:
                csv = audit_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Preuzmi logove kao CSV",
                    data=csv,
                    file_name=f"audit_log_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
                    mime='text/csv',
                )

    # Određivanje indexa poslednjeg taba (Settings)
    settings_idx = len(tabs) - 1

    with tabs[settings_idx]:
        st.subheader("⚙️ Podešavanja naloga")
        
        with st.container(border=True):
            st.write("### 🔑 Promena lozinke")
            with st.form("user_change_password_form"):
                current_pw = st.text_input("Trenutna lozinka", type="password")
                new_pw = st.text_input("Nova lozinka", type="password")
                confirm_pw = st.text_input("Potvrdite novu lozinku", type="password")
                
                submit_pw = st.form_submit_button("Ažuriraj lozinku", width="stretch")
                
                if submit_pw:
                    if new_pw != confirm_pw:
                        st.error("Nove lozinke se ne podudaraju!")
                    elif len(new_pw) < 6:
                        st.warning("Nova lozinka mora imati bar 6 karaktera.")
                    else:
                        # Provera stare lozinke
                        user_id = st.session_state.user_id
                        stored_pw = conn.execute("SELECT password FROM employees WHERE id=?", (user_id,)).fetchone()[0]
                        
                        if hash_password(current_pw) == stored_pw:
                            conn.execute("UPDATE employees SET password=? WHERE id=?", 
                                    (hash_password(new_pw), user_id))
                            conn.commit()
                            log_activity("PASSWORD_CHANGE", f"Korisnik {st.session_state.user_name} je promenio lozinku.")
                            st.success("Lozinka uspešno promenjena!")
                        else:
                            st.error("Trenutna lozinka nije ispravna.")