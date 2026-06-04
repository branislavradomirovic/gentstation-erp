import os
import streamlit as st
import json
import time
import pandas as pd
import requests
from pathlib import Path
from core.activity_logger import log_activity
from core.database import (
    test_redis_connection,
    DB_HOST,
    get_schema_readiness,
)
from core.video_processor import (
    test_ollama_connection,
    OLLAMA_BASE_URL,
    _select_model,
)
from core.comm_service import test_smtp_connection
from core.auth import verify_password, hash_password
from ui.header import render_page_header


AI_MEMORY_LIMIT_MB = int(os.getenv("AI_WORKER_MEMORY_LIMIT_MB", "2048"))


def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def test_bot_worker_status(conn):
    """Checks if the Telegram bot worker is reporting an online status in the database."""
    try:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key='telegram_bot_status'"
        ).fetchone()
        if row and row[0]:
            status_info = json.loads(row[0])
            last_ts = status_info.get("last_update_ts", 0)
            # Consider online if status is 'online' and heartbeat is less than 120 seconds old
            if (
                status_info.get("status") == "online"
                and (time.time() - float(last_ts)) < 120
            ):
                return True
    except Exception:
        pass
    return False


def _get_ollama_models(base_url: str) -> set[str]:
    """Return the set of installed Ollama model names."""
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=2)
        if resp.status_code == 200:
            return {m["name"] for m in resp.json().get("models", []) if m.get("name")}
    except Exception:
        pass
    return set()


def _get_effective_ai_models() -> list[str]:
    """Return the runtime model names the app will try to use."""
    models = [_select_model(False)]
    vision_model = _select_model(True)
    if vision_model not in models:
        models.append(vision_model)
    return [model for model in models if model]


def _get_missing_ai_models(base_url: str) -> list[str]:
    """Return configured AI models that are not installed in Ollama."""
    available = _get_ollama_models(base_url)
    return [model for model in _get_effective_ai_models() if model not in available]


def render(conn):
    st.markdown(
        """
        <style>
            .gs-status-dot {
                display:inline-flex;
                align-items:center;
                justify-content:center;
                min-width:5.9rem;
                padding:0.3rem 0.7rem;
                border-radius:999px;
                font-size:0.78rem;
                font-weight:700;
                color:#fff;
            }
            .gs-status-card {
                border:1px solid rgba(15, 23, 42, 0.08);
                border-radius:16px;
                padding:0.95rem 1rem;
                background:linear-gradient(180deg, rgba(255,255,255,0.98), rgba(247,249,252,0.95));
                box-shadow:0 12px 24px rgba(15, 23, 42, 0.05);
                min-height:8.25rem;
            }
            .gs-status-label {
                font-size:0.78rem;
                text-transform:uppercase;
                letter-spacing:0.08em;
                color:#5b6474;
                font-weight:700;
            }
            .gs-status-host {
                margin:0.3rem 0 0.8rem 0;
                font-size:1rem;
                font-weight:700;
                color:#111827;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    def _status_badge(label, color):
        return f'<span class="gs-status-dot" style="background:{color};">{label}</span>'

    def _format_size(size):
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    render_page_header("⚙ Settings")
    st.markdown(
        '<div class="gs-page-intro">Centralize profile preferences, service health, AI runtime policy, and operational defaults here. Development-only controls have been removed so this page stays focused on day-to-day production administration.</div>',
        unsafe_allow_html=True,
    )

    uid = st.session_state.get("user_id")
    username = st.session_state.get("username")
    user_role = st.session_state.get("user_role")

    total_open_alerts = 0
    try:
        total_open_alerts = conn.execute(
            "SELECT COUNT(*) FROM ai_alerts WHERE status IN ('new', 'acknowledged')"
        ).fetchone()[0]
    except Exception:
        conn.rollback()

    h1, h2, h3 = st.columns([2.4, 1, 1], vertical_alignment="bottom")
    with h1:
        st.markdown("#### Service Health")
        st.caption(
            f"{total_open_alerts} unresolved alert(s) currently require attention."
        )
    with h2:
        if st.button("Open Monitoring", key="nav_ai_monitoring", width="stretch"):
            st.session_state.active_page = "AI Monitoring"
            st.rerun()
    with h3:
        if st.button("Open Audit Log", key="nav_audit_log", width="stretch"):
            st.session_state.active_page = "Audit Log"
            st.rerun()

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_host = (
        redis_url.split("@")[-1].split("/")[0]
        if "@" in redis_url
        else redis_url.split("//")[-1].split("/")[0]
    )
    smtp_host = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    ai_host = OLLAMA_BASE_URL.replace("http://", "").replace("https://", "")
    missing_models = _get_missing_ai_models(OLLAMA_BASE_URL) if test_ollama_connection() else []
    redis_online = test_redis_connection()
    bot_online = test_bot_worker_status(conn)
    external_telegram_worker_enabled = _env_bool(
        "EXTERNAL_TELEGRAM_WORKER_ENABLED", "0"
    )

    cards = [
        ("Database", DB_HOST, "ONLINE" if conn else "OFFLINE", "#28a745" if conn else "#dc3545", None),
        ("Redis", redis_host, "ONLINE" if redis_online else "OFFLINE", "#28a745" if redis_online else "#dc3545", None),
        ("AI Service", ai_host, "DEGRADED" if missing_models else ("READY" if test_ollama_connection() else "UNREACHABLE"), "#ffc107" if missing_models or not test_ollama_connection() else "#28a745", ("Missing model(s): " + ", ".join(missing_models)) if missing_models else "BakLLaVA is available for processing."),
        ("Telegram Bot", "Worker", "ONLINE" if bot_online else ("EXPECTED" if external_telegram_worker_enabled else "OFFLINE"), "#28a745" if bot_online else ("#ffc107" if external_telegram_worker_enabled else "#dc3545"), "Uploader notifications and intake rely on this service."),
        ("Email", smtp_host, "CONNECTED" if test_smtp_connection(on_retry=None) else "OFFLINE", "#28a745" if test_smtp_connection(on_retry=None) else "#dc3545", "Manager report emails use this SMTP connection."),
    ]

    health_cols = st.columns(5)
    for col, (label, host, status, color, caption) in zip(health_cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="gs-status-card">
                    <div class="gs-status-label">{label}</div>
                    <div class="gs-status-host">{host}</div>
                    {_status_badge(status, color)}
                    <div style="margin-top:0.75rem; color:#5b6474; font-size:0.84rem; line-height:1.45;">{caption or ""}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.divider()

    left_col, right_col = st.columns([1.05, 0.95], gap="large")

    with left_col:
        st.markdown("#### Profile & Access")
        st.markdown(f"Signed in as **{username}**")
        st.caption(f"Role: {user_role}")

        current_mode = st.session_state.get("dark_mode", False)
        dark_mode = st.toggle("Enable dark mode", value=current_mode)
        if dark_mode != current_mode:
            st.session_state["dark_mode"] = dark_mode
            try:
                conn.execute(
                    "UPDATE users SET dark_mode_enabled = %s WHERE id = %s",
                    (dark_mode, uid),
                )
                conn.commit()
                log_activity(conn, "SETTING_CHANGE", f"User set dark mode to {dark_mode}")
                st.toast("Theme preference saved.")
            except Exception as e:
                conn.rollback()
                st.error(f"Failed to save theme preference: {e}")
                st.session_state["dark_mode"] = current_mode
            st.rerun()

        with st.form("pw_form"):
            current_pw = st.text_input("Current password", type="password")
            new_pw = st.text_input("New password", type="password")
            confirm_pw = st.text_input("Confirm new password", type="password")

            if st.form_submit_button("Update Password", width="stretch"):
                if not current_pw or not new_pw:
                    st.error("Please fill in all fields.")
                elif new_pw != confirm_pw:
                    st.error("New passwords do not match.")
                else:
                    row = conn.execute(
                        "SELECT password_hash FROM users WHERE id = %s", (uid,)
                    ).fetchone()
                    if row and verify_password(current_pw, row[0]):
                        conn.execute(
                            "UPDATE users SET password_hash = %s, force_password_change = FALSE WHERE id = %s",
                            (hash_password(new_pw), uid),
                        )
                        conn.commit()
                        log_activity(conn, "PASSWORD_CHANGE", f"User {username} changed password")
                        st.success("Password updated successfully.")
                    else:
                        st.error("Incorrect current password.")

    with right_col:
        st.markdown("#### Recent Activity")
        try:
            audit_query = """
                SELECT timestamp as "Time", user_name as "User", action as "Action", ip_address as "IP"
                FROM activity_logs
                ORDER BY timestamp DESC LIMIT 8
            """
            rows = conn.execute(audit_query).fetchall()
            df_recent = pd.DataFrame(rows, columns=["Time", "User", "Action", "IP"])
            st.dataframe(df_recent, use_container_width=True, hide_index=True)
        except Exception:
            conn.rollback()
            st.caption("No recent activity logs found.")

    st.divider()

    runtime_tab, categories_tab, retention_tab = st.tabs(
        ["AI Runtime", "Station Categories", "Storage & Retention"]
    )

    with runtime_tab:
        st.markdown("#### AI Runtime & Operations")
        ai_col, ops_col = st.columns(2, gap="large")

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        available_models = []
        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=2)
            if resp.status_code == 200:
                available_models = [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            pass

        fixed_model = (
            os.getenv("OLLAMA_VISION_MODEL")
            or os.getenv("OLLAMA_MODEL")
            or "bakllava:latest"
        ).strip()
        row_al = conn.execute(
            "SELECT value FROM system_settings WHERE key='ai_worker_memory_limit'"
        ).fetchone()
        ai_mem_limit = int(row_al[0]) if row_al else AI_MEMORY_LIMIT_MB
        row_bl = conn.execute(
            "SELECT value FROM system_settings WHERE key='bot_worker_memory_limit'"
        ).fetchone()
        bot_mem_limit = int(row_bl[0]) if row_bl else 1024

        row_over = conn.execute(
            "SELECT value FROM system_settings WHERE key='staffing_threshold_over'"
        ).fetchone()
        row_under = conn.execute(
            "SELECT value FROM system_settings WHERE key='staffing_threshold_under'"
        ).fetchone()
        staff_over = int(row_over[0]) if row_over and row_over[0] else 5
        staff_under = int(row_under[0]) if row_under and row_under[0] else 2

        with ai_col:
            st.markdown("##### AI Runtime")
            st.code(fixed_model, language="text")
            if available_models and fixed_model not in available_models:
                st.warning(
                    f"The configured BakLLaVA model `{fixed_model}` is not currently listed by Ollama."
                )
            else:
                st.caption("BakLLaVA is the only model the application uses for analysis.")

            new_ai_limit = st.number_input(
                "AI worker memory limit (MB)",
                min_value=512,
                max_value=16384,
                value=ai_mem_limit,
                step=256,
            )
            new_bot_limit = st.number_input(
                "Bot worker memory limit (MB)",
                min_value=256,
                max_value=4096,
                value=bot_mem_limit,
                step=128,
            )

        with ops_col:
            st.markdown("##### Operational Defaults")
            new_staff_over = st.number_input(
                "Overstaffed threshold",
                min_value=1,
                value=staff_over,
                key="cfg_staff_over",
            )
            new_staff_under = st.number_input(
                "Understaffed threshold",
                min_value=0,
                value=staff_under,
                key="cfg_staff_under",
            )
            st.caption(
                "These thresholds drive the staffing indicators shown in the station directory and overview screens."
            )

        if st.button("Save Runtime & Operational Settings", width="stretch", type="primary"):
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("ollama_model_override", fixed_model),
            )
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("ollama_vision_model_override", fixed_model),
            )
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("ai_auto_scale_enabled", "0"),
            )
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("ai_auto_scale_active", "0"),
            )
            conn.execute("DELETE FROM system_settings WHERE key='ai_auto_scale_down_model'")
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("ai_worker_memory_limit", str(int(new_ai_limit))),
            )
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("bot_worker_memory_limit", str(int(new_bot_limit))),
            )
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("staffing_threshold_over", str(int(new_staff_over))),
            )
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("staffing_threshold_under", str(int(new_staff_under))),
            )
            conn.commit()
            log_activity(
                conn,
                "SETTING_CHANGE",
                f"Updated runtime settings: model={fixed_model}, ai_mem={int(new_ai_limit)}, bot_mem={int(new_bot_limit)}, staffing=({int(new_staff_under)}-{int(new_staff_over)})",
            )
            st.success("Runtime and operational settings updated.")
            time.sleep(0.8)
            st.rerun()

    with categories_tab:
        st.markdown("#### Station Categories")
        st.caption(
            "Manage the station types used across directories and maps. The duplicate category composition chart has been removed from Settings to keep this area focused on administration."
        )

        category_schema = get_schema_readiness(conn)
        if not category_schema["is_ready"]:
            st.warning(
                "Station category management is unavailable because the Postgres schema is behind the current code."
            )
            for msg in category_schema["blockers"] + category_schema["warnings"]:
                st.caption(msg)
        else:
            categories_df = pd.read_sql_query(
                "SELECT * FROM station_categories ORDER BY name", conn
            )
            current_categories = {
                row["name"]: {
                    "id": row["id"],
                    "color": row["color"],
                    "description": row["description"],
                }
                for _, row in categories_df.iterrows()
            }

            cat_counts = {}
            try:
                counts_res = conn.execute(
                    "SELECT sc.name, COUNT(s.id) FROM station_categories sc LEFT JOIN stations s ON s.category_id = sc.id GROUP BY sc.id"
                ).fetchall()
                cat_counts = {str(row[0]): row[1] for row in counts_res}
            except Exception:
                conn.rollback()

            valid_colors = [
                "blue", "green", "red", "purple", "orange", "darkred", "lightred",
                "beige", "darkblue", "darkgreen", "cadetblue", "darkpurple",
                "pink", "lightblue", "lightgreen", "gray", "black"
            ]

            add_col, manage_col = st.columns(2, gap="large")
            with add_col:
                with st.form("add_category_form", clear_on_submit=True):
                    st.markdown("##### Add Category")
                    new_cat_name = st.text_input("Category name", placeholder="e.g. Highway")
                    new_cat_color = st.selectbox("Marker color", options=valid_colors)
                    new_cat_desc = st.text_area(
                        "Description",
                        placeholder="Short operational description",
                        max_chars=200,
                    )
                    if st.form_submit_button("Create Category", use_container_width=True):
                        cleaned_name = (new_cat_name or "").strip()
                        if not cleaned_name:
                            st.error("Name is required.")
                        elif any(cleaned_name.lower() == k.lower() for k in current_categories.keys()):
                            st.error("Category already exists.")
                        else:
                            conn.execute(
                                "INSERT INTO station_categories (name, color, description) VALUES (%s, %s, %s)",
                                (cleaned_name, new_cat_color, (new_cat_desc or "").strip()),
                            )
                            conn.commit()
                            log_activity(conn, "CREATE_CATEGORY", f"Added category: {cleaned_name}")
                            st.success(f"Category '{cleaned_name}' created.")
                            time.sleep(0.8)
                            st.rerun()

            with manage_col:
                st.markdown("##### Manage Existing")
                sorted_cats = sorted(list(current_categories.keys()))
                cat_to_edit = st.selectbox(
                    "Category",
                    options=sorted_cats,
                    format_func=lambda x: f"{x} ({cat_counts.get(x, 0)} stations)",
                )
                if cat_to_edit:
                    cat_data = current_categories[cat_to_edit]
                    current_color = cat_data.get("color", "gray")
                    current_desc = cat_data.get("description", "")

                    col_a, col_b = st.columns(2)
                    new_color = col_a.selectbox(
                        "Marker color",
                        options=valid_colors,
                        index=valid_colors.index(current_color) if current_color in valid_colors else 0,
                        key=f"color_{cat_to_edit}",
                    )
                    if col_b.button("Save Details", use_container_width=True, key=f"btn_upd_{cat_to_edit}"):
                        conn.execute(
                            "UPDATE station_categories SET color = %s, description = %s WHERE id = %s",
                            (new_color, (st.session_state.get(f'desc_{cat_to_edit}') or "").strip(), current_categories[cat_to_edit]["id"]),
                        )
                        conn.commit()
                        log_activity(conn, "UPDATE_CATEGORY", f"Updated category: {cat_to_edit}")
                        st.success("Category updated.")
                        time.sleep(0.8)
                        st.rerun()

                    st.text_area(
                        "Description",
                        value=current_desc,
                        key=f"desc_{cat_to_edit}",
                        max_chars=200,
                    )

                    if cat_to_edit.lower() != "other":
                        if st.button(f"Delete '{cat_to_edit}'", type="secondary", use_container_width=True):
                            st.session_state[f"confirm_cat_del_{cat_to_edit}"] = True

                        if st.session_state.get(f"confirm_cat_del_{cat_to_edit}"):
                            st.warning(
                                f"Confirm deletion only after stations are reassigned from '{cat_to_edit}'."
                            )
                            c1, c2 = st.columns(2)
                            if c1.button("Confirm Delete", type="primary", use_container_width=True):
                                conn.execute(
                                    "DELETE FROM station_categories WHERE id = %s",
                                    (current_categories[cat_to_edit]["id"],),
                                )
                                conn.commit()
                                log_activity(conn, "DELETE_CATEGORY", f"Deleted category: {cat_to_edit}")
                                st.session_state.pop(f"confirm_cat_del_{cat_to_edit}", None)
                                st.success("Category removed.")
                                time.sleep(0.8)
                                st.rerun()
                            if c2.button("Cancel", use_container_width=True):
                                st.session_state.pop(f"confirm_cat_del_{cat_to_edit}", None)
                                st.rerun()
                    else:
                        st.caption("The 'Other' category is a protected system fallback.")

    with retention_tab:
        st.markdown("#### Storage & Retention")
        st.caption(
            "Videos remain on disk only while waiting or processing. Successful jobs clear the media file automatically and keep the AI result in Postgres."
        )

        try:
            db_size_row = conn.execute(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            ).fetchone()
            db_size_str = db_size_row[0] if db_size_row else "N/A"

            uploads_path = Path("uploads")
            uploads_path.mkdir(exist_ok=True)
            total_bytes = sum(
                f.stat().st_size for f in uploads_path.rglob("*") if f.is_file()
            )

            processed_count_row = conn.execute(
                "SELECT COUNT(*) FROM submissions WHERE processed = 1"
            ).fetchone()
            processed_count = processed_count_row[0] if processed_count_row else 0

            pending_media_row = conn.execute(
                "SELECT COUNT(*) FROM submissions WHERE video_path IS NOT NULL"
            ).fetchone()
            pending_media = pending_media_row[0] if pending_media_row else 0

            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("Database Storage", db_size_str)
            sm2.metric("Media Storage", _format_size(total_bytes))
            sm3.metric("Processed Reports", processed_count)
            sm4.metric("Queued Media Files", pending_media)
        except Exception as e:
            conn.rollback()
            st.caption(f"Storage metrics currently unavailable: {e}")

        if st.button(
            "30-Day Uploads Cleanup",
            help="Delete leftover files in uploads/ that are older than 30 days.",
            width="stretch",
        ):
            try:
                uploads_dir = Path("uploads")
                cutoff = time.time() - (30 * 24 * 3600)
                deleted_count = 0
                if uploads_dir.exists():
                    for f in uploads_dir.rglob("*"):
                        if f.is_file() and f.stat().st_mtime < cutoff:
                            f.unlink()
                            deleted_count += 1
                log_activity(
                    conn,
                    "DATA_CLEANUP",
                    f"User {username} performed a 30-day storage cleanup, removing {deleted_count} files.",
                )
                st.success(f"Cleanup complete. {deleted_count} old files removed.")
                time.sleep(0.8)
                st.rerun()
            except Exception as e:
                st.error(f"Storage cleanup failed: {e}")
