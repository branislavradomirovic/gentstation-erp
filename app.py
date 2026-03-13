import os
import streamlit as st
from pathlib import Path

import subprocess
import sys


# Start the bot as a background process if not already running
if "bot_started" not in st.session_state:
    subprocess.Popen([sys.executable, "bot_worker.py"])
    st.session_state["bot_started"] = True

# Start the AI worker as a background process if not already running
if "ai_worker_started" not in st.session_state:
    subprocess.Popen([sys.executable, "core/ai_worker.py"])
    st.session_state["ai_worker_started"] = True


# --- 1. PAGE CONFIGURATION (MUST BE FIRST) ---
st.set_page_config(
    page_title="GentStation Opus ERP",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
            margin-top: -1.5rem !important;
        }

        /* INCREASED VERTICAL SPACING between sidebar components */
        [data-testid="stVerticalBlock"] { 
            gap: 0.5rem !important; 
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
    </style>
""", unsafe_allow_html=True)

# Core imports
from core.database import get_connection, ensure_schema
from core.auth import login_user_streamlit, logout_user_streamlit
from core.session import validate_session_token
from core.activity_logger import log_activity

# Page imports
import pages.dashboard as dashboard
import pages.regions as regions
import pages.stations as stations
import pages.employees as employees
import pages.admin_users as admin_users
import pages.gm_dashboard as gm_dashboard
import pages.ai_reports as ai_reports
import pages.audit_log as audit_log

# UI imports
from ui.sidebar import display_sidebar

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
                "SELECT id, username, email, role FROM users WHERE id = ?", (uid,)
            ).fetchone()
            if row:
                st.session_state["user_id"] = row[0]
                st.session_state["username"] = row[1]
                st.session_state["user_role"] = row[3]
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
        st.markdown("<h2 style='margin: 0; padding: 0;'>GentStation Opus ERP</h2>", unsafe_allow_html=True)

    # Add a bit of space before the form
    st.markdown("<br>", unsafe_allow_html=True)    

    with st.form("login_form"):
        cred = st.text_input("Username or Email")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Login", use_container_width=True):
            ok, msg = login_user_streamlit(st, cred, pw)
            if ok:
                st.rerun()
            else:
                st.error(msg)
    st.stop()

# --- 5. AUTHENTICATED APP SHELL ---
selected_page = display_sidebar(conn)

# Fallback: If for some reason selected_page is None or empty, default to Dashboard
if not selected_page:
    selected_page = "Dashboard"

# --- 6. ROUTING LOGIC ---
try:
    if selected_page == "Dashboard":
        dashboard.render(conn)
    elif selected_page == "Regions":
        regions.render(conn)
    elif selected_page == "Stations":
        stations.render(conn)
    elif selected_page == "Employees":
        employees.render(conn)
    elif selected_page == "AI Reports":
        ai_reports.render(conn)
    elif selected_page == "Audit Log":
        audit_log.render(conn)
    elif selected_page == "GM Dashboard":
        gm_dashboard.render(conn)
    elif selected_page == "Admin Users":
        if st.session_state.get("user_role") == "General Manager":
            admin_users.render(conn)
        else:
            st.error("Access Denied.")
            
except Exception as e:
    st.error(f"Error loading page: {e}")
    st.info("Check if the page module is correctly defined in the /pages folder.")