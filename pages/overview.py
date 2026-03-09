# gentstation_opus/pages/overview.py
import streamlit as st
import pandas as pd

def render(conn):
    st.title("📊 Network Overview")
    c1, c2, c3 = st.columns(3)
    c1.metric("Regions", conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0])
    c2.metric("Stations", conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0])
    c3.metric("Employees", conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0])
    st.subheader("Recent AI Reports")
    df = pd.read_sql_query("SELECT created_at, report_role, station_id, sentiment FROM ai_reports ORDER BY created_at DESC LIMIT 20", conn)
    st.dataframe(df, use_container_width=True)