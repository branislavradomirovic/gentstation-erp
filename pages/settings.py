import streamlit as st
import hashlib
from core.activity_logger import log_activity
from core.auth import verify_password, hash_password
from ui.header import render_page_header

def render(conn):
    render_page_header("⚙ Profile Settings")
    
    uid = st.session_state.get("user_id")
    username = st.session_state.get("username")
    
    st.write(f"Logged in as: **{username}**")
    
    st.divider()
    st.subheader("Change Password")
    
    with st.form("pw_form"):
        current_pw = st.text_input("Current password", type="password")
        new_pw = st.text_input("New password", type="password")
        confirm_pw = st.text_input("Confirm new password", type="password")
        
        if st.form_submit_button("Update Password"):
            if not current_pw or not new_pw:
                st.error("Please fill in all fields.")
            elif new_pw != confirm_pw:
                st.error("New passwords do not match.")
            else:
                # Verify current password from users table
                row = conn.execute("SELECT password_hash, email FROM users WHERE id = ?", (uid,)).fetchone()
                if row:
                    stored_hash, email = row
                    if verify_password(current_pw, stored_hash):
                        # 1. Update users table (Bcrypt)
                        new_bcrypt = hash_password(new_pw)
                        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_bcrypt, uid))
                        
                        # 2. Update employees table (SHA256 - Legacy Sync) if email link exists
                        if email:
                            new_sha = hashlib.sha256(new_pw.encode()).hexdigest()
                            conn.execute("UPDATE employees SET password = ? WHERE email = ?", (new_sha, email))
                        
                        conn.commit()
                        log_activity(conn, "PASSWORD_CHANGE", f"User {username} changed password")
                        st.success("Password updated successfully!")
                    else:
                        st.error("Incorrect current password.")
                else:
                    st.error("User record not found.")