# pages/admin_users.py
import streamlit as st
import pandas as pd
from core.database import get_connection
from core.activity_logger import log_activity
from core.auth import create_user, hash_password, verify_password

def render(conn):
    st.title("🔧 User Management (Admin)")

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
    df = pd.read_sql_query("SELECT id, username, email, role, is_active, created_at FROM users ORDER BY id DESC", conn)
    if df.empty:
        st.info("No users yet.")
        return

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### Edit / Deactivate user")
    uid = st.selectbox("Select user id", df['id'].tolist())
    if uid:
        row = df[df['id'] == uid].iloc[0]
        st.write(f"Username: **{row['username']}**  Role: **{row['role']}** Active: **{row['is_active']}**")
        if st.button("Deactivate user"):
            conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (uid,))
            conn.commit()
            log_activity(conn, "DEACTIVATE_USER", f"User ID {uid}")
            st.success("User deactivated.")
        if st.button("Activate user"):
            conn.execute("UPDATE users SET is_active = 1 WHERE id = ?", (uid,))
            conn.commit()
            log_activity(conn, "ACTIVATE_USER", f"User ID {uid}")
            st.success("User activated.")
        if st.button("Delete user"):
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