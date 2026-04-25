import os
import logging
import warnings
import streamlit as st
from pathlib import Path

import subprocess
import sys

warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy connectable",
)
try:
    from urllib3.exceptions import NotOpenSSLWarning

    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gentstation.app")


# --- 1. PAGE CONFIGURATION (MUST BE FIRST) ---
st.set_page_config(
    page_title="Gas Station Manager",
    layout="wide",
    initial_sidebar_state="expanded"
)

def start_background_workers():
    """
    Ensure background processes (Telegram Bot, AI Worker) are running.
    Uses lock-file PID checks to avoid duplicate launches across reruns.
    """
    project_root = Path(__file__).resolve().parent
    bot_lock_file = Path("/tmp/gentstationai_bot_worker.lock")
    ai_lock_file = Path("/tmp/gentstationai_ai_worker.lock")

    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except Exception:
            return False
        # Treat zombie state as not running.
        try:
            stat = subprocess.check_output(["ps", "-p", str(pid), "-o", "stat="], text=True).strip()
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
            subprocess.Popen(
                [sys.executable, "-u", str(script_path)],
                cwd=str(project_root),
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
            )
            return True
        except Exception as e:
            logger.warning("Could not start worker %s: %s", script_path, e)
            return False

    def _env_bool(name: str, default: str = "1") -> bool:
        return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

    auto_start = _env_bool("AUTO_START_BACKGROUND_WORKERS", "1")
    auto_start_telegram = _env_bool("AUTO_START_TELEGRAM_BOT", "1")
    auto_start_ai = _env_bool("AUTO_START_AI_WORKER", "1")

    if not auto_start:
        logger.info("AUTO_START_BACKGROUND_WORKERS is disabled. Skipping worker startup.")
        return
    
    # 1. Start Telegram Bot
    bot_script = project_root / "bot" / "bot_worker.py"
    telegram_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not auto_start_telegram:
        logger.info("AUTO_START_TELEGRAM_BOT is disabled. Skipping Telegram Bot startup.")
    elif _is_running_from_lock(bot_lock_file):
        logger.debug("Telegram Bot worker already running.")
    elif bot_script.exists() and telegram_token:
        if _spawn_worker(bot_script, Path("/tmp/gentstation_bot.log")):
            logger.info("Started Telegram Bot worker: %s", bot_script)
    elif bot_script.exists():
        logger.info("Skipping Telegram Bot startup (TELEGRAM_BOT_TOKEN is not configured).")

    # 2. Start AI Worker
    ai_script = project_root / "core" / "ai_worker.py"
    if not auto_start_ai:
        logger.info("AUTO_START_AI_WORKER is disabled. Skipping AI worker startup.")
    elif _is_running_from_lock(ai_lock_file):
        logger.debug("AI worker already running.")
    elif ai_script.exists():
        if _spawn_worker(ai_script, Path("/tmp/gentstation_ai.log")):
            logger.info("Started AI worker: %s", ai_script)

# --- 2. GLOBAL CSS INJECTION (Optimized for Spacing & Alignment) ---
st.markdown("""
    <style>
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
            gap: 1.5rem !important; 
        }
        
        /* Ensure the logo image stays flush */
        [data-testid="stSidebar"] [data-testid="stImage"] {
            margin-top: 0px !important;
            padding-top: 0px !important;
        }

        /* UI Polish: Rounded buttons and taller height for breathability */
        .stButton button { 
            border-radius: 8px;
            height: 2.8em;
            margin-top: 0.2rem;
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
    </style>
""", unsafe_allow_html=True)

# --- DARK MODE INJECTION ---
if st.session_state.get("dark_mode"):
    st.markdown("""
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
    """, unsafe_allow_html=True)

# Core imports
from core.database import get_connection, ensure_schema
from core.auth import login_user_streamlit, logout_user_streamlit, hash_password as hash_password_bcrypt
from core.session import validate_session_token
from core.activity_logger import log_activity
from core.config import LOGIN_DISCLAIMER_HTML, FOOTER_DISCLAIMER_TEXT

# Page imports
import pages.dashboard as dashboard
import pages.role_center as role_center
import pages.shifts as shifts
import pages.regions as regions
import pages.stations as stations
import pages.map_view as map_view
import pages.employees as employees
import pages.admin_users as admin_users
import pages.gm_dashboard as gm_dashboard
import pages.ai_reports as ai_reports
import pages.ai_alerts as ai_alerts
import pages.ai_monitoring as ai_monitoring
import pages.audit_log as audit_log
import pages.settings as settings
import pages.help as page_help

# UI imports
from ui.sidebar import display_sidebar, PAGE_CONFIG

# Communication service for password reset
try:
    from core.comm_service import send_password_reset_email
except ImportError:
    def send_password_reset_email(*args, **kwargs): st.error("Email service unavailable.")

def _build_db_unavailable_message(error: Exception) -> str:
    return (
        "Database connection is unavailable right now. "
        "Please make sure PostgreSQL is running and reachable at the host configured in `.env` "
        f"(current error: {error})."
    )


conn = None
try:
    # Initialize Database
    try:
        conn = get_connection()
    except Exception as db_error:
        st.error(_build_db_unavailable_message(db_error))
        st.info(
            "If you are running locally, start PostgreSQL on your machine or run the Docker stack. "
            "If you are using Docker, verify the `postgres` service is up and healthy."
        )
        st.stop()

    # Initialize workers only after the database is reachable.
    start_background_workers()

    # --- 3. SESSION PERSISTENCE ---
    def restore_session():
        """Checks for an existing session token to keep the user logged in."""
        token = st.session_state.get("session_token")
        if token and "user_id" not in st.session_state:
            uid = validate_session_token(token)
            if uid:
                # Using standard parameter replacement to avoid '? vs %s' confusion
                row = conn.execute(
                    "SELECT id, username, email, role, dark_mode_enabled FROM users WHERE id = %s", (uid,)
                ).fetchone()
                if row:
                    st.session_state["user_id"] = row[0]
                    st.session_state["username"] = row[1]
                    st.session_state["user_role"] = row[3]
                    st.session_state["dark_mode"] = bool(row[4])
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
                /* Pull login content to the top of the viewport. */
                [data-testid="stAppViewContainer"] .main .block-container {
                    padding-top: 0.4rem !important;
                    margin-top: 0 !important;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # Center logo and login form in the same column for visual alignment.
        _, content_col, _ = st.columns([1, 1.6, 1], vertical_alignment="top")
        with content_col:
            logo_path = Path("assets/GSAI_Horizontal.png")
            if not logo_path.exists():
                logo_path = Path("assets/OpusLogo.png")
            if logo_path.exists():
                st.image(str(logo_path), use_container_width=True)

            # Add a bit of space before the form
            st.markdown("<br>", unsafe_allow_html=True)

            # --- SYSTEM STATUS WIDGET ---
            try:
                sys_row = conn.execute("SELECT value FROM system_settings WHERE key='maintenance_mode'").fetchone()
                if sys_row and sys_row[0] == '1':
                    st.warning("🛠️ **MAINTENANCE MODE**\n\nLogin restricted to Administrators.", icon="⚠️")
                else:
                    st.caption("🟢 System Status: **Operational**")
            except Exception:
                pass

            with st.form("login_form"):
                cred = st.text_input("Username or Email")
                pw = st.text_input("Password", type="password")
                ack = st.checkbox("I acknowledge the disclaimer below")

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

            # --- FORGOT PASSWORD ---
            if st.button("Forgot Password?", type="secondary"):
                st.session_state['show_forgot_pw'] = True

            if st.session_state.get('show_forgot_pw'):
                with st.form("forgot_pw_form"):
                    st.subheader("Reset Your Password")
                    email_to_reset = st.text_input("Enter your registered email address")
                    if st.form_submit_button("Send Reset Link", width="stretch"):
                        if email_to_reset:
                            send_password_reset_email(conn, email_to_reset)
                        else:
                            st.error("Please enter an email address.")

        # Render disclaimer outside the centered login column so it spans the full page content width.
        st.markdown(LOGIN_DISCLAIMER_HTML, unsafe_allow_html=True)

        st.stop()

    # --- 5. AUTHENTICATED APP SHELL ---
    selected_page = display_sidebar(conn)

    # --- Maintenance Mode Banner ---
    try:
        m_row = conn.execute("SELECT value FROM system_settings WHERE key='maintenance_mode'").fetchone()
        if m_row and m_row[0] == '1':
            st.warning("🚨 **MAINTENANCE MODE ACTIVE** - System access is restricted to General Managers. Some features may be unavailable.", icon="⚠️")
    except Exception:
        pass

    # Fallback
    if not selected_page:
        selected_page = "Dashboard"

    # --- 6. ROUTING LOGIC ---
    try:
        PAGE_HANDLERS = {
            "Dashboard": dashboard.render,
            "Personal Dashboard": role_center.render,
            "Shifts": shifts.render,
            "Regions": regions.render,
            "Stations": stations.render,
            "Map View": map_view.render,
            "Employees": employees.render,
            "AI Reports": ai_reports.render,
            "AI Alerts": ai_alerts.render,
            "AI Monitoring": ai_monitoring.render,
            "Audit Log": audit_log.render,
            "GM Dashboard": gm_dashboard.render,
            "Admin Users": admin_users.render,
            "Settings": settings.render,
            "Help": page_help.render
        }

        if selected_page in PAGE_HANDLERS:
            required_roles = PAGE_CONFIG.get(selected_page, {}).get("roles", [])
            if st.session_state.get("user_role") in required_roles:
                PAGE_HANDLERS[selected_page](conn)
                st.divider()
                st.markdown(f"<div style='text-align: center; opacity: 0.7;'>{FOOTER_DISCLAIMER_TEXT}</div>", unsafe_allow_html=True)
            else:
                st.error("Access Denied.")
        else:
            st.error(f"Page '{selected_page}' not found.")

    except Exception as e:
        st.error(f"Error loading page: {e}")
finally:
    if conn:
        conn.close()
