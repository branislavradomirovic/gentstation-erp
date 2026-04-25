import streamlit as st
import json
import time
import os
import base64
import signal
import sys
import subprocess
import logging
from pathlib import Path
from contextlib import suppress
import pandas as pd
import requests
from datetime import datetime
try:
    import redis
except ImportError:
    redis = None
from core.video_processor import sample_frames, call_ollama
from core.activity_logger import log_activity
from core.database import get_pool_stats, get_system_uptime
from ui.header import render_page_header

logger = logging.getLogger("gentstation.ai_monitoring")

def render(conn):
    render_page_header("🖥️ AI & Service Monitoring")

    # --- System Uptime ---
    uptime_seconds = get_system_uptime()
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    
    uptime_str = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m {int(uptime_seconds % 60)}s"
    st.info(f"⏱️ **System Uptime:** {uptime_str}")

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
            updated_str = datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d %H:%M:%S')
            st.caption(f"Last update: {updated_str}")
        return status_info

    # --- Redis Status ---
    st.divider()
    st.subheader("📦 Infrastructure Services")
    
    r_col1, r_col2 = st.columns(2)
    
    # Redis Check
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    if redis is None:
        r_col1.error("🔴 Redis: Library Missing")
        r_col1.caption("Please run: pip install redis")
    else:
        # Try to fetch last known active time from DB
        last_active_row = conn.execute("SELECT value FROM system_settings WHERE key=%s", ("redis_last_active",)).fetchone()
        last_active_ts = float(last_active_row[0]) if last_active_row and last_active_row[0] else None

        try:
            r = redis.from_url(redis_url, socket_connect_timeout=2)
            r.ping()

            # Update last active in DB on success
            now_ts = time.time()
            conn.execute(
                "INSERT INTO system_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                ("redis_last_active", str(now_ts))
            )
            conn.commit()

            r_col1.success("✅ Redis: Online")
            r_col1.caption(f"Connected to {redis_url}")
            r_col1.caption(f"Last active: {datetime.fromtimestamp(now_ts).strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            r_col1.error(f"🔴 Redis: Offline")
            r_col1.caption(f"Error: {e}")
            if last_active_ts:
                r_col1.caption(f"Last active: {datetime.fromtimestamp(last_active_ts).strftime('%Y-%m-%d %H:%M:%S')}")

    # Redis Health History Chart
    st.subheader("Redis Health History (Last 24h)")
    try:
        history_df = pd.read_sql_query(
            """
            SELECT timestamp, is_online
            FROM redis_health_logs
            WHERE timestamp >= NOW() - INTERVAL '24 HOURS'
            ORDER BY timestamp ASC
            """,
            conn
        )
        if not history_df.empty:
            # Convert boolean to int for charting (1 = Online, 0 = Offline)
            history_df['is_online_int'] = history_df['is_online'].astype(int)
            st.line_chart(history_df.set_index('timestamp')['is_online_int'])
            st.caption("Chart shows 1 for Online, 0 for Offline.")
        else:
            st.info("No Redis health history available yet. Ensure the Telegram bot worker is running.")
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
            conn
        )
        if not latency_df.empty:
            # Display a multiline chart grouped by model
            chart_data = latency_df.pivot(index='timestamp', columns='model_name', values='latency_seconds')
            st.area_chart(chart_data)
            st.caption("Latency in seconds. Higher values indicate slower model response times.")
        else:
            st.info("No inference latency data recorded yet. Processing more videos will populate this chart.")
    except Exception as e:
        st.warning(f"Could not load latency history: {e}")

    # Worker Health Charts
    st.subheader("⚙️ Worker Resource Usage (Last 24h)")
    try:
        health_df = pd.read_sql_query(
            """
            SELECT timestamp, worker_name, cpu_percent, memory_mb
            FROM worker_health_logs
            WHERE timestamp >= NOW() - INTERVAL '24 HOURS'
            ORDER BY timestamp ASC
            """,
            conn
        )
        if not health_df.empty:
            hcol1, hcol2 = st.columns(2)
            
            with hcol1:
                st.write("**CPU Usage (%)**")
                cpu_chart = health_df.pivot(index='timestamp', columns='worker_name', values='cpu_percent')
                st.line_chart(cpu_chart)
                
            with hcol2:
                st.write("**Memory Usage (MB)**")
                mem_chart = health_df.pivot(index='timestamp', columns='worker_name', values='memory_mb')
                st.line_chart(mem_chart)
                
            st.caption("Monitoring real-time overhead of AI inference and Telegram bot activity.")
        else:
            st.info("No worker health data recorded yet.")
    except Exception as e:
        st.warning(f"Could not load worker health history: {e}")

    # AI Success/Failure Rate Chart
    st.subheader("AI Processing Volume (Last 24h)")
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
            conn
        )
        if not volume_df.empty:
            volume_df = volume_df.set_index('hour')
            st.bar_chart(volume_df)
            st.caption("Hourly breakdown of completed (Success) vs. exhausted (Failure) AI jobs.")
        else:
            st.info("No processing volume data found for the last 24 hours.")
    except Exception as e:
        st.warning(f"Could not load processing volume: {e}")

    # DB Pool Stats
    stats = get_pool_stats()
    if stats:
        r_col2.success("✅ Database Health")
        usage_pct = (stats['used'] / stats['maxconn']) * 100
        r_col2.metric("Connections In Use", f"{stats['used']} / {stats['maxconn']}", f"{usage_pct:.1f}% load")
        r_col2.progress(stats['used'] / stats['maxconn'])
    else:
        r_col2.error("🔴 Database Pool: Error")

    # --- Query Statistics ---
    st.divider()
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
            conn
        )
        
        with qcol1:
            st.write("**Top Slow Query Patterns (Last 24h)**")
            if not query_stats_df.empty:
                st.dataframe(query_stats_df, hide_index=True, width="stretch")
            else:
                st.info("No slow queries recorded in the last 24 hours. Performance looks good!")

        with qcol2:
            st.write("**Recent Slow Incidents**")
            recent_slow = pd.read_sql_query(
                "SELECT timestamp, duration_seconds FROM slow_query_logs ORDER BY timestamp DESC LIMIT 5",
                conn
            )
            if not recent_slow.empty:
                st.line_chart(recent_slow.set_index('timestamp'))
    except Exception as e:
        st.warning(f"Could not load query statistics: {e}")

    # --- Telegram Bot Status ---
    st.divider()
    st.subheader("🤖 Telegram Bot")
    bot_row = conn.execute("SELECT value FROM system_settings WHERE key='telegram_bot_status'").fetchone()
    bot_status_info = render_worker_status("Telegram Bot Worker", bot_row, stale_after_seconds=90)

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
        st.caption("Why offline: `TELEGRAM_BOT_TOKEN` is missing in `.env`.")
    elif bot_status == "error":
        st.caption(f"Worker reported error: {bot_details or 'N/A'}")
    elif bot_stale:
        st.caption("Heartbeat is stale. Worker process may be stuck.")

    # --- AI Worker Status ---
    st.divider()
    st.subheader("🧠 AI Worker")
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

    if ai_stale and ai_last_update_ts:
        st.error(f"🔴 AI Worker: Stale Heartbeat")
        st.caption(f"The worker was last active {int(time.time() - float(ai_last_update_ts))}s ago.")
    elif ai_status == "processing":
        total = ai_status_info.get("total", 0)
        current = ai_status_info.get("current", 0)
        progress_val = (current / total) if total > 0 else 0
        st.info("AI processing is currently in progress...")
        st.progress(progress_val, text=f"Processing task {current} of {total}")
        st.html("<meta http-equiv='refresh' content='10'>")

    # Show Reset button if either processing or stale
    if ai_status == "processing" or (ai_stale and ai_last_update_ts):
        if st.button("🔄 Reset AI Status to Idle", key="reset_ai_manual", width="stretch"):
            conn.execute("UPDATE system_settings SET value = %s WHERE key = 'ai_processing_status'", (json.dumps({"status": "idle", "last_update_ts": time.time()}),))
            conn.commit()
            log_activity(conn, "AI_STATUS_RESET", "User manually cleared stuck AI status")
            st.success("Status reset. If the worker was genuinely stuck, it will now resume.")
            time.sleep(1)
            st.rerun()
    else:
        last_run_ts = ai_status_info.get("last_run_ts")
        if last_run_ts:
            last_run_str = datetime.fromtimestamp(last_run_ts).strftime('%Y-%m-%d %H:%M:%S')
            st.success(f"✅ AI Worker is idle. Last batch finished at {last_run_str}.")
        else:
            st.success("✅ AI Worker is idle.")

    if st.button("🚀 Force AI Processing Batch", type="primary", width="stretch"):
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
        st.success("Batch processing signal sent!")
        time.sleep(1)
        st.rerun()

    # --- Ollama Status ---
    st.divider()
    st.subheader("🦙 Ollama Connectivity")

    # Active Model Display
    row_m = conn.execute("SELECT value FROM system_settings WHERE key='ollama_model_override'").fetchone()
    row_v = conn.execute("SELECT value FROM system_settings WHERE key='ollama_vision_model_override'").fetchone()
    
    active_llm = row_m[0] if row_m else os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct")
    active_vision = row_v[0] if row_v else os.getenv("OLLAMA_VISION_MODEL", "bakllava")

    mcol1, mcol2 = st.columns(2)
    mcol1.info(f"**Active LLM:** {active_llm}")
    
    if active_vision:
        mcol2.success(f"**Vision System:** Enabled ({active_vision})")
    else:
        mcol2.warning("**Vision System:** Disabled (Using Metadata Only)")
    st.write("")

    # Auto-Scale status indicator
    row_as_active = conn.execute("SELECT value FROM system_settings WHERE key='ai_auto_scale_active'").fetchone()
    if row_as_active and row_as_active[0] == '1':
        st.warning(f"📉 **Auto-Scale Active:** System has switched to a smaller model due to high memory pressure.")
        if st.button("♻️ Restore Primary Model", width="stretch"):
            conn.execute("UPDATE system_settings SET value = '0' WHERE key = 'ai_auto_scale_active'")
            conn.commit()
            log_activity(conn, "AUTO_SCALE_RESET", "User manually restored primary AI model")
            st.success("Primary model restored. Next job will use default configuration.")
            time.sleep(1)
            st.rerun()

    if st.button("🩺 Run Full System Health Check", width="stretch", type="primary"):
        with st.status("Executing AI Pipeline Diagnostics...") as status_box:
            # 1. Connectivity Check
            st.write("Probing Ollama API connectivity...")
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            try:
                resp = requests.get(f"{base_url}/api/tags", timeout=5)
                if resp.status_code == 200:
                    st.write("✅ API Connectivity: **OK**")
                else:
                    st.write(f"❌ API Connectivity: **Failed** (HTTP {resp.status_code})")
            except Exception as e:
                st.write(f"❌ API Connectivity: **Error** ({e})")

            # 2. LLM Inference Check
            st.write(f"Testing Primary LLM ({active_llm})...")
            try:
                llm_start = time.time()
                llm_response = call_ollama("Verify system health. Respond with exactly 'READY'.", active_llm, is_json=False)
                llm_time = time.time() - llm_start
                if "READY" in llm_response.upper():
                    st.write(f"✅ LLM Inference: **Functional** (Latency: {llm_time:.1f}s)")
                else:
                    st.write(f"⚠️ LLM Inference: **Partial** (Unexpected response: '{llm_response}')")
            except Exception as e:
                st.write(f"❌ LLM Inference: **Failed** ({e})")

            # 3. Vision Inference Check
            if active_vision:
                st.write(f"Testing Vision Model ({active_vision})...")
                try:
                    res = conn.execute("SELECT video_path FROM submissions WHERE video_path IS NOT NULL ORDER BY timestamp DESC LIMIT 1").fetchone()
                    if res and os.path.exists(res[0]):
                        frames = sample_frames(res[0], 1)
                        if frames:
                            v_resp = call_ollama("What is this? (1-3 words)", active_vision, [frames[0].image_b64], is_json=False)
                            st.write(f"✅ Vision Inference: **Functional** (Response: '{v_resp}')")
                        else:
                            st.write("❌ Vision Inference: **Failed** (Frame extraction failed)")
                    else:
                        st.write("ℹ️ Vision Inference: **Skipped** (No sample video found in database)")
                except Exception as e:
                    st.write(f"❌ Vision Inference: **Failed** ({e})")
            
            status_box.update(label="System Health Check Complete", state="complete", expanded=True)

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
        if not local_only:
            add("http://host.docker.internal:11434")
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
                    model_rows.append({
                        "Model": m.get("name") or m.get("model") or "unknown",
                        "Size": m.get("size", "-"),
                        "Modified": m.get("modified_at", "-"),
                    })
                st.dataframe(model_rows, width="stretch", hide_index=True)
            else:
                st.info("Connected to Ollama, but no models are currently available.")
        else:
            st.error("❌ Could not connect to Ollama.")
            st.code("\n".join(checked), language="text")

    if st.button("🖼️ Test Vision Inference", width="stretch", help="Extract one frame from a recent video and ask the model to describe it.", disabled=not active_vision):
        # 1. Find a sample video from recent submissions
        res = conn.execute("SELECT video_path FROM submissions WHERE video_path IS NOT NULL ORDER BY timestamp DESC LIMIT 1").fetchone()
        
        if not res or not os.path.exists(res[0]):
            st.error("No valid video files found in the database to use for testing.")
        else:
            video_path = res[0]
            with st.spinner(f"Extracting frame and calling {active_vision}..."):
                try:
                    # Extract exactly 1 frame
                    frames = sample_frames(video_path, 1)
                    if frames:
                        # Display the frame to verify OpenCV is working
                        st.image(base64.b64decode(frames[0].image_b64), caption=f"Test frame extracted from: {os.path.basename(video_path)}")
                        
                        # Call Ollama with the specific vision model
                        test_prompt = "Describe what you see in this gas station CCTV frame in one short sentence."
                        desc = call_ollama(test_prompt, active_vision, [frames[0].image_b64], is_json=False)
                        
                        st.success(f"**Model Response:** {desc}")
                    else:
                        st.error("OpenCV was unable to extract any frames from the selected video.")
                except Exception as e:
                    st.error(f"Vision test failed: {e}")

    # --- Process Management ---
    st.divider()
    st.subheader("🛠️ Process Management")
    st.write("Manually stop or restart background services. This will clear lock files and attempt to spawn new process instances.")

    def _kill_worker(lock_path):
        if lock_path.exists():
            try:
                pid_text = lock_path.read_text().strip()
                if pid_text:
                    pid = int(pid_text)
                    # Try SIGTERM first
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(1)
                    # Check if still alive, then SIGKILL
                    try:
                        os.kill(pid, 0)
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
            except Exception as e:
                logger.debug(f"Process kill error for {lock_path}: {e}")
            finally:
                with suppress(Exception):
                    lock_path.unlink(missing_ok=True)

    pm_col1, pm_col2 = st.columns(2)

    if pm_col1.button("🛑 Stop All Workers", width="stretch", help="Kills current worker processes and deletes lock files."):
        with st.spinner("Terminating worker processes..."):
            _kill_worker(Path("/tmp/gentstationai_bot_worker.lock"))
            _kill_worker(Path("/tmp/gentstationai_ai_worker.lock"))
            log_activity(conn, "WORKER_STOP", "User stopped all background workers via UI")
            st.success("All workers stopped and locks cleared.")
            time.sleep(1)
            st.rerun()

    if pm_col2.button("🔄 Restart All Workers", type="primary", width="stretch", help="Kills current processes and immediately spawns new ones."):
        with st.spinner("Restarting worker processes..."):
            # 1. Kill and Clean
            _kill_worker(Path("/tmp/gentstationai_bot_worker.lock"))
            _kill_worker(Path("/tmp/gentstationai_ai_worker.lock"))
            
            # 2. Re-spawn (Logic similar to app.py)
            project_root = Path(__file__).resolve().parents[1]
            worker_configs = [
                (project_root / "bot" / "bot_worker.py", Path("/tmp/gentstation_bot.log")),
                (project_root / "core" / "ai_worker.py", Path("/tmp/gentstation_ai.log"))
            ]
            
            for script_path, log_path in worker_configs:
                if script_path.exists():
                    try:
                        log_path.parent.mkdir(parents=True, exist_ok=True)
                        log_file = open(log_path, "a", buffering=1)
                        subprocess.Popen(
                            [sys.executable, "-u", str(script_path)],
                            cwd=str(project_root),
                            stdout=log_file,
                            stderr=log_file,
                            start_new_session=True,
                        )
                    except Exception as e:
                        st.error(f"Failed to start {script_path.name}: {e}")

            log_activity(conn, "WORKER_RESTART", "User restarted all background workers via UI")
            st.success("Restart commands issued successfully.")
            time.sleep(2)
            st.rerun()

    # --- Diagnostics ---
    st.divider()
    st.subheader("🛠 Diagnostics")
    
    def _age_text(ts_value):
        if not ts_value: return "N/A"
        try:
            age_sec = max(0, int(time.time() - float(ts_value)))
            if age_sec < 60: return f"{age_sec}s ago"
            return f"{age_sec // 60}m {age_sec % 60}s ago"
        except: return "Error"

    pending_row = conn.execute("SELECT COUNT(*) FROM submissions WHERE processed = 0 AND video_path IS NOT NULL").fetchone()
    failed_row = conn.execute("SELECT COUNT(*) FROM submissions WHERE processed = -1").fetchone()
    
    dcol1, dcol2, dcol3, dcol4 = st.columns(4)
    dcol1.metric("Bot Heartbeat", _age_text(bot_last_update_ts))
    dcol2.metric("AI Heartbeat", _age_text(ai_last_update_ts))
    dcol3.metric("Pending Tasks", pending_row[0] if pending_row else 0)
    dcol4.metric("Failed Tasks", failed_row[0] if failed_row else 0)

    st.caption("Quick restart hints (local development):")
    st.code("pkill -f bot/bot_worker.py && pkill -f core/ai_worker.py", language="bash")
