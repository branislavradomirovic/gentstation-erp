# gentstation_opus/pages/employees.py
import streamlit as st
import pandas as pd
import hashlib
import secrets
from core.activity_logger import log_activity

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_temp_password(n: int = 10) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(secrets.choice(alphabet) for _ in range(n))

def render(conn):
    st.title("👥 Employees")

    # Top: create new employee
    with st.expander("➕ Register New Employee"):
        with st.form("add_emp"):
            first = st.text_input("First name")
            last = st.text_input("Surname")
            email = st.text_input("Email")
            role = st.selectbox("Role", ["Employee", "Gas Station Supervisor", "Gas Station Manager", "Region Manager", "Region Director", "General Manager"])
            assign_station = st.text_input("Assign station id (optional)")
            assign_region = st.text_input("Assign region id (optional)")
            if st.form_submit_button("Create Employee"):
                if not first.strip() or not email.strip():
                    st.error("Name and email are required.")
                else:
                    pw = generate_temp_password()
                    hashed = hash_password(pw)
                    conn.execute("INSERT INTO employees (name, surname, email, password, role, station_id, region_id) VALUES (?,?,?,?,?,?,?)",
                                 (first.strip(), last.strip(), email.strip(), hashed, role, int(assign_station) if assign_station else None, int(assign_region) if assign_region else None))
                    conn.commit()
                    log_activity(conn, "CREATE_EMPLOYEE", f"Created employee {first} {last} ({email}) role {role}")
                    st.success(f"Employee {first} {last} created. Temporary password: {pw}")
                    st.rerun()

    # List employees
    df = pd.read_sql_query("""
        SELECT e.id, e.name || ' ' || e.surname as fullname, e.email, e.role, s.name as station_name, r.name as region_name
        FROM employees e
        LEFT JOIN stations s ON e.station_id = s.id
        LEFT JOIN regions r ON e.region_id = r.id
        ORDER BY e.id
    """, conn)

    st.subheader("Employee Directory")
    if df.empty:
        st.info("No employees found.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("✏️ Edit / Delete Employee")
    emp_ids = df['id'].tolist() if not df.empty else []
    if emp_ids:
        sel = st.selectbox("Select employee", emp_ids, format_func=lambda x: f"ID {x}: {df[df['id']==x]['fullname'].values[0]}")
        rec = pd.read_sql_query("SELECT * FROM employees WHERE id = ?", conn, params=(sel,)).iloc[0]
        with st.form(f"edit_emp_{sel}"):
            name = st.text_input("First name", value=rec['name'])
            surname = st.text_input("Surname", value=rec['surname'])
            email = st.text_input("Email", value=rec['email'])
            role = st.selectbox("Role", ["Employee", "Gas Station Supervisor", "Gas Station Manager", "Region Manager", "Region Director", "General Manager"], index=["Employee", "Gas Station Supervisor", "Gas Station Manager", "Region Manager", "Region Director", "General Manager"].index(rec['role']) if rec['role'] in ["Employee","Gas Station Supervisor","Gas Station Manager","Region Manager","Region Director","General Manager"] else 0)
            station_id = st.text_input("Station ID", value=str(rec['station_id']) if rec['station_id'] else "")
            region_id = st.text_input("Region ID", value=str(rec['region_id']) if rec['region_id'] else "")
            tg = st.text_input("Telegram Chat ID", value=rec['telegram_chat_id'] if rec['telegram_chat_id'] else "")
            if st.form_submit_button("Save changes"):
                try:
                    conn.execute("UPDATE employees SET name=?, surname=?, email=?, role=?, station_id=?, region_id=?, telegram_chat_id=? WHERE id=?",
                                 (name.strip(), surname.strip(), email.strip(), role, int(station_id) if station_id else None, int(region_id) if region_id else None, tg.strip() if tg.strip() else None, sel))
                    conn.commit()
                    log_activity(conn, "UPDATE_EMPLOYEE", f"Updated employee ID {sel}")
                    st.success("Employee updated.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error updating employee: {e}")
            if st.button("🗑️ Delete employee"):
                try:
                    conn.execute("DELETE FROM employees WHERE id = ?", (sel,))
                    conn.commit()
                    log_activity(conn, "DELETE_EMPLOYEE", f"Deleted employee ID {sel}")
                    st.success("Employee deleted.")
                    st.rerun()
                except Exception as e:
                    st.error("Unable to delete employee - may be referenced by other records.")
        st.divider()
        # Resend credentials (simple)
        if st.button("📧 Resend credentials (generate new temp password)"):
            new_pw = generate_temp_password()
            conn.execute("UPDATE employees SET password = ? WHERE id = ?", (hash_password(new_pw), sel))
            conn.commit()
            log_activity(conn, "PASSWORD_RESET", f"Reset password for employee {sel}")
            st.success(f"New temporary password: {new_pw} (send via email/telegram in production)")