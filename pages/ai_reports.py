# gentstation_opus/pages/ai_reports.py
import streamlit as st
import pandas as pd

def render(conn):
    st.title("📈 AI Reports")
    role = st.session_state.user_role
    uid = st.session_state.user_id
    if role == "General Manager":
        df = pd.read_sql_query("SELECT * FROM ai_reports ORDER BY created_at DESC LIMIT 200", conn)
    elif role == "Region Director":
        # fetch director's regions
        regs = conn.execute("SELECT region_id FROM director_regions WHERE employee_id = ?", (uid,)).fetchall()
        region_ids = [r[0] for r in regs]
        if region_ids:
            placeholder = ",".join("?"*len(region_ids))
            df = pd.read_sql_query(f"SELECT * FROM ai_reports WHERE region_id IN ({placeholder}) ORDER BY created_at DESC", conn, params=region_ids)
        else:
            df = pd.DataFrame()
    elif role == "Region Manager":
        # show reports for manager's region_id
        region_id = conn.execute("SELECT region_id FROM employees WHERE id = ?", (uid,)).fetchone()[0]
        df = pd.read_sql_query("SELECT * FROM ai_reports WHERE region_id = ? ORDER BY created_at DESC", conn, params=(region_id,))
    elif role == "Gas Station Manager":
        station_id = conn.execute("SELECT station_id FROM employees WHERE id = ?", (uid,)).fetchone()[0]
        df = pd.read_sql_query("SELECT * FROM ai_reports WHERE station_id = ? ORDER BY created_at DESC", conn, params=(station_id,))
    else:
        df = pd.DataFrame()
    if df.empty:
        st.info("No AI reports available.")
        return
    st.dataframe(df[['created_at','report_role','station_id','sentiment','safety_score','kpi_json']], use_container_width=True)
    # preview detail
    idx = st.selectbox("Select report ID to preview", df['id'].tolist())
    if idx:
        row = df[df['id']==idx].iloc[0]
        st.subheader(f"Report {idx} - {row['report_role']}")
        st.write(row['report_text'] or "")
        st.json(json.loads(row['kpi_json']) if row['kpi_json'] else {})