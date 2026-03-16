import streamlit as st
import hashlib
import json
import time
from datetime import datetime
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

    st.divider()
    st.subheader("Appearance")
    
    current_mode = st.session_state.get("dark_mode", False)
    dark_mode = st.toggle("🌙 Enable Dark Mode", value=current_mode)
    if dark_mode != current_mode:
        # Update session state for immediate UI change
        st.session_state["dark_mode"] = dark_mode
        # Persist to database
        try:
            conn.execute("UPDATE users SET dark_mode_enabled = ? WHERE id = ?", (1 if dark_mode else 0, uid))
            conn.commit()
            log_activity(conn, "SETTING_CHANGE", f"User set dark mode to {dark_mode}")
            st.toast("Theme preference saved!")
        except Exception as e:
            st.error(f"Failed to save theme preference: {e}")
            st.session_state["dark_mode"] = current_mode # Revert on failure
        st.rerun()

    st.divider()
    st.subheader("🤖 AI Configuration")

    # --- AI Processing Status ---
    status_placeholder = st.empty()
    
    def display_ai_status():
        status_row = conn.execute("SELECT value FROM system_settings WHERE key='ai_processing_status'").fetchone()
        status_info = {}
        if status_row and status_row[0]:
            try:
                status_info = json.loads(status_row[0])
            except json.JSONDecodeError:
                status_info = {"status": "unknown"}
        
        status = status_info.get("status", "idle")
        
        with status_placeholder.container():
            if status == "processing":
                total = status_info.get("total", 0)
                current = status_info.get("current", 0)
                progress_val = (current / total) if total > 0 else 0
                st.info("AI processing is currently in progress...")
                st.progress(progress_val, text=f"Processing task {current} of {total}")
                st.html("<meta http-equiv='refresh' content='5'>") # Auto-refresh page
            else:
                last_run_ts = status_info.get("last_run_ts")
                if last_run_ts:
                    last_run_str = datetime.fromtimestamp(last_run_ts).strftime('%Y-%m-%d %H:%M:%S')
                    st.success(f"✅ AI Worker is idle. Last batch finished at {last_run_str}.")
                else:
                    st.success("✅ AI Worker is idle.")

    display_ai_status()

    st.caption("AI processing runs automatically every hour. You can force a batch run immediately.")
    
    if st.button("🚀 Force AI Processing Now", type="primary", use_container_width=True):
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('force_ai_processing', '1')")
        conn.commit()
        log_activity(conn, "AI_FORCE_RUN", "User manually triggered AI processing batch")
        st.success("Batch processing signal sent! The AI worker will pick this up within 10 seconds.")
        time.sleep(1) # Give a moment for the user to see the message
        st.rerun()