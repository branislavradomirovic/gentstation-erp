# gentstation_opus/core/activity_logger.py
import streamlit as st

def log_activity(conn, action, details):
    user = st.session_state.get("user_name", "System")
    try:
        conn.execute(
            "INSERT INTO activity_logs (user_name, action, details) VALUES (?, ?, ?)",
            (user, action, details)
        )
        conn.commit()
    except Exception as e:
        # log locally if DB fails
        print("log_activity error:", e)