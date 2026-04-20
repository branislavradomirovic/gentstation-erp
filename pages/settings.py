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
                row = conn.execute("SELECT password_hash, email FROM users WHERE id = %s", (uid,)).fetchone()
                if row:
                    stored_hash, email = row
                    if verify_password(current_pw, stored_hash):
                        # 1. Update users table (Bcrypt)
                        new_bcrypt = hash_password(new_pw)
                        conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_bcrypt, uid))
                        
                        # 2. Update employees table (SHA256 - Legacy Sync) if email link exists
                        if email:
                            new_sha = hashlib.sha256(new_pw.encode()).hexdigest()
                            conn.execute("UPDATE employees SET password = %s WHERE email = %s", (new_sha, email))
                        
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
            conn.execute("UPDATE users SET dark_mode_enabled = %s WHERE id = %s", (1 if dark_mode else 0, uid))
            conn.commit()
            log_activity(conn, "SETTING_CHANGE", f"User set dark mode to {dark_mode}")
            st.toast("Theme preference saved!")
        except Exception as e:
            st.error(f"Failed to save theme preference: {e}")
            st.session_state["dark_mode"] = current_mode # Revert on failure
        st.rerun()

    st.divider()
    st.subheader("🤖 AI Configuration")

    def render_worker_status(title, status_row, stale_after_seconds=120):
        status_info = {}
        if status_row and status_row[0]:
            try:
                status_info = json.loads(status_row[0])
            except json.JSONDecodeError:
                status_info = {"status": "unknown"}

        status = status_info.get("status", "offline")
        ts = status_info.get("last_update_ts")
        details = status_info.get("details")
        stale = False
        if ts:
            stale = (time.time() - float(ts)) > stale_after_seconds

        if status == "online" and not stale:
            st.success(f"✅ {title}: Online")
        elif status == "starting":
            st.info(f"🟡 {title}: Starting")
        elif status == "error":
            msg = details or "Unknown error"
            st.error(f"🔴 {title}: Error - {msg}")
        elif stale:
            st.warning(f"⚠️ {title}: Stale heartbeat")
        else:
            st.warning(f"⚪ {title}: Offline")

        if ts:
            updated_str = datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d %H:%M:%S')
            st.caption(f"Last update: {updated_str}")

    # --- Bot Status ---
    bot_row = conn.execute("SELECT value FROM system_settings WHERE key='telegram_bot_status'").fetchone()
    render_worker_status("Telegram Bot", bot_row, stale_after_seconds=90)

    st.divider()
    st.subheader("🤖 AI Worker Status")
    ai_status_row = conn.execute("SELECT value FROM system_settings WHERE key='ai_processing_status'").fetchone()
    ai_status_info = {}
    if ai_status_row and ai_status_row[0]:
        try:
            ai_status_info = json.loads(ai_status_row[0])
        except json.JSONDecodeError:
            ai_status_info = {"status": "unknown"}

    ai_status = ai_status_info.get("status", "idle")
    if ai_status == "processing":
        total = ai_status_info.get("total", 0)
        current = ai_status_info.get("current", 0)
        progress_val = (current / total) if total > 0 else 0
        st.info("AI processing is currently in progress...")
        st.progress(progress_val, text=f"Processing task {current} of {total}")
        st.html("<meta http-equiv='refresh' content='5'>")
    else:
        last_run_ts = ai_status_info.get("last_run_ts")
        if last_run_ts:
            last_run_str = datetime.fromtimestamp(last_run_ts).strftime('%Y-%m-%d %H:%M:%S')
            st.success(f"✅ AI Worker is idle. Last batch finished at {last_run_str}.")
        else:
            st.success("✅ AI Worker is idle.")

    st.caption("AI processing runs automatically every hour. You can force a batch run immediately.")
    
    if st.button("🚀 Force AI Processing Now", type="primary", width="stretch"):
        conn.execute(
            """
            INSERT INTO system_settings (key, value)
            VALUES (%s, '1')
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            ("force_ai_processing",)
        )
        conn.commit()
        log_activity(conn, "AI_FORCE_RUN", "User manually triggered AI processing batch")
        st.success("Batch processing signal sent! The AI worker will pick this up within 10 seconds.")
        time.sleep(1) # Give a moment for the user to see the message
        st.rerun()

    # --- Admin: Default Break Duration (General Manager only) ---
    user_role = st.session_state.get("user_role", "Employee")
    if user_role == "General Manager":
        st.divider()
        st.subheader("Admin: Break Settings")
        # read current value from system_settings
        try:
            row = conn.execute("SELECT value FROM system_settings WHERE key=%s", ("default_break_minutes",)).fetchone()
            current_default = int(row[0]) if row and row[0] else 15
        except Exception:
            current_default = 15

        new_val = st.number_input("Default break duration (minutes)", min_value=1, max_value=240, value=current_default)
        if st.button("Save Break Duration", type="primary"):
            try:
                conn.execute(
                    "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    ("default_break_minutes", str(int(new_val))),
                )
                conn.commit()
                log_activity(conn, "SETTING_CHANGE", f"Admin set default_break_minutes to {int(new_val)}")
                st.success("Default break duration updated.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save: {e}")
