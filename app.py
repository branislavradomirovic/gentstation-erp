import os
import json
import logging
import warnings
import time
import streamlit as st
from pathlib import Path

import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()

warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy connectable",
)
try:
    from urllib3.exceptions import NotOpenSSLWarning

    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("gentstation.app")


def _env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


# --- 1. PAGE CONFIGURATION (MUST BE FIRST) ---
st.set_page_config(
    page_title="Gas Station Manager", layout="wide", initial_sidebar_state="expanded"
)


def start_background_workers():
    """
    Ensure background processes (Telegram Bot, AI Worker) are running.
    Uses lock-file PID checks to avoid duplicate launches across reruns.
    """
    project_root = Path(__file__).resolve().parent

    # Worker Registry for robust management
    WORKERS = [
        {
            "name": "Telegram Bot",
            "script": project_root / "core" / "bot_worker.py",
            "lock": Path("/tmp/gentstationai_bot_worker.lock"),
            "log": Path("/tmp/gentstation_bot.log"),
            "enabled_env": "AUTO_START_TELEGRAM_BOT",
            "requires_env": ["TELEGRAM_BOT_TOKEN"],
        },
        {
            "name": "AI Worker",
            "script": project_root / "core" / "ai_worker.py",
            "lock": Path("/tmp/gentstationai_ai_worker.lock"),
            "log": Path("/tmp/gentstation_ai.log"),
            "enabled_env": "AUTO_START_AI_WORKER",
            "requires_env": [],
        },
        {
            "name": "Report Scheduler",
            "script": project_root / "core" / "report_scheduler.py",
            "lock": Path("/tmp/gentstationai_report_scheduler.lock"),
            "log": Path("/tmp/gentstation_report_scheduler.log"),
            "enabled_env": "AUTO_START_REPORT_SCHEDULER",
            "requires_env": [],
        },
    ]

    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except Exception:
            return False
        # Treat zombie state as not running.
        try:
            stat = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "stat="], text=True
            ).strip()
            if not stat or stat.upper().startswith("Z"):
                return False
        except Exception:
            pass
        return True

    def _is_running_from_lock(lock_file: Path) -> bool:
        try:
            if not lock_file.exists():
                return False
            pid_txt = lock_file.read_text().strip()
            if not pid_txt:
                return False
            return _pid_alive(int(pid_txt))
        except Exception:
            return False

    def _spawn_worker(script_path: Path, log_path: Path):
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = open(log_path, "a", buffering=1)

            # Ensure sub-process has the project root in PYTHONPATH
            env = os.environ.copy()
            env["PYTHONPATH"] = (
                str(project_root) + os.pathsep + env.get("PYTHONPATH", "")
            )

            subprocess.Popen(
                [sys.executable, "-u", str(script_path)],
                cwd=str(project_root),
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
                env=env,
            )
            return True
        except Exception as e:
            logger.warning("Could not start worker %s: %s", script_path, e)
            return False

    def _set_worker_starting_status(status_key: str, details: str):
        try:
            from core.database import get_connection

            conn = get_connection()
            conn.execute(
                """
                INSERT INTO system_settings (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (
                    status_key,
                    json.dumps(
                        {
                            "status": "starting",
                            "details": details,
                            "last_update_ts": time.time(),
                        }
                    ),
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("Could not publish starting status for %s: %s", status_key, e)

    def _read_status_payload(status_key: str):
        try:
            from core.database import get_connection

            conn = get_connection()
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key = %s",
                (status_key,),
            ).fetchone()
            conn.close()
            if not row or not row[0]:
                return None
            return json.loads(row[0])
        except Exception as e:
            logger.debug("Could not read status payload for %s: %s", status_key, e)
            return None

    def _is_stale_status(status_key: str, stale_after_seconds: int = 180) -> bool:
        payload = _read_status_payload(status_key)
        if not payload:
            return True
        ts = payload.get("last_update_ts")
        if not ts:
            return True
        try:
            return (time.time() - float(ts)) > stale_after_seconds
        except Exception:
            return True

    default_worker_start = os.getenv("AUTO_START_BACKGROUND_WORKERS_DEFAULT", "0")
    global_worker_start = _env_bool(
        "AUTO_START_BACKGROUND_WORKERS", default_worker_start
    )
    worker_enabled_flags = {
        cfg["name"]: _env_bool(cfg["enabled_env"], default_worker_start) for cfg in WORKERS
    }

    if not global_worker_start and not any(worker_enabled_flags.values()):
        logger.info("No background workers are enabled for auto-start.")
        return

    for cfg in WORKERS:
        # 1. Check if enabled via env
        worker_enabled = worker_enabled_flags[cfg["name"]]
        if not worker_enabled and not global_worker_start:
            logger.info("%s startup is disabled via env.", cfg["name"])
            continue
        if not worker_enabled and global_worker_start:
            logger.info("%s startup is disabled via env.", cfg["name"])
            continue

        # 2. Check for required environment variables (e.g., Tokens)
        missing_reqs = [r for r in cfg["requires_env"] if not os.getenv(r)]
        if missing_reqs:
            logger.warning(
                "Skipping %s: Missing %s", cfg["name"], ", ".join(missing_reqs)
            )
            continue

        # 3. Health Check: Is it already running?
        if _is_running_from_lock(cfg["lock"]):
            if cfg["name"] == "Report Scheduler" and _is_stale_status(
                "report_scheduler_status"
            ):
                logger.warning(
                    "Report Scheduler lock exists but heartbeat is stale or missing. Recycling worker."
                )
                try:
                    cfg["lock"].unlink(missing_ok=True)
                except Exception as e:
                    logger.warning("Could not clear stale Report Scheduler lock: %s", e)
                    continue
            else:
                logger.debug("%s is already running.", cfg["name"])
                continue

        # 4. Spawn if script exists
        if cfg["script"].exists():
            if _spawn_worker(cfg["script"], cfg["log"]):
                if cfg["name"] == "Report Scheduler":
                    _set_worker_starting_status(
                        "report_scheduler_status",
                        "Report scheduler is starting from app boot sequence.",
                    )
                logger.info("Successfully launched %s.", cfg["name"])


# --- 2. GLOBAL CSS INJECTION (Optimized for Spacing & Alignment) ---
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.1rem !important;
            padding-bottom: 1.25rem !important;
            max-width: 1440px;
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top right, rgba(11, 94, 215, 0.06), transparent 28%),
                linear-gradient(180deg, #f7f9fc 0%, #f4f7fb 45%, #eef3f8 100%);
        }

        /* Hide the default Streamlit auto-navigation */
        [data-testid="stSidebarNav"] { display: none !important; }

        /* Hide the sidebar header container (source of top gap) */
        [data-testid="stSidebarHeader"] {
            display: none !important;
            padding: 0 !important;
        }

        /* Remove top padding from the main sidebar area */
        [data-testid="stSidebarContent"] {
            padding-top: 0rem !important;
        }

        /* Pull the logo to the absolute top edge */
        [data-testid="stSidebarContent"] > div:first-child {
            margin-top: 1.5rem !important;
        }

        /* INCREASED VERTICAL SPACING between sidebar components */
        [data-testid="stVerticalBlock"] {
            gap: 0.9rem !important;
        }

        /* Ensure the logo image stays flush */
        [data-testid="stSidebar"] [data-testid="stImage"] {
            margin-top: 0px !important;
            padding-top: 0px !important;
        }
        /* Force sidebar logo to a clear, centered size */
        [data-testid="stSidebar"] img {
            width: 160px !important;
            height: auto !important;
            display: block !important;
            margin: 6px auto !important;
        }

        [data-testid="stSidebar"] .block-container,
        [data-testid="stSidebarContent"] > div {
            gap: 0.65rem !important;
        }

        /* UI polish: compact, consistent controls */
        .stButton button {
            border-radius: 10px;
            min-height: 2.5rem;
            margin-top: 0.1rem;
            font-weight: 600;
            border: 1px solid rgba(15, 23, 42, 0.08);
        }

        .stButton button[kind="primary"] {
            box-shadow: 0 10px 18px rgba(11, 94, 215, 0.14);
        }

        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(246,248,251,0.96));
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 14px;
            padding: 0.8rem 0.95rem;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
        }

        div[data-testid="stMetricLabel"] {
            font-size: 0.8rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 14px;
            overflow: hidden;
        }

        div[data-testid="stExpander"] {
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 14px;
            background: rgba(255,255,255,0.78);
        }

        div[data-testid="stAlert"] {
            border-radius: 14px;
        }

        div[data-baseweb="tab-list"] {
            gap: 0.35rem;
        }

        button[data-baseweb="tab"] {
            border-radius: 999px !important;
            padding: 0.35rem 0.85rem !important;
            background: rgba(15, 23, 42, 0.04) !important;
        }

        button[data-baseweb="tab"][aria-selected="true"] {
            background: rgba(11, 94, 215, 0.12) !important;
        }

        .gs-surface {
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 16px;
            background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(247,249,252,0.95));
            box-shadow: 0 14px 30px rgba(15, 23, 42, 0.05);
            padding: 1rem 1.05rem;
        }

        .gs-page-intro {
            margin-top: -0.2rem;
            margin-bottom: 0.75rem;
            color: #5b6474;
            font-size: 0.95rem;
            line-height: 1.5;
        }

        .gs-section-kicker {
            font-size: 0.76rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #0b5ed7;
            font-weight: 800;
            margin-bottom: 0.35rem;
        }

        footer { visibility: hidden; }

        .login-disclaimer {
            margin-top: 1rem;
            padding: 0.75rem;
            text-align: center;
            font-size: 0.75rem;
            color: #4a4a4a;
            background-color: rgba(240, 242, 246, 0.75);
            border-radius: 10px;
            backdrop-filter: blur(5px);
        }

        .login-shell {
            display: grid;
            grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
            gap: 2rem;
            align-items: stretch;
            margin: 0.35rem auto 0 auto;
        }

        .login-panel {
            border: 1px solid rgba(15, 23, 42, 0.10);
            border-radius: 18px;
            background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(245,247,250,0.96));
            box-shadow: 0 20px 60px rgba(15, 23, 42, 0.10);
            padding: 1.5rem 1.6rem;
            min-height: 100%;
        }

        [data-testid="stHeader"] {
            height: 0rem !important;
            background: transparent !important;
        }

        [data-testid="stToolbar"] {
            top: 0.35rem !important;
        }

        .login-brand-panel [data-testid="stImage"] img {
            max-height: 56px;
            width: auto !important;
            object-fit: contain;
        }

        .login-brand-panel [data-testid="stImageContainer"] {
            max-width: 250px !important;
            width: 250px !important;
            margin: 0 auto;
        }

        .login-brand-panel {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 1.5rem;
        }

        .login-brand-copy {
            display: grid;
            gap: 0.9rem;
        }

        .login-readiness {
            margin-top: 0.2rem;
            padding: 1rem 1.05rem;
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 16px;
            background: linear-gradient(180deg, rgba(248,250,252,0.98), rgba(241,245,249,0.94));
        }

        .login-readiness-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 0.75rem;
            margin-bottom: 0.8rem;
        }

        .login-readiness-title {
            font-size: 0.96rem;
            font-weight: 800;
            color: #0f172a;
        }

        .login-readiness-subtitle {
            font-size: 0.76rem;
            color: #64748b;
        }

        .login-readiness-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.65rem;
        }

        .login-readiness-card {
            padding: 0.8rem 0.85rem;
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: rgba(255,255,255,0.92);
        }

        .login-readiness-card.is-ready {
            background: rgba(240, 253, 244, 0.92);
            border-color: rgba(34, 197, 94, 0.25);
        }

        .login-readiness-card.is-warning,
        .login-readiness-card.is-starting {
            background: rgba(255, 251, 235, 0.94);
            border-color: rgba(245, 158, 11, 0.25);
        }

        .login-readiness-card.is-offline {
            background: rgba(254, 242, 242, 0.94);
            border-color: rgba(239, 68, 68, 0.2);
        }

        .login-readiness-topline {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            margin-bottom: 0.3rem;
        }

        .login-readiness-label {
            font-size: 0.8rem;
            font-weight: 700;
            color: #0f172a;
        }

        .login-readiness-state {
            font-size: 0.66rem;
            font-weight: 800;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: #334155;
        }

        .login-readiness-detail {
            font-size: 0.76rem;
            line-height: 1.45;
            color: #5b6474;
        }

        .login-kicker {
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #0b5ed7;
        }

        .login-title {
            margin: 0;
            font-size: 2rem;
            line-height: 1.08;
            color: #111827;
        }

        .login-subtitle {
            margin: 0;
            font-size: 1rem;
            line-height: 1.65;
            color: #4b5563;
            max-width: 38rem;
        }

        .login-brand-panel .login-disclaimer {
            margin-top: 0;
            padding: 1rem 1.1rem;
            text-align: left;
            font-size: 0.96rem;
            line-height: 1.6;
            color: #374151;
            background: rgba(255,255,255,0.72);
            border: 1px solid rgba(148, 163, 184, 0.28);
            border-radius: 14px;
        }

        .login-brand-actions {
            display: grid;
            gap: 0.9rem;
            align-content: start;
        }

        .login-form-panel {
            display: flex;
            flex-direction: column;
            justify-content: center;
        }

        .login-form-header {
            margin-bottom: 0.6rem;
        }

        .login-form-title {
            margin: 0;
            font-size: 1.5rem;
            line-height: 1.2;
            color: #111827;
        }

        .login-form-subtitle {
            margin: 0.55rem 0 0 0;
            font-size: 0.95rem;
            line-height: 1.55;
            color: #6b7280;
        }

        .login-status {
            margin: 0.65rem 0 1rem 0;
            padding: 0.8rem 0.95rem;
            border-radius: 12px;
            font-size: 0.9rem;
            background: rgba(11, 94, 215, 0.08);
            border: 1px solid rgba(11, 94, 215, 0.14);
            color: #0f172a;
        }

        @media (max-width: 900px) {
            .login-shell {
                grid-template-columns: 1fr;
                gap: 1.2rem;
                margin-top: 0.2rem;
            }

            .login-panel {
                padding: 1.4rem;
            }

            .login-title {
                font-size: 1.65rem;
            }

            .login-readiness-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
""",
    unsafe_allow_html=True,
)

# --- DARK MODE INJECTION ---
if st.session_state.get("dark_mode"):
    st.markdown(
        """
        <style>
            [data-testid="stAppViewContainer"] {
                background-color: #0E1117;
                color: #FAFAFA;
            }
            [data-testid="stSidebar"] {
                background-color: #262730;
            }
            [data-testid="stHeader"] {
                background-color: rgba(0,0,0,0);
            }
            .login-disclaimer {
                background-color: rgba(38, 39, 48, 0.9) !important;
                color: #FAFAFA !important;
            }
        </style>
    """,
        unsafe_allow_html=True,
    )

# Core imports
from core.database import Base
from sqlalchemy.orm import configure_mappers
try:
    # Import models package to register classes in the SQLAlchemy registry
    import core.models

    # 1. Check mapped class names (Crucial for resolving relationship strings like "Submission")
    registered_classes = [name for name in Base.registry._class_registry.keys() if not name.startswith("_")]
    logger.info("SQLAlchemy Class Registry: %s", ", ".join(registered_classes))

    # 2. Check physical table names
    table_names = list(Base.metadata.tables.keys())
    logger.info("SQLAlchemy Metadata Tables: %s", ", ".join(table_names))

    # Force SQLAlchemy to initialize relationships immediately to catch errors early
    configure_mappers()
except Exception as e:
    logger.error("Database mapper initialization failed: %s", e)
    st.error(f"❌ Database Configuration Error: {e}")
    st.info("Check if all models (including Submission) are imported in core/models/__init__.py")
    st.stop()


from core.database import get_connection, get_schema_readiness
from core.auth import (
    login_user_streamlit,
    logout_user_streamlit,
)
from core.session import validate_session_token
from core.activity_logger import log_activity
from core.config import LOGIN_DISCLAIMER_HTML, FOOTER_DISCLAIMER_TEXT

# Page imports
import pages.dashboard as dashboard
import pages.regions as regions
import pages.stations as stations
import pages.map_view as map_view
import pages.employees as employees
import pages.admin_users as admin_users
import pages.ai_reports as ai_reports
import pages.ai_alerts as ai_alerts
import pages.ai_monitoring as ai_monitoring
import pages.audit_log as audit_log
import pages.admin_data_import as admin_data_import
import pages.settings as settings
import pages.help as page_help

# UI imports
from ui.sidebar import display_sidebar
from core.access_control import PAGE_CONFIG, has_access

# Communication service for password reset
try:
    from core.comm_service import send_password_reset_email
except ImportError:

    def send_password_reset_email(*args, **kwargs):
        st.error("Email service unavailable.")


def run_boot_sequence():
    """
    Shows a system boot sequence UI and ensures all external
    dependencies (DB, Ollama) and internal workers are ready.
    """
    from core.database import DB_HOST, DB_PORT, test_redis_connection
    from core.video_processor import test_ollama_connection, OLLAMA_BASE_URL
    from core.comm_service import test_smtp_connection

    boot_summary = []

    st.subheader("🚀 System Boot Sequence")

    db_status = st.empty()
    redis_status = st.empty()
    tg_config_status = st.empty()
    email_status = st.empty()
    ai_status = st.empty()
    worker_status = st.empty()
    bot_worker_status_display = st.empty()
    report_scheduler_status_display = st.empty()

    # 1. Database Connectivity
    db_status.info(f"⏳ Connecting to PostgreSQL at `{DB_HOST}`...")

    def db_retry_callback(attempt, total, remaining, error):
        production_hint = (
            "💡 *Render deployment: verify the managed Postgres connection string is attached to `DATABASE_URL`.*"
            if os.getenv("APP_ENV", "").strip().lower() in {"production", "prod"}
            or os.getenv("RENDER_SERVICE_ID")
            else "💡 *Reminder: Ensure PostgreSQL is running (e.g., `docker compose up -d postgres`) before starting the app.*"
        )
        db_status.warning(
            f"⚠️ **Database connection attempt {attempt}/{total} failed.**\n\n"
            f"Retrying in **{remaining}s**...\n\n"
            f"**Current Error:** `{error}`\n\n"
            f"{production_hint}"
        )

    try:
        _conn = get_connection(on_retry=db_retry_callback)
        db_status.success(f"✅ Database: **Connected** (`{DB_HOST}:{DB_PORT}`)")
        boot_summary.append(
            {"label": "Database", "state": "ready", "detail": f"{DB_HOST}:{DB_PORT}"}
        )
    except Exception as e:
        db_status.error(f"❌ Database: **Offline**")
        boot_summary.append(
            {"label": "Database", "state": "offline", "detail": str(e)}
        )
        st.error(f"Error details: `{e}`")
        st.divider()
        st.warning("### 💡 Startup Reminder")
        st.markdown(
            f"""
        PostgreSQL must be running **before** the application starts.

        - **Using Docker?** Run `docker compose up -d postgres`
        - **Running Locally?** Start your local Postgres server.
        - **Environment Check:** Verify `DB_HOST` in `.env` (Current: `{DB_HOST}`).
        """
        )
        if st.button("🔄 Retry Connection", use_container_width=True):
            st.rerun()
        st.stop()

    # 2. Redis Connectivity
    redis_url = os.getenv("REDIS_URL", "").strip()
    auto_start_bool = _env_bool("AUTO_START_BACKGROUND_WORKERS", "1")
    external_scheduler_enabled = _env_bool(
        "EXTERNAL_REPORT_SCHEDULER_ENABLED", "0"
    )
    external_telegram_worker_enabled = _env_bool(
        "EXTERNAL_TELEGRAM_WORKER_ENABLED", "0"
    )

    if not auto_start_bool or not redis_url:
        redis_status.info("ℹ️ Redis checks disabled (background workers disabled or REDIS_URL unset).")
        boot_summary.append(
            {"label": "Redis", "state": "warning", "detail": "Checks disabled"}
        )
    else:
        redis_status.info(f"⏳ Connecting to Redis...")

        def redis_retry_callback(attempt, total, remaining, error):
            redis_status.warning(
                f"⚠️ **Redis connection attempt {attempt}/{total} failed.**\n\n"
                f"Retrying in **{remaining}s**...\n\n"
                f"**Current Error:** `{error}`\n\n"
                "💡 *Reminder: Ensure Redis is running (e.g., `docker compose up -d redis`) before starting the app.*"
            )

        if test_redis_connection(on_retry=redis_retry_callback):
            redis_status.success(f"✅ Redis: **Online** (`{redis_url}`)")
            boot_summary.append(
                {"label": "Redis", "state": "ready", "detail": redis_url}
            )
        else:
            redis_status.warning(f"⚠️ Redis: **Offline**. Background tasks may be delayed.")
            st.caption(f"Check your `REDIS_URL` in `.env`.")
            boot_summary.append(
                {"label": "Redis", "state": "warning", "detail": "Unavailable"}
            )

    # 3. Telegram Bot Configuration
    tg_config_status.info("⏳ Checking Telegram Bot configuration...")
    tg_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    tg_url = (os.getenv("TELEGRAM_BOT_URL") or "").strip()

    if not tg_token:
        tg_config_status.error("❌ Telegram Bot: **Token Missing**")
        boot_summary.append(
            {"label": "Telegram Bot", "state": "offline", "detail": "Token missing"}
        )
        st.warning(
            "`TELEGRAM_BOT_TOKEN` is not configured in `.env`. Automated reports via Telegram will not function."
        )
    elif not tg_url:
        tg_config_status.warning("⚠️ Telegram Bot: **URL Missing**")
        boot_summary.append(
            {"label": "Telegram Bot", "state": "warning", "detail": "URL missing"}
        )
        st.caption(
            "`TELEGRAM_BOT_URL` is not set. Deep links for registration may be unavailable."
        )
    else:
        tg_config_status.success("✅ Telegram Bot: **Configured**")
        boot_summary.append(
            {"label": "Telegram Bot", "state": "ready", "detail": "Configured"}
        )

    # 4. AI Service Connectivity
    ai_status.info(f"⏳ Verifying Ollama AI at `{OLLAMA_BASE_URL}`...")

    def ai_retry_callback(attempt, total, remaining, error):
        ai_status.warning(
            f"⚠️ **AI Service connection attempt {attempt}/{total} failed.**\n\n"
            f"Retrying in **{remaining}s**...\n\n"
            f"**Current Error:** `{error}`\n\n"
            f"💡 *Reminder: Ensure Ollama is running (`ollama serve`) at `{OLLAMA_BASE_URL}`.*"
        )

    if test_ollama_connection(on_retry=ai_retry_callback):
        ai_status.success(f"✅ AI Service: **Ready** (`{OLLAMA_BASE_URL}`)")
        boot_summary.append(
            {"label": "AI Service", "state": "ready", "detail": OLLAMA_BASE_URL}
        )
    else:
        ai_status.warning(
            f"⚠️ AI Service: **Unreachable**. Automated analysis will be disabled."
        )
        st.caption(
            f"Reminder: Ensure `ollama serve` is running at `{OLLAMA_BASE_URL}`."
        )
        boot_summary.append(
            {"label": "AI Service", "state": "warning", "detail": "Unavailable"}
        )

    # 5. Email Service Connectivity
    email_status.info("⏳ Connecting to SMTP Server...")

    def email_retry_callback(attempt, total, remaining, error):
        email_status.warning(
            f"⚠️ **SMTP connection attempt {attempt}/{total} failed.**\n\n"
            f"Retrying in **{remaining}s**...\n\n"
            f"**Current Error:** `{error}`\n\n"
            "💡 *Check your SMTP credentials in `.env`. If using Gmail, ensure you use an App Password.*"
        )

    if test_smtp_connection(on_retry=email_retry_callback):
        email_status.success("✅ Email Service: **Online**")
        boot_summary.append(
            {"label": "Email", "state": "ready", "detail": "SMTP online"}
        )
    else:
        email_status.warning(
            "⚠️ Email Service: **Offline**. Password resets and notifications will be disabled."
        )
        boot_summary.append(
            {"label": "Email", "state": "warning", "detail": "SMTP offline"}
        )

    # 6. Spawn Internal Workers
    report_scheduler_enabled = (
        _env_bool("AUTO_START_REPORT_SCHEDULER", "0") or external_scheduler_enabled
    )
    if report_scheduler_enabled:
        _conn.execute(
            """
            INSERT INTO system_settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (
                "report_scheduler_status",
                json.dumps(
                    {
                        "status": "starting",
                        "details": "Report Scheduler is launching during boot sequence.",
                        "last_update_ts": time.time(),
                    }
                ),
            ),
        )
        _conn.commit()

    worker_status.info("⏳ Launching Telegram Bot, AI Worker, and Report Scheduler processes...")
    start_background_workers()
    worker_status.success("✅ System Workers: **Operational**")

    # 7. Check Telegram Bot Worker Status
    bot_status_row = _conn.execute(
        "SELECT value FROM system_settings WHERE key='telegram_bot_status'"
    ).fetchone()
    if bot_status_row and bot_status_row[0]:
        try:
            status_info = json.loads(bot_status_row[0])
            if status_info.get("status") == "online":
                bot_worker_status_display.success("✅ Telegram Bot Worker: **Online**")
                boot_summary.append(
                    {"label": "Bot Worker", "state": "ready", "detail": "Online"}
                )
            else:
                bot_worker_status_display.warning(
                    f"⚠️ Telegram Bot Worker: **{status_info.get('status', 'Offline')}**"
                )
                boot_summary.append(
                    {
                        "label": "Bot Worker",
                        "state": "warning",
                        "detail": str(status_info.get("status", "offline")).title(),
                    }
                )
        except json.JSONDecodeError:
            bot_worker_status_display.warning(
                "⚠️ Telegram Bot Worker: **Status Unknown**"
            )
            boot_summary.append(
                {"label": "Bot Worker", "state": "warning", "detail": "Status unknown"}
            )
    else:
        if external_telegram_worker_enabled:
            bot_worker_status_display.info(
                "⏳ Telegram Bot Worker: **Awaiting first heartbeat**"
            )
            boot_summary.append(
                {"label": "Bot Worker", "state": "starting", "detail": "Awaiting heartbeat"}
            )
        else:
            bot_worker_status_display.warning(
                "⚠️ Telegram Bot Worker: **Offline** (No status record)"
            )
            boot_summary.append(
                {"label": "Bot Worker", "state": "warning", "detail": "No status record"}
            )

    scheduler_status_row = _conn.execute(
        "SELECT value FROM system_settings WHERE key='report_scheduler_status'"
    ).fetchone()
    if scheduler_status_row and scheduler_status_row[0]:
        try:
            status_info = json.loads(scheduler_status_row[0])
            scheduler_state = status_info.get("status", "Offline")
            if scheduler_state in {"starting", "running", "idle"}:
                report_scheduler_status_display.success(
                    f"✅ Report Scheduler: **{scheduler_state.title()}**"
                )
                boot_summary.append(
                    {
                        "label": "Report Scheduler",
                        "state": "ready" if scheduler_state in {"running", "idle"} else "starting",
                        "detail": scheduler_state.title(),
                    }
                )
            else:
                report_scheduler_status_display.warning(
                    f"⚠️ Report Scheduler: **{scheduler_state}**"
                )
                boot_summary.append(
                    {
                        "label": "Report Scheduler",
                        "state": "warning",
                        "detail": str(scheduler_state).title(),
                    }
                )
        except json.JSONDecodeError:
            report_scheduler_status_display.warning(
                "⚠️ Report Scheduler: **Status Unknown**"
            )
            boot_summary.append(
                {"label": "Report Scheduler", "state": "warning", "detail": "Status unknown"}
            )
    else:
        if report_scheduler_enabled:
            report_scheduler_status_display.info(
                "⏳ Report Scheduler: **Starting**"
            )
            boot_summary.append(
                {"label": "Report Scheduler", "state": "starting", "detail": "Launching"}
            )
        else:
            report_scheduler_status_display.warning(
                "⚠️ Report Scheduler: **Offline** (No status record)"
            )
            boot_summary.append(
                {"label": "Report Scheduler", "state": "offline", "detail": "Disabled"}
            )

    st.session_state["boot_summary_cards"] = boot_summary

    # Brief visual confirmation before proceeding
    if "boot_complete" not in st.session_state:
        time.sleep(1)
        st.session_state["boot_complete"] = True
        st.rerun()

    return _conn


def ensure_runtime_dirs():
    """Create local runtime directories when they are missing."""
    for name in ("uploads", "downloads"):
        Path(name).mkdir(parents=True, exist_ok=True)


def render_login_readiness_panel():
    cards = st.session_state.get("boot_summary_cards") or []
    if not cards:
        return

    def _state_label(state: str) -> str:
        state = (state or "warning").lower()
        mapping = {
            "ready": "Ready",
            "starting": "Starting",
            "warning": "Attention",
            "offline": "Offline",
        }
        return mapping.get(state, state.title())

    markup = [
        '<div class="login-readiness">',
        '<div class="login-readiness-header">',
        '<div class="login-readiness-title">System Readiness</div>',
        '<div class="login-readiness-subtitle">Latest startup verification</div>',
        "</div>",
        '<div class="login-readiness-grid">',
    ]

    for card in cards:
        state = (card.get("state") or "warning").lower()
        label = str(card.get("label") or "Service")
        detail = str(card.get("detail") or "").strip() or "No detail available."
        markup.extend(
            [
                f'<div class="login-readiness-card is-{state}">',
                '<div class="login-readiness-topline">',
                f'<div class="login-readiness-label">{label}</div>',
                f'<div class="login-readiness-state">{_state_label(state)}</div>',
                "</div>",
                f'<div class="login-readiness-detail">{detail}</div>',
                "</div>",
            ]
        )

    markup.extend(["</div>", "</div>"])
    st.markdown("".join(markup), unsafe_allow_html=True)


conn = None
try:
    ensure_runtime_dirs()
    # If we are starting fresh, show the boot sequence.
    # Once booted or logged in, we bypass the sequence for snappier navigation.
    if "user_id" not in st.session_state and "boot_complete" not in st.session_state:
        conn = run_boot_sequence()
    else:
        conn = get_connection()
        # Ensure workers are checked if we skipped boot sequence (e.g. page refresh)
        start_background_workers()

    # --- 3. SESSION PERSISTENCE ---
    def restore_session():
        """Checks for an existing session token to keep the user logged in."""
        token = st.session_state.get("session_token")
        if token and "user_id" not in st.session_state:
            uid = validate_session_token(token)
            if uid:
                # Fetch all user-related data from the single users table
                row = conn.execute(
                    "SELECT id, username, email, role, dark_mode_enabled, name, surname, station_id, region_id, telegram_chat_id, force_password_change FROM users WHERE id = %s",
                    (uid,),
                ).fetchone()
                if row:
                    st.session_state["user_id"] = row[0]
                    st.session_state["username"] = row[1]
                    st.session_state["email"] = row[2]
                    st.session_state["user_role"] = row[3]
                    st.session_state["dark_mode"] = bool(row[4])
                    st.session_state["name"] = row[5]
                    st.session_state["surname"] = row[6]
                    st.session_state["user_name_full"] = f"{row[5]} {row[6]}".strip()
                    st.session_state["user_station_id"] = row[7]
                    st.session_state["user_region_id"] = row[8]
                    st.session_state["user_telegram_chat_id"] = row[9]
                    st.session_state["force_password_change"] = bool(row[10])
                else:
                    if "session_token" in st.session_state:
                        del st.session_state["session_token"]

    if "session_token" in st.session_state:
        restore_session()

    # --- 4. LOGIN INTERFACE ---
    if "user_id" not in st.session_state:
        st.markdown(
            """
            <style>
                [data-testid="stAppViewContainer"] .main .block-container {
                    padding-top: 0.25rem !important;
                    padding-bottom: 1.5rem !important;
                    max-width: 1120px !important;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )

        left_col, right_col = st.columns([1.25, 0.95], gap="large", vertical_alignment="top")
        with left_col:
            st.markdown('<div class="login-panel login-brand-panel">', unsafe_allow_html=True)
            logo_path = Path("assets/GSAI_Horizontal.png")
            if not logo_path.exists():
                logo_path = Path("assets/OpusLogo.png")
            if logo_path.exists():
                st.image(str(logo_path), width=250)
            st.markdown(
                """
                <div class="login-brand-copy">
                    <div class="login-kicker">Operational Video Intelligence</div>
                    <h1 class="login-title">GentStationAI</h1>
                    <p class="login-subtitle">
                        Centralized video reporting, AI risk assessment, and station oversight in one streamlined workspace.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_login_readiness_panel()
            st.markdown('<div class="login-brand-actions">', unsafe_allow_html=True)
            if st.button("Forgot Password?", type="secondary", use_container_width=True):
                st.session_state["show_forgot_pw"] = True
            st.markdown(LOGIN_DISCLAIMER_HTML, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with right_col:
            st.markdown('<div class="login-panel login-form-panel">', unsafe_allow_html=True)
            st.markdown(
                """
                <div class="login-form-header">
                    <h2 class="login-form-title">Sign in</h2>
                    <p class="login-form-subtitle">
                        Use your GentStationAI account to access dashboards, reporting, and station operations.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            status_markup = '<div class="login-status">System status: Operational</div>'
            try:
                sys_row = conn.execute(
                    "SELECT value FROM system_settings WHERE key='maintenance_mode'"
                ).fetchone()
                if sys_row and sys_row[0] == "1":
                    status_markup = (
                        '<div class="login-status">'
                        "<strong>Maintenance mode is active.</strong><br>"
                        "Login is currently restricted to General Manager accounts."
                        "</div>"
                    )
            except Exception:
                pass
            st.markdown(status_markup, unsafe_allow_html=True)

            with st.form("login_form"):
                cred = st.text_input("Username or Email")
                pw = st.text_input("Password", type="password")
                ack = st.checkbox("I acknowledge the AI usage disclaimer")

                submitted = st.form_submit_button("Login", width="stretch")

                if submitted:
                    if not ack:
                        st.error("You must acknowledge the disclaimer to log in.")
                    else:
                        ok, msg = login_user_streamlit(st, cred, pw)
                        if ok:
                            st.rerun()
                        else:
                            st.error(msg)

            if st.session_state.get("show_forgot_pw"):
                with st.form("forgot_pw_form"):
                    st.subheader("Reset Your Password")
                    email_to_reset = st.text_input(
                        "Enter your registered email address"
                    )
                    if st.form_submit_button("Send Reset Link", width="stretch"):
                        if email_to_reset:
                            send_password_reset_email(conn, email_to_reset)
                        else:
                            st.error("Please enter an email address.")
            st.markdown("</div>", unsafe_allow_html=True)

        st.stop()

    # --- 5. AUTHENTICATED APP SHELL ---
    selected_page = display_sidebar(conn)

    # --- 5.1 FORCE PASSWORD CHANGE OVERRIDE ---
    if st.session_state.get("force_password_change"):
        if selected_page != "Settings":
            st.warning(
                "🔒 **Security Requirement:** You must change your temporary password before accessing other features."
            )
            selected_page = "Settings"

    # --- Maintenance Mode Banner ---
    try:
        m_row = conn.execute(
            "SELECT value FROM system_settings WHERE key='maintenance_mode'"
        ).fetchone()
        if m_row and m_row[0] == "1":
            st.warning(
                "🚨 **MAINTENANCE MODE ACTIVE** - System access is restricted to General Managers. Some features may be unavailable.",
                icon="⚠️",
            )
    except Exception:
        pass

    try:
        schema_state = get_schema_readiness(conn)
        if not schema_state["is_ready"]:
            st.warning(
                "Postgres schema is behind the current application code. Some pages are intentionally limited until migrations are applied."
            )
            for msg in schema_state["blockers"] + schema_state["warnings"]:
                st.caption(msg)
    except Exception as e:
        logger.warning("Schema readiness check failed: %s", e)

    # Fallback
    if not selected_page:
        selected_page = "Dashboard"

    # --- 6. ROUTING LOGIC ---
    def get_page_registry():
        """Returns a mapping of page IDs to their respective render functions."""
        return {
            "Dashboard": dashboard.render,
            "Regions": regions.render,
            "Stations": stations.render,
            "Map View": map_view.render,
            "Employees": employees.render,  # Keep employees for now, will be removed if GM Dashboard is fully integrated
            "AI Reports": ai_reports.render,
            "AI Alerts": ai_alerts.render,
            "AI Monitoring": ai_monitoring.render,
            "Audit Log": audit_log.render,
            "Data Import": admin_data_import.render,
            "Admin Users": admin_users.render,
            "Settings": settings.render,
            "Help": page_help.render,
        }

    try:
        registry = get_page_registry()
        user_role = st.session_state.get("user_role")
        username = st.session_state.get("username")

        if selected_page in registry:
            if has_access(selected_page, user_role, username):
                registry[selected_page](conn)
                st.divider()
                st.markdown(
                    f"<div style='text-align: center; opacity: 0.7;'>{FOOTER_DISCLAIMER_TEXT}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.error("Access Denied.")
        else:
            st.error(f"Page '{selected_page}' not found.")

    except Exception as e:
        st.error(f"Error loading page: {e}")
finally:
    if conn:
        conn.close()
