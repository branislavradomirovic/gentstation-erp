# pages/admin_users.py
import streamlit as st
import pandas as pd
from core.database import get_connection
from core.activity_logger import log_activity
from core.auth import create_user, hash_password, verify_password
from ui.header import render_page_header

def render(conn):
    render_page_header("🔧 User Management (Admin)")

    # --- SYSTEM MAINTENANCE CONTROL ---
    with st.expander("⚙️ System Maintenance", expanded=False):
        st.write("When enabled, only **General Manager** users can log in.")
        cur = conn.cursor()
        row_maint = cur.execute("SELECT value FROM system_settings WHERE key='maintenance_mode'").fetchone()
        is_maint_on = (row_maint and row_maint[0] == '1')

        new_maint = st.toggle("🚨 Enable Maintenance Mode", value=is_maint_on)
        if new_maint != is_maint_on:
            val = '1' if new_maint else '0'
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('maintenance_mode', ?)", (val,))
            conn.commit()
            log_activity(conn, "MAINTENANCE_MODE", f"Set to {new_maint}")
            st.rerun()

    # Only accessible to admins via app.py permissions check (app should only call render for admins)
    st.markdown("### Create new system user")
    with st.form("create_user_form"):
        username = st.text_input("Username")
        email = st.text_input("Email")
        role = st.selectbox("Role", ["General Manager", "Region Director", "Region Manager", "Gas Station Manager", "Employee"])
        pwd = st.text_input("Temporary password", value="", type="password")
        if st.form_submit_button("Create user"):
            if not username or not pwd:
                st.error("Username and password required")
            else:
                try:
                    u = create_user(username=username, password=pwd, email=email or None, role=role)
                    log_activity(conn, "CREATE_USER", f"Created user {username} role {role}")
                    st.success(f"User {username} created.")
                except Exception as e:
                    st.error(f"Failed to create user: {e}")

    st.divider()
    st.markdown("### Existing users")
    df = pd.read_sql_query("SELECT id, username, email, role, is_active, created_at, failed_attempts, locked_until FROM users ORDER BY id DESC", conn)
    if df.empty:
        st.info("No users yet.")
        return

    st.dataframe(df[['id', 'username', 'email', 'role', 'is_active', 'failed_attempts', 'locked_until']], use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### Edit / Deactivate user")
    uid = st.selectbox("Select user id", df['id'].tolist())
    if uid:
        row = df[df['id'] == uid].iloc[0]
        st.write(f"Username: **{row['username']}** | Role: **{row['role']}** | Active: **{row['is_active']}**")
        st.write(f"Failed Attempts: **{row['failed_attempts']}** | Locked Until: **{row['locked_until'] or 'Not Locked'}**")

        # Action buttons in columns for better layout
        cols = st.columns(4)
        
        # Unlock button - only shows if user is locked
        if row['locked_until']:
            if cols[0].button("🔓 Unlock User", use_container_width=True, type="primary"):
                conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (uid,))
                conn.commit()
                log_activity(conn, "UNLOCK_USER", f"Manually unlocked user ID {uid}")
                st.success(f"User {row['username']} has been unlocked.")
                st.rerun()

        if cols[1].button("Deactivate user", use_container_width=True):
            conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
            conn.commit()
            log_activity(conn, "DEACTIVATE_USER", f"User ID {uid}")
            st.success("User deactivated.")
        if cols[2].button("Activate user", use_container_width=True):
            conn.execute("UPDATE users SET is_active = 1 WHERE id = ?", (uid,))
            conn.commit()
            log_activity(conn, "ACTIVATE_USER", f"User ID {uid}")
            st.success("User activated.")
        if cols[3].button("🗑️ Delete user", type="secondary", use_container_width=True):
            try:
                conn.execute("DELETE FROM users WHERE id = ?", (uid,))
                conn.commit()
                log_activity(conn, "DELETE_USER", f"User ID {uid}")
                st.success("User deleted.")
            except Exception as e:
                st.error("Could not delete user: " + str(e))

    st.divider()
    st.markdown("### Reset password")
    uid_reset = st.selectbox("Select user to reset password", df['id'].tolist(), key="reset_uid")
    new_pw = st.text_input("New temporary password", type="password", key="reset_pw")
    if st.button("Reset password button"):
        if not new_pw:
            st.error("Provide new password.")
        else:
            conn.execute("UPDATE users SET password_hash = ? , updated_at = ? WHERE id = ?", (hash_password(new_pw), pd.Timestamp.now().isoformat(), uid_reset))
            conn.commit()
            log_activity(conn, "RESET_PASSWORD", f"Reset password for user {uid_reset}")
            st.success("Password reset. Share temporary password securely with the user.")