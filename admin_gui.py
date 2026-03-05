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

# --- UI HELPERS ---

def get_status_emoji(unprocessed_count):
    """Određuje vizuelni status stanice na osnovu broja neobrađenih snimaka."""
    if unprocessed_count == 0:
        return "🟢 😊" # Sve pod kontrolom
    elif unprocessed_count < 3:
        return "🟡 😐" # Potrebna pažnja
    else:
        return "🔴 ⚠️" # Kritično - zastoj u obradi

def display_sidebar_header():
    """Prikazuje logo i informacije o korisniku u sidebaru (vidljivo na svim tabovima)."""
    with st.sidebar:
        logo_path = "assets/Opus Logo .png"
        if os.path.exists(logo_path):
            st.image(logo_path, use_container_width=True)
        else:
            st.title("🛡️ GentStation App")
        
        st.divider()
        st.write(f"Korisnik: **{st.session_state.user_name}**")
        st.caption(f"Uloga: {st.session_state.user_role}")
        
        if st.button("🚪 Odjavi se", use_container_width=True):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()
        st.divider()
    # --- POMOĆNA FUNKCIJA ZA BRISANJE ---
    def delete_item(table, item_id):
        try:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
            conn.commit()
            st.success("Uspešno obrisano!")
            st.rerun()
        except Exception as e:
            st.error("Greška: Stavka je verovatno povezana sa drugim podacima.")

# --- AUTHENTICATION & SECURITY ---

if 'auth_status' not in st.session_state:
    st.session_state.auth_status = False
    st.session_state.user_email = None
    st.session_state.user_role = None
    st.session_state.user_id = None
    st.session_state.user_name = None

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def login_screen():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("⛽ GentStation Portal")
        with st.container(border=True):
            email = st.text_input("Email / Username")
            pw = st.text_input("Lozinka", type="password")
            if st.button("Prijavi se", use_container_width=True):
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
    # Pozivamo sidebar header koji sadrži logo i user info
    display_sidebar_header()

    role = st.session_state.user_role
    
    # Definisanje tabova na osnovu uloge
    if role == "General Manager":
        tab_list = ["📊 Network Oversight", "🌍 Regions", "⛽ Stations", "👥 Employees"]
    elif role in ["Region Director", "Region Manager"]:
        tab_list = ["📊 Network Oversight", "⛽ Stations", "👥 Employees"]
    else:
        tab_list = ["📊 My Dashboard"]
    
    tabs = st.tabs(tab_list)

    # --- 1. NETWORK OVERSIGHT ---
    with tabs[0]:
        if role == "Gas Station Manager":
            # Specijalni prikaz za menadžere stanica - Arhiva izveštaja
            st.subheader("📋 Arhiva AI Revizija (Srpski)")
            reports_df = pd.read_sql_query(f"""
                SELECT created_at as Datum, ai_content as Izveštaj 
                FROM report_logs 
                WHERE station_id = (SELECT station_id FROM employees WHERE id = {st.session_state.user_id}) 
                ORDER BY created_at DESC LIMIT 10
            """, conn)
            
            if not reports_df.empty:
                for _, row in reports_df.iterrows():
                    with st.expander(f"Izveštaj - {row['Datum']}"):
                        st.markdown(row['Izveštaj'])
            else:
                st.info("Još uvek nema generisanih izveštaja za vašu stanicu.")
        else:
            # Pregled za GM i Regionalne menadžere
            st.subheader("📊 Monitoring Prodajne Mreže")
            
            # KPI Kartice
            c1, c2, c3 = st.columns(3)
            c1.metric("Regioni", conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0])
            c2.metric("Stanice", conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0])
            c3.metric("Ukupno Zaposlenih", conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0])
            
            # SQL upit za listu stanica sa stanjem izveštaja
            query = """
                SELECT 
                    s.id, 
                    s.name as 'Naziv Stanice', 
                    s.physical_address as 'Adresa',
                    s.lat, s.lon,
                    (SELECT COUNT(*) FROM submissions WHERE station_id = s.id AND processed = 0) as 'Neobrađeno'
                FROM stations s
            """
            df_stats = pd.read_sql_query(query, conn)
            df_stats['Status'] = df_stats['Neobrađeno'].apply(get_status_emoji)
            
            # Generisanje linka za Google Maps
            df_stats['Mapa'] = df_stats.apply(lambda x: f"https://www.google.com/maps/search/?api=1&query={x['lat']},{x['lon']}", axis=1)

            # Glavna tabela sa statusima
            st.dataframe(
                df_stats[['Status', 'Naziv Stanice', 'Adresa', 'Neobrađeno', 'Mapa']],
                column_config={
                    "Mapa": st.column_config.LinkColumn("📍 Lokacija", display_text="Pogledaj Pin"),
                    "Neobrađeno": st.column_config.NumberColumn("Čeka na AI", format="%d 📹"),
                },
                use_container_width=True,
                hide_index=True
            )

            st.divider()
            
            # Vizuelni prikaz na mapi
            st.write("### 🌍 Geografski prikaz")
            m = folium.Map(location=[44.7866, 20.4489], zoom_start=6)
            for _, s in df_stats.iterrows():
                # Boja markera može da prati status
                icon_color = "green" if s['Neobrađeno'] == 0 else "orange" if s['Neobrađeno'] < 3 else "red"
                folium.Marker(
                    [s['lat'], s['lon']], 
                    tooltip=s['Naziv Stanice'],
                    icon=folium.Icon(color=icon_color, icon='info-sign')
                ).add_to(m)
            st_folium(m, width="100%", height=400)

    # --- 2. REGIONS (GM ONLY) ---
    if role == "General Manager":
        with tabs[1]:
            st.subheader("🌍 Upravljanje Regionima")
            
            # CREATE
            with st.expander("➕ Dodaj novi region"):
                with st.form("reg_add"):
                    r_name = st.text_input("Naziv regiona")
                    r_mail = st.text_input("Email regiona")
                    if st.form_submit_button("Sačuvaj Region"):
                        conn.execute("INSERT INTO regions (name, email) VALUES (?,?)", (r_name, r_mail))
                        conn.commit()
                        st.rerun()

            # READ
            df_reg = pd.read_sql_query("SELECT * FROM regions", conn)
            st.dataframe(df_reg, use_container_width=True, hide_index=True)

            # UPDATE & DELETE
            if not df_reg.empty:
                st.divider()
                target_r = st.selectbox("Izaberi region za izmenu/brisanje", df_reg['id'], 
                                    format_func=lambda x: df_reg[df_reg['id']==x]['name'].values[0])
                curr_r = df_reg[df_reg['id']==target_r].iloc[0]
                
                with st.form(f"edit_reg_{target_r}"):
                    u_name = st.text_input("Novi naziv", value=curr_r['name'])
                    u_mail = st.text_input("Novi email", value=curr_r['email'])
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("💾 Sačuvaj izmene"):
                        conn.execute("UPDATE regions SET name=?, email=? WHERE id=?", (u_name, u_mail, target_r))
                        conn.commit()
                        st.rerun()
                    if c2.form_submit_button("🗑️ Obriši region"):
                        delete_item("regions", target_r)

    # --- 3. STATIONS ---
    if role in ["General Manager", "Region Director", "Region Manager"]:
        idx = 2 if role == "General Manager" else 1
    with tabs[idx]:
        st.subheader("⛽ Upravljanje Stanicama")
        
        # CREATE
        with st.expander("➕ Registruj novu stanicu"):
            regs = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM regions").fetchall()}
            with st.form("stat_add"):
                s_name = st.text_input("Naziv stanice")
                s_reg = st.selectbox("Region", list(regs.keys()))
                s_addr = st.text_input("Fizička adresa")
                col1, col2 = st.columns(2)
                s_lat = col1.number_input("Latituda", format="%.6f")
                s_lon = col2.number_input("Longituda", format="%.6f")
                if st.form_submit_button("Sačuvaj Stanicu"):
                    conn.execute("""INSERT INTO stations (name, region_id, physical_address, lat, lon, category) 
                                    VALUES (?,?,?,?,?,'Retail')""", (s_name, regs[s_reg], s_addr, s_lat, s_lon))
                    conn.commit()
                    st.rerun()

        # READ
        df_stat = pd.read_sql_query("""
            SELECT s.id, s.name, r.name as region, s.physical_address, s.lat, s.lon 
            FROM stations s JOIN regions r ON s.region_id = r.id
        """, conn)
        st.dataframe(df_stat, use_container_width=True, hide_index=True)

        # UPDATE & DELETE
        if not df_stat.empty:
            st.divider()
            target_s = st.selectbox("Izaberi stanicu za izmenu/brisanje", df_stat['id'], 
                                   format_func=lambda x: df_stat[df_stat['id']==x]['name'].values[0])
            curr_s = pd.read_sql_query(f"SELECT * FROM stations WHERE id={target_s}", conn).iloc[0]
            
            with st.form(f"edit_stat_{target_s}"):
                u_name = st.text_input("Naziv", value=curr_s['name'])
                u_addr = st.text_input("Adresa", value=curr_s['physical_address'])
                c1, c2 = st.columns(2)
                u_lat = c1.number_input("Lat", value=curr_s['lat'], format="%.6f")
                u_lon = c2.number_input("Lon", value=curr_s['lon'], format="%.6f")
                
                btn1, btn2 = st.columns(2)
                if btn1.form_submit_button("💾 Sačuvaj izmene"):
                    conn.execute("UPDATE stations SET name=?, physical_address=?, lat=?, lon=? WHERE id=?", 
                                 (u_name, u_addr, u_lat, u_lon, target_s))
                    conn.commit()
                    st.rerun()
                if btn2.form_submit_button("🗑️ Obriši stanicu"):
                    delete_item("stations", target_s)

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