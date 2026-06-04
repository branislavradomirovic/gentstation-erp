import streamlit as st
import json
import time
import os
import signal
import logging
from pathlib import Path
from contextlib import suppress
import pandas as pd
from datetime import datetime

try:
    import psutil
    import redis
except ImportError:
    redis = None
from core.video_processor import sample_frames, call_ollama
from core.activity_logger import log_activity
from core.database import (
    get_pool_stats,
    get_system_uptime,
    test_redis_connection,
    DB_HOST,
)
from core.video_processor import test_ollama_connection, OLLAMA_BASE_URL
from ui.header import render_page_header
from pages.settings import test_bot_worker_status  # Re-use the status check

logger = logging.getLogger("gentstation.ai_monitoring")


def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def render(conn):
    render_page_header("🖥️ AI & Service Monitoring")

    # --- System Uptime ---
    # --- 1. COMPREHENSIVE SERVICE HEALTH ---
    st.subheader("🏥 Global Service Health")
    h_col1, h_col2, h_col3, h_col4, h_col5 = st.columns(5)

    def status_badge(is_online, label_on="ONLINE", label_off="OFFLINE"):
        color = "#28a745" if is_online else "#dc3545"
        label = label_on if is_online else label_off
        return f'<span style="background-color:{color}; color:white; padding:4px 12px; border-radius:15px; font-size:0.85rem; font-weight:bold;">{label}</span>'

    with h_col1:
        st.markdown(f"**Database**\n\n`{DB_HOST}`")
        st.markdown(status_badge(conn is not None), unsafe_allow_html=True)

    with h_col2:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        st.markdown(f"**Redis**\n\n`{redis_url.split('/')[-1]}`")
        st.markdown(status_badge(test_redis_connection()), unsafe_allow_html=True)

    with h_col3:
        ai_host = OLLAMA_BASE_URL.replace("http://", "").replace("https://", "")
        st.markdown(f"**AI Service**\n\n`{ai_host}`")
        st.markdown(
            status_badge(test_ollama_connection(), "READY", "UNREACHABLE"),
            unsafe_allow_html=True,
        )

    with h_col4:
        st.markdown("**Bot Worker**\n\n`Telegram`")
        st.markdown(status_badge(test_bot_worker_status(conn)), unsafe_allow_html=True)

    with h_col5:
        scheduler_row = conn.execute(
            "SELECT value FROM system_settings WHERE key='report_scheduler_status'"
        ).fetchone()
        scheduler_auto_start = _env_bool("AUTO_START_REPORT_SCHEDULER", "0")
        external_scheduler_enabled = _env_bool(
            "EXTERNAL_REPORT_SCHEDULER_ENABLED", "0"
        )
        scheduler_online = False
        scheduler_label = "OFFLINE"
        scheduler_caption = None
        if scheduler_row and scheduler_row[0]:
            try:
                scheduler_payload = json.loads(scheduler_row[0])
                scheduler_state = str(
                    scheduler_payload.get("status") or "offline"
                ).lower()
                scheduler_online = scheduler_state in {"starting", "running", "idle"}
                if scheduler_state == "starting":
                    scheduler_label = "STARTING"
                    scheduler_caption = "Booting from application startup."
                elif scheduler_state in {"running", "idle"}:
                    scheduler_label = "READY"
                elif scheduler_state == "error":
                    scheduler_label = "ERROR"
            except Exception:
                scheduler_online = False
        elif scheduler_auto_start or external_scheduler_enabled:
            scheduler_online = True
            scheduler_label = "STARTING"
            scheduler_caption = "Scheduler container is expected. Waiting for first heartbeat."
        st.markdown("**Report Scheduler**\n\n`20:00 Rollups`")
        st.markdown(
            status_badge(scheduler_online, scheduler_label, "OFFLINE"),
            unsafe_allow_html=True,
        )
        if scheduler_caption:
            st.caption(scheduler_caption)

    st.markdown("---")

    # --- 2. WORKER CONTROLS (RESTART) ---
    st.subheader("⚙️ Background Service Controls")
    st.write("Force-restart workers if they appear stale or offline.")

    c_ctrl1, c_col2, c_col3 = st.columns([1, 1, 1])

    def _reset_stuck_jobs_in_db(timeout_seconds=1800):
        cutoff_sql = "NOW() - (%s || ' seconds')::interval"
        conn.execute(
            f"""
            UPDATE submissions
            SET status='pending'
            WHERE status='processing'
              AND processing_started_ts IS NOT NULL
              AND processing_started_ts < {cutoff_sql}
            """,
            (str(int(timeout_seconds)),),
        )
        conn.commit()

    def _restart_service(lock_name, task_name):
        lock_path = Path(f"/tmp/{lock_name}")
        if lock_path.exists():
            try:
                pid = int(lock_path.read_text().strip())
                with suppress(Exception):
                    os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                with suppress(Exception):
                    os.kill(pid, signal.SIGKILL)
                lock_path.unlink(missing_ok=True)
                st.toast(
                    f"Terminated {task_name}. System will auto-spawn a new instance.",
                    icon="🔄",
                )
            except Exception as e:
                st.error(f"Restart failed: {e}")
        else:
            st.info(f"No active lock for {task_name}. Spawning now...")

        # Clear any jobs that might have been stuck in 'processing' by the terminated worker
        _reset_stuck_jobs_in_db()
        time.sleep(1)
        st.rerun()

    if c_ctrl1.button("🔄 Restart AI Worker", width="stretch"):
        _restart_service("gentstationai_ai_worker.lock", "AI Worker")
    if c_col2.button("🔄 Restart Bot Worker", width="stretch"):
        _restart_service("gentstationai_bot_worker.lock", "Bot Worker")
    if c_col3.button("🧹 Deep Clean All", type="secondary", width="stretch"):
        st.session_state.active_page = "Settings"  # Redirect to deep clean in settings
        st.rerun()

    st.markdown("---")

    # --- New Real-Time Metrics Widget ---
    st.subheader("⚡ Worker Heartbeat & Resources")
    m_col1, m_col2 = st.columns(2)

    def get_latest_metrics(worker_name):
        row = conn.execute(
            """
            SELECT cpu_percent, memory_mb, timestamp
            FROM worker_health_logs
            WHERE worker_name = %s
            ORDER BY timestamp DESC LIMIT 1
        """,
            (worker_name,),
        ).fetchone()
        return row if row else (0.0, 0.0, None)

    ai_cpu, ai_mem, ai_ts = get_latest_metrics("ai_worker")
    bot_cpu, bot_mem, bot_ts = get_latest_metrics("telegram_bot")

    with m_col1:
        with st.container(border=True):
            st.markdown("**🧠 AI Worker Resources**")
            c1, c2 = st.columns(2)
            c1.metric("CPU", f"{ai_cpu}%")
            c2.metric("Memory", f"{int(ai_mem)} MB")
            if ai_ts:
                st.caption(f"Last sync: {ai_ts.strftime('%H:%M:%S')}")
            st.caption("Idle workers normally show near-zero CPU between jobs.")

    with m_col2:
        with st.container(border=True):
            st.markdown("**🤖 Bot Worker Resources**")
            c1, c2 = st.columns(2)
            c1.metric("CPU", f"{bot_cpu}%")
            c2.metric("Memory", f"{int(bot_mem)} MB")
            if bot_ts:
                st.caption(f"Last sync: {bot_ts.strftime('%H:%M:%S')}")

    if st.button("🔄 Refresh Real-Time Data", width="stretch"):
        st.rerun()

    st.markdown("---")

    st.write("Real-time operational status of AI components and background services.")

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
            updated_str = datetime.fromtimestamp(float(ts)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            st.caption(f"Last update: {updated_str}")
        return status_info

    # --- Worker Status & Control ---
    st.subheader("⚙️ Worker Status & Control")

    w_col1, w_col2 = st.columns(2)

    r_col1, r_col2 = st.columns(2)

    # Redis Check
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    if redis is None:
        r_col1.error("🔴 Redis: Library Missing")
        r_col1.caption("Please install the `redis` library.")
        r_col1.caption("Please run: pip install redis")
    else:
        # Try to fetch last known active time from DB
        last_active_row = conn.execute(
            "SELECT value FROM system_settings WHERE key=%s", ("redis_last_active",)
        ).fetchone()
        last_active_ts = (
            float(last_active_row[0])
            if last_active_row and last_active_row[0]
            else None
        )

        try:
            r = redis.from_url(redis_url, socket_connect_timeout=2)
            r.ping()

            # Update last active in DB on success
            now_ts = time.time()
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("redis_last_active", str(now_ts)),
            )
            conn.commit()

            r_col1.success("✅ Redis: Online")
            r_col1.caption(f"Connected to {redis_url}")
            r_col1.caption(
                f"Last active: {datetime.fromtimestamp(now_ts).strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            r_col1.error(f"🔴 Redis: Offline")
            r_col1.caption(f"Error: {e}")
            if last_active_ts:
                r_col1.caption(
                    f"Last active: {datetime.fromtimestamp(last_active_ts).strftime('%Y-%m-%d %H:%M:%S')}"
                )

    with st.expander("Redis Health History (Last 24h)", expanded=False):
        try:
            # Use the connection passed to the render function
            history_df = pd.read_sql_query(
                """
                SELECT timestamp, is_online
                FROM redis_health_logs
                WHERE timestamp >= NOW() - INTERVAL '24 HOURS'
                ORDER BY timestamp ASC
                """,
                conn,
            )
            if not history_df.empty:
                # Convert boolean to int for charting (1 = Online, 0 = Offline)
                history_df["is_online_int"] = history_df["is_online"].astype(int)
                st.line_chart(history_df.set_index("timestamp")["is_online_int"])
                st.caption("Chart shows 1 for Online, 0 for Offline.")
            else:
                st.info(
                    "No Redis health history available yet. Ensure the Telegram bot worker is running."
                )
        except Exception as e:
            st.warning(f"Could not load Redis health history: {e}")

    # AI Inference Latency Chart
    st.subheader("AI Inference Latency (Last 24h)")
    try:
        latency_df = pd.read_sql_query(
            """
            SELECT timestamp, latency_seconds, model_name
            FROM ai_inference_latency
            WHERE timestamp >= NOW() - INTERVAL '24 HOURS'
            ORDER BY timestamp ASC
            """,
            conn,
        )
        if not latency_df.empty:
            latency_df = latency_df.rename(
                columns={
                    "timestamp": "Timestamp",
                    "latency_seconds": "Latency (s)",
                    "model_name": "Model",
                }
            )
            latency_df = latency_df.sort_values("Timestamp")
            st.write("**Latency (seconds)**")
            st.line_chart(
                latency_df.set_index("Timestamp")[["Latency (s)"]],
                height=260,
            )
            summary_col1, summary_col2, summary_col3 = st.columns(3)
            summary_col1.metric(
                "Latest",
                f"{float(latency_df['Latency (s)'].iloc[-1]):.2f}s",
            )
            summary_col2.metric(
                "24h Average",
                f"{float(latency_df['Latency (s)'].mean()):.2f}s",
            )
            summary_col3.metric(
                "24h Peak",
                f"{float(latency_df['Latency (s)'].max()):.2f}s",
            )
            st.caption(
                "Latency in seconds for BakLLaVA inference. Higher values indicate slower model response times."
            )
        else:
            st.info(
                "No inference latency data recorded yet. Processing more videos will populate this chart."
            )
    except Exception as e:
        st.warning(f"Could not load latency history: {e}")

    # Worker Health Charts
    with st.expander("Worker Resource Usage", expanded=False):
        try:
            health_df = pd.read_sql_query(
                """
                SELECT timestamp, worker_name, cpu_percent, memory_mb
                FROM worker_health_logs
                WHERE timestamp >= NOW() - INTERVAL '24 HOURS'
                ORDER BY timestamp ASC
                """,
                conn,
            )
            if not health_df.empty:
                hcol1, hcol2 = st.columns(2)

                with hcol1:
                    st.write("**CPU Usage (%)**")
                    cpu_chart = health_df.pivot(
                        index="timestamp", columns="worker_name", values="cpu_percent"
                    )
                    st.line_chart(cpu_chart)

                with hcol2:
                    st.write("**Memory Usage (MB)**")
                    mem_chart = health_df.pivot(
                        index="timestamp", columns="worker_name", values="memory_mb"
                    )
                    st.line_chart(mem_chart)

                st.caption(
                    "Monitoring real-time overhead of AI inference and Telegram bot activity."
                )
            else:
                st.info("No worker health data recorded yet.")
        except Exception as e:
            st.warning(f"Could not load worker health history: {e}")

    # AI Success/Failure Rate Chart
    with st.expander("AI Processing Volume", expanded=False):
        st.write("**Hourly Processing Volume**")
        try:
            volume_df = pd.read_sql_query(
                """
                SELECT
                    date_trunc('hour', processed_ts) as hour,
                    COUNT(*) FILTER (WHERE processed = 1) as success,
                    COUNT(*) FILTER (WHERE processed = -1) as failure
                FROM submissions
                WHERE processed_ts >= NOW() - INTERVAL '24 HOURS'
                GROUP BY 1
                ORDER BY 1 ASC
                """,
                conn,
            )
            if not volume_df.empty:
                volume_df = volume_df.set_index("hour")
                st.bar_chart(volume_df)
                st.caption(
                    "Hourly breakdown of completed (Success) vs. exhausted (Failure) AI jobs."
                )
            else:
                st.info("No processing volume data found for the last 24 hours.")
        except Exception as e:
            st.warning(f"Could not load processing volume: {e}")

    st.markdown("---")
    stats = get_pool_stats()
    if stats:
        r_col2.success("✅ Database Health")
        usage_pct = stats["usage_pct"]

        if usage_pct >= 90:
            r_col2.error(f"⚠️ High Pool Usage: {usage_pct}%")
        elif usage_pct >= 70:
            r_col2.warning(f"🟡 Moderate Pool Usage: {usage_pct}%")

        r_col2.metric(
            "Connections In Use",
            f"{stats['checkedout']} / {stats['total_capacity']}",
            f"{usage_pct}% load",
            delta_color="inverse" if usage_pct > 80 else "normal"
        )
        progress_val = min(1.0, usage_pct / 100.0)
        r_col2.progress(progress_val)
    else:
        r_col2.error("🔴 Database Pool: Error")

    # --- Database Query Performance ---
    st.markdown("---")
    st.subheader("📊 Database Query Performance")

    qcol1, qcol2 = st.columns([2, 1])

    try:
        # Aggregated stats for frequent slow queries
        query_stats_df = pd.read_sql_query(
            """
            SELECT
                LEFT(query_text, 100) as "Query Template",
                COUNT(*) as "Hits",
                ROUND(AVG(duration_seconds), 3) as "Avg Latency (s)",
                ROUND(MAX(duration_seconds), 3) as "Max Latency (s)"
            FROM slow_query_logs
            WHERE timestamp >= NOW() - INTERVAL '24 HOURS'
            GROUP BY 1
            ORDER BY "Hits" DESC
            LIMIT 10
            """,
            conn,
        )

        with qcol1:
            st.write("**Top Slow Query Patterns (Last 24h)**")
            if not query_stats_df.empty:
                st.dataframe(query_stats_df, hide_index=True, width="stretch")
            else:
                st.info(
                    "No slow queries recorded in the last 24 hours. Performance looks good!"
                )

        with qcol2:
            st.write("**Recent Slow Incidents**")
            recent_slow = pd.read_sql_query(
                "SELECT timestamp, duration_seconds FROM slow_query_logs ORDER BY timestamp DESC LIMIT 5",
                conn,
            )
            if not recent_slow.empty:
                st.line_chart(recent_slow.set_index("timestamp"))
    except Exception as e:
        st.warning(f"Could not load query statistics: {e}")

    # --- Diagnostics ---
    st.markdown("---")
    st.subheader("🛠 Diagnostics")

    # Fetch latest heartbeats for metrics
    ai_status_row = conn.execute(
        "SELECT value FROM system_settings WHERE key='ai_processing_status'"
    ).fetchone()
    ai_last_update_ts = None
    if ai_status_row and ai_status_row[0]:
        try:
            ai_last_update_ts = json.loads(ai_status_row[0]).get("last_update_ts")
        except Exception:
            pass

    bot_status_row = conn.execute(
        "SELECT value FROM system_settings WHERE key='telegram_bot_status'"
    ).fetchone()
    bot_last_update_ts = None
    if bot_status_row and bot_status_row[0]:
        try:
            bot_last_update_ts = json.loads(bot_status_row[0]).get("last_update_ts")
        except Exception:
            pass

    def _age_text(ts_value):
        if not ts_value:
            return "N/A"
        try:
            age_sec = max(0, int(time.time() - float(ts_value)))
            if age_sec < 60:
                return f"{age_sec}s ago"
            return f"{age_sec // 60}m {age_sec % 60}s ago"
        except:
            return "Error"

    pending_row = conn.execute(
        "SELECT COUNT(*) FROM submissions WHERE processed = 0 AND video_path IS NOT NULL"
    ).fetchone()
    failed_row = conn.execute(
        "SELECT COUNT(*) FROM submissions WHERE processed = -1"
    ).fetchone()

    dcol1, dcol2, dcol3, dcol4 = st.columns(4)
    dcol1.metric("Bot Last Signal", _age_text(bot_last_update_ts))
    dcol2.metric("AI Last Signal", _age_text(ai_last_update_ts))
    dcol3.metric("Pending Tasks", pending_row[0] if pending_row else 0)
    dcol4.metric("Failed Tasks", failed_row[0] if failed_row else 0)
