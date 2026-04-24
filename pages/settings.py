import streamlit as st
import hashlib
import json
import time
import os
import requests
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
            conn.execute("UPDATE users SET dark_mode_enabled = %s WHERE id = %s", (dark_mode, uid))
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

    bot_status_info = {}
    if bot_row and bot_row[0]:
        try:
            bot_status_info = json.loads(bot_row[0])
        except json.JSONDecodeError:
            bot_status_info = {"status": "unknown"}

    bot_status = bot_status_info.get("status", "offline")
    bot_last_update_ts = bot_status_info.get("last_update_ts")
    bot_details = bot_status_info.get("details")
    bot_stale = False
    if bot_last_update_ts:
        try:
            bot_stale = (time.time() - float(bot_last_update_ts)) > 90
        except Exception:
            bot_stale = False

    token_configured = bool((os.getenv("TELEGRAM_BOT_TOKEN") or "").strip())
    if not token_configured:
        st.caption("Why offline: `TELEGRAM_BOT_TOKEN` is missing in `.env`, so the bot worker does not start.")
    elif not bot_row or not bot_row[0]:
        st.caption("Why offline: no Telegram heartbeat has been written yet. Worker may not be started yet.")
    elif bot_status == "error":
        st.caption(f"Why offline: bot worker reported error. Details: {bot_details or 'N/A'}")
    elif bot_stale:
        st.caption("Why offline: heartbeat is stale. Worker process may be stuck or terminated.")
    elif bot_status in {"offline", "stopped"}:
        st.caption("Why offline: worker is not running right now.")

    st.write("**Registered Bots**")
    linked_rows = conn.execute(
        """
        SELECT
            e.name || ' ' || e.surname AS employee_name,
            COALESCE(r.name, rs.name, '-') AS region_name,
            COALESCE(st.name, '-') AS station_name,
            e.telegram_chat_id
        FROM employees e
        LEFT JOIN stations st ON e.station_id = st.id
        LEFT JOIN regions r ON e.region_id = r.id
        LEFT JOIN regions rs ON st.region_id = rs.id
        WHERE e.telegram_chat_id IS NOT NULL
        ORDER BY employee_name
        """
    ).fetchall()

    if linked_rows:
        reg_bot_data = []
        for employee_name, region_name, station_name, _ in linked_rows:
            reg_bot_data.append(
                {
                    "Name": employee_name,
                    "Region": region_name,
                    "Station": station_name,
                    "Bot Status": "Linked",
                }
            )
        st.dataframe(reg_bot_data, width="stretch", hide_index=True)
    else:
        st.caption("No registered/linked bot users yet.")

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
    ai_last_update_ts = ai_status_info.get("last_update_ts")
    ai_stale = False
    if ai_last_update_ts:
        try:
            ai_stale = (time.time() - float(ai_last_update_ts)) > 180
        except Exception:
            ai_stale = False

    if ai_status == "processing":
        total = ai_status_info.get("total", 0)
        current = ai_status_info.get("current", 0)
        progress_val = (current / total) if total > 0 else 0
        pending_row = conn.execute("SELECT COUNT(*) FROM submissions WHERE processed = 0 AND video_path IS NOT NULL").fetchone()
        pending_count = pending_row[0] if pending_row else 0

        if pending_count == 0 and (current >= total or ai_stale):
            st.warning("⚠️ AI status was left in 'processing', but there are no pending tasks.")
            st.caption("If this persists, restart AI worker once to refresh status.")
        else:
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

    st.write("**Ollama Connectivity**")

    def _ollama_candidate_urls():
        base = (os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") or "").rstrip("/")
        local_only = os.getenv("OLLAMA_LOCAL_ONLY", "1").strip().lower() in {"1", "true", "yes", "on"}
        seen = set()
        urls = []

        def add(url):
            url = (url or "").rstrip("/")
            if url and url not in seen:
                seen.add(url)
                urls.append(url)

        add(base)
        add("http://localhost:11434")
        add("http://127.0.0.1:11434")

        if "localhost" in base:
            add(base.replace("localhost", "127.0.0.1"))
        if "127.0.0.1" in base:
            add(base.replace("127.0.0.1", "localhost"))
        if "host.docker.internal" in base:
            add(base.replace("host.docker.internal", "localhost"))
            add(base.replace("host.docker.internal", "127.0.0.1"))

        if not local_only:
            add("http://host.docker.internal:11434")
            if "localhost" in base:
                add(base.replace("localhost", "host.docker.internal"))
            if "127.0.0.1" in base:
                add(base.replace("127.0.0.1", "host.docker.internal"))

        return urls

    if st.button("🔎 Test Ollama Connectivity", width="stretch"):
        checked = []
        success_url = None
        models = []

        for base_url in _ollama_candidate_urls():
            tags_url = f"{base_url}/api/tags"
            try:
                resp = requests.get(tags_url, timeout=5)
                if resp.status_code == 200:
                    payload = resp.json() if resp.content else {}
                    models = payload.get("models", []) or []
                    success_url = base_url
                    break
                checked.append(f"{tags_url} -> HTTP {resp.status_code}")
            except Exception as e:
                checked.append(f"{tags_url} -> {e}")

        if success_url:
            st.success(f"✅ Ollama is reachable at: {success_url}")
            if models:
                model_rows = []
                for m in models:
                    model_rows.append(
                        {
                            "Model": m.get("name") or m.get("model") or "unknown",
                            "Size": m.get("size", "-"),
                            "Modified": m.get("modified_at", "-"),
                        }
                    )
                st.dataframe(model_rows, width="stretch", hide_index=True)
            else:
                st.info("Connected to Ollama, but no models are currently available.")
        else:
            st.error("❌ Could not connect to Ollama `/api/tags` on any candidate URL.")
            st.caption("Checked endpoints:")
            st.code("\n".join(checked) if checked else "No endpoints were checked.", language="text")

    st.divider()
    st.subheader("🛠 Worker Diagnostics")

    def _age_text(ts_value):
        if not ts_value:
            return "No heartbeat yet"
        try:
            age_sec = max(0, int(time.time() - float(ts_value)))
        except Exception:
            return "Unknown"
        mins, sec = divmod(age_sec, 60)
        hrs, mins = divmod(mins, 60)
        if hrs:
            return f"{hrs}h {mins}m {sec}s ago"
        if mins:
            return f"{mins}m {sec}s ago"
        return f"{sec}s ago"

    ai_last_update_ts = ai_status_info.get("last_update_ts")

    pending_row = conn.execute("SELECT COUNT(*) FROM submissions WHERE processed = 0 AND video_path IS NOT NULL").fetchone()
    failed_row = conn.execute("SELECT COUNT(*) FROM submissions WHERE processed = -1").fetchone()
    pending_count = pending_row[0] if pending_row else 0
    failed_count = failed_row[0] if failed_row else 0

    dcol1, dcol2, dcol3, dcol4 = st.columns(4)
    dcol1.metric("Bot heartbeat age", _age_text(bot_last_update_ts))
    dcol2.metric("AI heartbeat age", _age_text(ai_last_update_ts))
    dcol3.metric("Pending queue", pending_count)
    dcol4.metric("Failed queue", failed_count)

    st.caption("Quick restart hints (local development):")
    st.code(
        "pkill -f bot/bot_worker.py\n"
        "pkill -f core/ai_worker.py\n"
        "streamlit run app.py",
        language="bash",
    )
    st.caption(
        "Tip: use `.env` toggles `AUTO_START_TELEGRAM_BOT` and `AUTO_START_AI_WORKER` "
        "to control which worker auto-starts."
    )

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
