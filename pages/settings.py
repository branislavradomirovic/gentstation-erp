import streamlit as st
import hashlib
import json
import time
import os
import requests
from datetime import datetime
from core.activity_logger import log_activity
from core.database import get_pool_stats
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
