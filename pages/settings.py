# gentstation_opus/pages/settings.py
import streamlit as st
from core.activity_logger import log_activity

def render(conn):
    st.title("⚙ Settings")
    st.write("Change your password")
    with st.form("pw_form"):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm", type="password")
        if st.form_submit_button("Change"):
            if new != confirm:
                st.error("Passwords must match")
            else:
                # naive password update (add hashing in your prod)
                uid = st.session_state.user_id
                conn.execute("UPDATE employees SET password = ? WHERE id = ?", (new, uid))
                conn.commit()
                log_activity(conn, "PASSWORD_CHANGE", f"user {st.session_state.get('user_name')} changed password")
                st.success("Password updated")