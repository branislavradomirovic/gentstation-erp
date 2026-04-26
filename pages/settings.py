import os
import streamlit as st
import hashlib
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from core.activity_logger import log_activity
from core.database import get_pool_stats, test_redis_connection, DB_HOST
from core.video_processor import test_ollama_connection, OLLAMA_BASE_URL
from core.comm_service import test_smtp_connection
from core.auth import verify_password, hash_password
from ui.header import render_page_header

def render(conn):
    # --- 0. PULSE CSS ---
    st.markdown("""
        <style>
            @keyframes status-pulse {
                0% { box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.7); }
                70% { box-shadow: 0 0 0 10px rgba(220, 53, 69, 0); }
                100% { box-shadow: 0 0 0 0 rgba(220, 53, 69, 0); }
            }
            .pulse-badge {
                animation: status-pulse 2s infinite;
                display: inline-block;
            }
        </style>
    """, unsafe_allow_html=True)

    render_page_header("⚙ Profile Settings")

    # --- 1. SYSTEM HEALTH WIDGET (MOVED FROM DASHBOARD) ---
    total_open_alerts = 0
    try:
        total_open_alerts = conn.execute("SELECT COUNT(*) FROM ai_alerts WHERE status IN ('new', 'acknowledged')").fetchone()[0]
    except Exception:
        conn.rollback()

    uptime_pct = 100.0
    try:
        uptime_row = conn.execute("""
            SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE is_online) / COUNT(*), 1)
            FROM redis_health_logs
            WHERE timestamp >= NOW() - INTERVAL '24 HOURS'
        """).fetchone()
        if uptime_row and uptime_row[0] is not None:
            uptime_pct = float(uptime_row[0])
    except Exception:
        conn.rollback()

    sh_title_col, sh_btn_col1, sh_btn_col2, sh_btn_col3 = st.columns([2, 1, 1, 1], vertical_alignment="bottom")
    with sh_title_col:
        st.markdown(
            f"#### 🏥 System Health <span style='font-size: 0.8rem; color: #666; vertical-align: middle; margin-left: 8px;'>(Uptime: {uptime_pct}%)</span>",
            unsafe_allow_html=True
        )
        st.markdown(f"<span style='font-size: 0.9rem; color: #dc3545;'>🚨 {total_open_alerts} Active Alerts</span>", unsafe_allow_html=True)

    with sh_btn_col1:
        if st.button("🔄 Re-check", key="recheck_services_btn", width="stretch"):
            st.rerun()
    with sh_btn_col2:
        if st.button("📈 Monitoring", key="nav_ai_monitoring", width="stretch"):
            st.session_state.active_page = "AI Monitoring"
            st.rerun()
    with sh_btn_col3:
        if st.button("🛡️ Audit Log", key="nav_audit_log", width="stretch"):
            st.session_state.active_page = "Audit Log"
            st.rerun()

    h_col1, h_col2, h_col3, h_col4 = st.columns(4)

    def status_badge(label, color, animate=False):
        cls = "pulse-badge" if animate else ""
        return f'<span class="{cls}" style="background-color:{color}; color:white; padding:2px 12px; border-radius:15px; font-size:0.85rem; font-weight:bold;">{label}</span>'

    with h_col1:
        st.markdown(f"**Database**\n\n`{DB_HOST}`")
        if conn:
            st.markdown(status_badge("ONLINE", "#28a745"), unsafe_allow_html=True)
        else:
            st.markdown(status_badge("OFFLINE", "#dc3545", animate=True), unsafe_allow_html=True)

    with h_col2:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_host = redis_url.split("@")[-1].split("/")[0] if "@" in redis_url else redis_url.split("//")[-1].split("/")[0]
        st.markdown(f"**Redis**\n\n`{redis_host}`")
        if test_redis_connection():
            st.markdown(status_badge("ONLINE", "#28a745"), unsafe_allow_html=True)
        else:
            st.markdown(status_badge("OFFLINE", "#dc3545", animate=True), unsafe_allow_html=True)

    with h_col3:
        ai_host = OLLAMA_BASE_URL.replace("http://", "").replace("https://", "")
        st.markdown(f"**AI Service**\n\n`{ai_host}`")
        if test_ollama_connection():
            st.markdown(status_badge("READY", "#28a745"), unsafe_allow_html=True)
        else:
            st.markdown(status_badge("UNREACHABLE", "#ffc107", animate=True), unsafe_allow_html=True)

    with h_col4:
        smtp_host = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        st.markdown(f"**Email (SMTP)**\n\n`{smtp_host}`")
        if test_smtp_connection():
            st.markdown(status_badge("CONNECTED", "#28a745"), unsafe_allow_html=True)
        else:
            st.markdown(status_badge("OFFLINE", "#dc3545", animate=True), unsafe_allow_html=True)

    st.divider()

    # --- 1.5 RECENT SYSTEM ACTIVITY (MOVED FROM DASHBOARD) ---
    st.subheader("🕒 Recent System Activity")
    try:
        audit_query = """
            SELECT timestamp as "Time", user_name as "User", action as "Action", ip_address as "IP"
            FROM activity_logs
            ORDER BY timestamp DESC LIMIT 5
        """
        rows = conn.execute(audit_query).fetchall()
        df_recent = pd.DataFrame(rows, columns=["Time", "User", "Action", "IP"])
        st.table(df_recent)
    except Exception as e:
        conn.rollback()
        st.caption("No recent activity logs found.")

    st.divider()

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
            conn.execute("UPDATE users SET dark_mode_enabled = %s WHERE id = %s", (dark_mode, uid))
            conn.commit()
            log_activity(conn, "SETTING_CHANGE", f"User set dark mode to {dark_mode}")
            st.toast("Theme preference saved!")
        except Exception as e:
            st.error(f"Failed to save theme preference: {e}")
            st.session_state["dark_mode"] = current_mode # Revert on failure
        st.rerun()

    st.divider()
    st.subheader("🤖 AI Model Configuration")
    st.write("Override the default LLM model used for video metadata and safety analysis.")

    # Fetch available models from Ollama
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    available_models = []
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=2)
        if resp.status_code == 200:
            available_models = [m['name'] for m in resp.json().get('models', [])]
    except Exception:
        pass

    # Get current overrides from system_settings
    row_m = conn.execute("SELECT value FROM system_settings WHERE key='ollama_model_override'").fetchone()
    current_m_override = row_m[0] if row_m else None

    row_v = conn.execute("SELECT value FROM system_settings WHERE key='ollama_vision_model_override'").fetchone()
    current_v_override = row_v[0] if row_v else None

    row_al = conn.execute("SELECT value FROM system_settings WHERE key='ai_worker_memory_limit'").fetchone()
    ai_mem_limit = int(row_al[0]) if row_al else 2048

    row_bl = conn.execute("SELECT value FROM system_settings WHERE key='bot_worker_memory_limit'").fetchone()
    bot_mem_limit = int(row_bl[0]) if row_bl else 1024

    env_default = os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct")
    env_v_default = os.getenv("OLLAMA_VISION_MODEL", "bakllava")
    options = ["Use Environment Default"] + available_models

    # Determine current selection index
    default_idx = 0
    if current_m_override and current_m_override in options:
        default_idx = options.index(current_m_override)

    default_v_idx = 0
    if current_v_override and current_v_override in options:
        default_v_idx = options.index(current_v_override)

    selected_model = st.selectbox(
        "Select Primary LLM",
        options=options,
        index=default_idx,
        help=f"Used for text analysis and metadata. Env default: {env_default}"
    )

    selected_vision_model = st.selectbox(
        "Select Vision Model",
        options=options,
        index=default_v_idx,
        help=f"Used for image/video frame analysis. Env default: {env_v_default or 'None'}"
    )

    st.write("**Resource Safety Limits**")
    col_m1, col_m2 = st.columns(2)
    new_ai_limit = col_m1.number_input("AI Worker Limit (MB)", min_value=512, max_value=16384, value=ai_mem_limit, step=256)
    new_bot_limit = col_m2.number_input("Bot Worker Limit (MB)", min_value=256, max_value=4096, value=bot_mem_limit, step=128)

    st.divider()
    st.subheader("📉 Auto-Scale Down (Experimental)")
    st.write("Automatically switch to a smaller model if memory usage is consistently high.")

    # Load Auto-Scale Settings
    as_enabled = conn.execute("SELECT value FROM system_settings WHERE key='ai_auto_scale_enabled'").fetchone()
    as_thresh = conn.execute("SELECT value FROM system_settings WHERE key='ai_auto_scale_threshold_mb'").fetchone()
    as_model = conn.execute("SELECT value FROM system_settings WHERE key='ai_auto_scale_down_model'").fetchone()
    as_counts = conn.execute("SELECT value FROM system_settings WHERE key='ai_auto_scale_consecutive_counts'").fetchone()

    is_as_on = st.toggle("Enable Auto-Scale Down", value=(as_enabled and as_enabled[0] == '1'))

    col_as1, col_as2 = st.columns(2)
    as_threshold_mb = col_as1.number_input("Trigger Threshold (MB)", min_value=512, max_value=8192, value=int(as_thresh[0]) if as_thresh else 1500)
    as_samples = col_as2.number_input("Consecutive Samples", min_value=1, max_value=10, value=int(as_counts[0]) if as_counts else 3)

    failover_options = ["Use Environment Default"] + available_models
    failover_idx = 0
    if as_model and as_model[0] in failover_options:
        failover_idx = failover_options.index(as_model[0])

    selected_failover = st.selectbox("Failover Model", options=failover_options, index=failover_idx, help="Model to use when auto-scale is active.")

    if st.button("Save Model Configuration", width="stretch", type="primary"):
        # Save Auto-Scale Settings
        conn.execute("INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", ("ai_auto_scale_enabled", "1" if is_as_on else "0"))
        conn.execute("INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", ("ai_auto_scale_threshold_mb", str(as_threshold_mb)))
        conn.execute("INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", ("ai_auto_scale_consecutive_counts", str(as_samples)))
        conn.execute("INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", ("ai_auto_scale_down_model", selected_failover if selected_failover != "Use Environment Default" else None))

        # Save Primary LLM
        val_m = selected_model if selected_model != "Use Environment Default" else None
        if val_m:
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("ollama_model_override", val_m)
            )
        else:
            conn.execute("DELETE FROM system_settings WHERE key='ollama_model_override'")

        # Save Vision Model
        val_v = selected_vision_model if selected_vision_model != "Use Environment Default" else None
        if val_v:
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("ollama_vision_model_override", val_v)
            )
        else:
            conn.execute("DELETE FROM system_settings WHERE key='ollama_vision_model_override'")

        # Save Memory Limits
        conn.execute("INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    ("ai_worker_memory_limit", str(new_ai_limit)))
        conn.execute("INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    ("bot_worker_memory_limit", str(new_bot_limit)))

        conn.commit()
        log_activity(conn, "SETTING_CHANGE", f"Changed models - LLM: {selected_model}, Vision: {selected_vision_model}")
        st.success("AI model preferences updated!")
        time.sleep(1)
        st.rerun()

    st.divider()
    st.subheader("🧹 Data Management")

    # --- STORAGE METRICS ---
    try:
        # 1. Database Size (Postgres Internal)
        db_size_row = conn.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()
        db_size_str = db_size_row[0] if db_size_row else "N/A"

        # 2. Uploads Directory Size
        uploads_path = Path("uploads")
        uploads_path.mkdir(exist_ok=True)
        total_bytes = sum(f.stat().st_size for f in uploads_path.rglob('*') if f.is_file())

        def format_size(size):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024: return f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} TB"

        # 3. Processed Videos Count
        processed_count_row = conn.execute("SELECT COUNT(*) FROM submissions WHERE processed = 1").fetchone()
        processed_count = processed_count_row[0] if processed_count_row else 0

        sm_col1, sm_col2, sm_col3 = st.columns(3)
        sm_col1.metric("Database Storage", db_size_str)
        sm_col2.metric("Media Storage", format_size(total_bytes))
        sm_col3.metric("Processed Videos", f"{processed_count} files")
    except Exception as e:
        conn.rollback()
        st.caption(f"Storage metrics currently unavailable: {e}")

    dm_col1, dm_col2, dm_col3 = st.columns(3)

    if dm_col1.button("🗑️ Clear Health Logs", help="Deletes historical Redis health logs.", width="stretch"):
        try:
            conn.execute("DELETE FROM redis_health_logs")
            conn.commit()
            log_activity(conn, "DATA_CLEANUP", f"User {username} cleared Redis Health Logs")
            st.success("Redis health logs cleared successfully.")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            conn.rollback()
            st.error(f"Failed to clear logs: {e}")

    if dm_col2.button("🗑️ Clear Slow Query Logs", help="Deletes historical slow query data.", width="stretch"):
        try:
            conn.execute("DELETE FROM slow_query_logs")
            conn.commit()
            log_activity(conn, "DATA_CLEANUP", f"User {username} cleared Slow Query Logs")
            st.success("Slow query logs cleared.")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            conn.rollback()
            st.error(f"Failed to clear slow query logs: {e}")

    if dm_col3.button("🔍 Validate Paths", help="Checks if all submitted video/audio files exist on the server disk.", width="stretch"):
        try:
            results = conn.execute("SELECT id, video_path, audio_path FROM submissions WHERE video_path IS NOT NULL OR audio_path IS NOT NULL").fetchall()
            missing = []
            checked_count = 0
            for sub_id, v_path, a_path in results:
                checked_count += 1
                if v_path and not os.path.exists(v_path):
                    missing.append(f"ID {sub_id}: Video missing -> `{v_path}`")
                if a_path and not os.path.exists(a_path):
                    missing.append(f"ID {sub_id}: Audio missing -> `{a_path}`")

            if not missing:
                st.success(f"Validation complete. All {checked_count} file references are valid!")
            else:
                st.warning(f"Found {len(missing)} missing files out of {checked_count} checked.")
                with st.expander("View Missing Files Details"):
                    for item in missing:
                        st.markdown(f"- {item}")
            log_activity(conn, "FILE_VALIDATION", f"User {username} validated paths. {len(missing)}/{checked_count} files missing.")
        except Exception as e:
            conn.rollback()
            st.error(f"Validation failed: {e}")

    dm_col4, dm_col5 = st.columns(2)

    if dm_col4.button("🗑️ Purge Missing Entries", help="Permanently removes database records from 'submissions' if their associated video or audio files are no longer found on the server disk.", width="stretch"):
        try:
            results = conn.execute("SELECT id, video_path, audio_path FROM submissions WHERE video_path IS NOT NULL OR audio_path IS NOT NULL").fetchall()
            to_delete = []
            for sub_id, v_path, a_path in results:
                # Identify records where a referenced file is missing
                v_missing = v_path and not os.path.exists(v_path)
                a_missing = a_path and not os.path.exists(a_path)
                if v_missing or a_missing:
                    to_delete.append(sub_id)

            if to_delete:
                placeholder = ",".join(["%s"] * len(to_delete))
                conn.execute(f"DELETE FROM submissions WHERE id IN ({placeholder})", to_delete)
                conn.commit()
                log_activity(conn, "DATA_CLEANUP", f"User {username} purged {len(to_delete)} missing submissions from the database.")
                st.success(f"Purge complete. {len(to_delete)} ghost entries removed.")
            else:
                st.info("No invalid database entries found to purge.")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            conn.rollback()
            st.error(f"Purge failed: {e}")

    if dm_col5.button("🧹 30-Day Storage Cleanup", help="Deletes all files in the 'uploads/' folder that are older than 30 days to reclaim disk space.", width="stretch"):
        try:
            uploads_dir = Path("uploads")
            cutoff = time.time() - (30 * 24 * 3600) # 30 days in seconds
            deleted_count = 0
            if uploads_dir.exists():
                for f in uploads_dir.rglob('*'):
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        f.unlink()
                        deleted_count += 1
            log_activity(conn, "DATA_CLEANUP", f"User {username} performed a 30-day storage cleanup, removing {deleted_count} files.")
            st.success(f"Cleanup complete. {deleted_count} old files removed from storage.")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Storage cleanup failed: {e}")
