import os
import streamlit as st
from pathlib import Path

import subprocess
import sys


# --- 1. PAGE CONFIGURATION (MUST BE FIRST) ---
st.set_page_config(
    page_title="Gas Station Manager",
    layout="wide",
    initial_sidebar_state="expanded"
)

@st.cache_resource
def start_background_workers():
    """
    Starts background processes (Telegram Bot, AI Worker) exactly once
    per server session using Streamlit's cache mechanism.
    """
    project_root = Path(__file__).resolve().parent
    
    # 1. Start Telegram Bot
    bot_script = project_root / "bot_worker.py"
    if bot_script.exists():
        subprocess.Popen([sys.executable, str(bot_script)], cwd=str(project_root))
        print(f"🚀 [app.py] Started Bot Worker: {bot_script}")

    # 2. Start AI Worker
    ai_script = project_root / "core" / "ai_worker.py"
    if ai_script.exists():
        subprocess.Popen([sys.executable, str(ai_script)], cwd=str(project_root))
        print(f"🧠 [app.py] Started AI Worker: {ai_script}")

# Initialize workers
start_background_workers()

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
from core.auth import login_user_streamlit, logout_user_streamlit
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
import pages.gm_dashboard as gm_dashboard
import pages.ai_reports as ai_reports
import pages.ai_alerts as ai_alerts
import pages.audit_log as audit_log
import pages.settings as settings
import pages.help as page_help

# UI imports
from ui.sidebar import display_sidebar, PAGE_CONFIG

# Initialize Database
conn = get_connection()

# --- 3. SESSION PERSISTENCE ---
def restore_session():
    """Checks for an existing session token to keep the user logged in."""
    token = st.session_state.get("session_token")
    if token and "user_id" not in st.session_state:
        uid = validate_session_token(token)
        if uid:
            row = conn.execute(
                "SELECT id, username, email, role, dark_mode_enabled FROM users WHERE id = ?", (uid,)
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
    # Use a column layout: [1, 4, 1] - small side buffers, logo, then text
    # We use 5 columns to center the pair: [buffer, logo, text, buffer]
    _, logo_col, text_col, _ = st.columns([1.5, 0.4, 1.8, 1.5], vertical_alignment="center")
    
    with logo_col:
        logo_path = Path("assets/OpusLogo.png")
        if logo_path.exists():
            # We set a fixed width (e.g., 80px) to match the height of H2 text
            st.image(str(logo_path), width=100)
            
    with text_col:
        # Removing the 'text-align: center' since it is now left-aligned to the logo
        st.markdown("<h2 style='margin: 0; padding: 0;'>Gas Station Manager</h2>", unsafe_allow_html=True)

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
        if st.form_submit_button("Login", use_container_width=True):
            if not ack:
                st.error("You must acknowledge the disclaimer to log in.")
            else:
                ok, msg = login_user_streamlit(st, cred, pw)
                if ok:
                    st.rerun()
                else:
                    st.error(msg)

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
    # Fail silently if the table/column doesn't exist yet
    pass

# Fallback: If for some reason selected_page is None or empty, default to Dashboard
if not selected_page:
    selected_page = "Dashboard"

# --- 6. ROUTING LOGIC ---
try:
    # Dictionary mapping page IDs to their render functions
    PAGE_HANDLERS = {
        "Dashboard": dashboard.render,
        "Regions": regions.render,
        "Stations": stations.render,
        "Map View": map_view.render,
        "Employees": employees.render,
        "AI Reports": ai_reports.render,
        "AI Alerts": ai_alerts.render,
        "Audit Log": audit_log.render,
        "GM Dashboard": gm_dashboard.render,
        "Admin Users": admin_users.render,
        "Settings": settings.render,
        "Help": page_help.render
    }

    if selected_page in PAGE_HANDLERS:
        # Verify permissions using the centralized PAGE_CONFIG from sidebar
        required_roles = PAGE_CONFIG.get(selected_page, {}).get("roles", [])
        
        if st.session_state.get("user_role") in required_roles:
            PAGE_HANDLERS[selected_page](conn)
            
            st.divider()
            # Centered footer disclaimer
            st.markdown(f"<div style='text-align: center; opacity: 0.7;'>{FOOTER_DISCLAIMER_TEXT}</div>", unsafe_allow_html=True)
        else:
            st.error("Access Denied. You do not have permission to view this page.")
            st.warning("Please select a page from the sidebar.")
    else:
        st.error(f"Page '{selected_page}' not found.")

except Exception as e:
    st.error(f"Error loading page: {e}")
    st.info("Check if the page module is correctly defined in the /pages folder.")