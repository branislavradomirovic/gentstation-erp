# gentstation_opus/pages/audit_log.py
import streamlit as st
import pandas as pd
from ui.header import render_page_header

def render(conn):
    render_page_header("🛡 System Audit Log")
    col1, col2, col3 = st.columns(3)
    user_filter = col1.text_input("User name")
    action_filter = col2.text_input("Action")
    date_filter = col3.date_input("From date", value=None)
    query = "SELECT timestamp AS Timestamp, user_name AS Operator, action AS Action, details AS Details FROM activity_logs WHERE 1=1"
    params = []
    if user_filter:
        query += " AND user_name LIKE ?"
        params.append(f"%{user_filter}%")
    if action_filter:
        query += " AND action LIKE ?"
        params.append(f"%{action_filter}%")
    if date_filter:
        query += " AND date(timestamp) >= ?"
        params.append(date_filter.isoformat())
    query += " ORDER BY timestamp DESC LIMIT 1000"
    df = pd.read_sql_query(query, conn, params=params)
    st.dataframe(df, use_container_width=True)