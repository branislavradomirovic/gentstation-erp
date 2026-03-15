import streamlit as st
import pandas as pd
import os
from pathlib import Path
from core.auth import logout_user_streamlit

# --- 1. PAGE CONFIGURATION ---
# Centralized definition for pages, their icons, and access roles.
# This makes the sidebar modular and easier to maintain.
PAGE_CONFIG = {
    "Dashboard": {
        "id": "Dashboard",
        "icon": "🏠",
        "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager", "Gas Station Supervisor", "Employee"]
    },
    "Regions": {
        "id": "Regions",
        "icon": "🌍",
        "roles": ["General Manager"]
    },
    "Stations": {
        "id": "Stations",
        "icon": "⛽",
        "roles": ["General Manager", "Region Director", "Region Manager"]
    },
    "Map View": {
        "id": "Map View",
        "icon": "🗺️",
        "roles": ["General Manager", "Region Director", "Region Manager"]
    },
    "Employees": {
        "id": "Employees",
        "icon": "👥",
        "roles": ["General Manager"]
    },
    "AI Reports": {
        "id": "AI Reports",
        "icon": "📈",
        "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager"]
    },
    "AI Alerts": {
        "id": "AI Alerts",
        "icon": "🚨",
        "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager"]
    },
    "Audit Log": {
        "id": "Audit Log",
        "icon": "🛡️",
        "roles": ["General Manager"]
    },
    "GM Dashboard": {
        "id": "GM Dashboard",
        "icon": "📊",
        "roles": ["General Manager"]
    },
    "Admin Users": { "id": "Admin Users", "icon": "👤", "roles": ["General Manager"] },
    "Settings": { "id": "Settings", "icon": "⚙", "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager", "Gas Station Supervisor", "Employee"] },
    "Help": { "id": "Help", "icon": "❓", "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager", "Gas Station Supervisor", "Employee"] }
}

def get_logo_path():
    """Locates the logo using an absolute path relative to this file."""
    base_path = Path(__file__).resolve().parents[1] 
    logo_file = base_path / "assets" / "OpusLogo.png"
    return str(logo_file) if logo_file.exists() else None

def display_sidebar(conn):
    user_role = st.session_state.get("user_role", "Employee")
    username = st.session_state.get("username", "User")
    
    with st.sidebar:
        # 1. BRANDING & USER (Updated for horizontal alignment)
        logo_col, title_col = st.columns([1, 2], vertical_alignment="center")
        with logo_col:
            logo = get_logo_path()
            if logo:
                st.image(logo, width=70)
        with title_col:
            st.markdown(f"**Gas Station Manager**")
            st.caption(f"👤 `{username}` | {user_role}")
        
        st.write("") 

        # 2. DYNAMIC NAVIGATION MENU (New Structure)
        MENU_STRUCTURE = {
            "main": ["Dashboard", "Help"],
            "expanders": {
                "📊 Dashboard": ["GM Dashboard", "Map View"],
                "🏢 Organization": ["Regions", "Stations", "Employees"],
                "🤖 AI Control": ["AI Reports", "AI Alerts"],
                "⚙️ Settings": ["Admin Users", "Settings", "Audit Log"]
            }
        }

        # Get all pages visible to the current user
        visible_pages_details = {
            page['id']: {"label": label, "icon": page['icon']}
            for label, page in PAGE_CONFIG.items()
            if user_role in page['roles']
        }
        visible_page_ids = set(visible_pages_details.keys())

        # Default to dashboard if active page is not set or not accessible
        if "active_page" not in st.session_state or st.session_state.active_page not in visible_page_ids:
            st.session_state.active_page = "Dashboard"

        # 3. RENDER MENU
        for page_id in MENU_STRUCTURE["main"]:
            if page_id in visible_page_ids:
                details = visible_pages_details[page_id]
                is_active = st.session_state.active_page == page_id
                if st.button(f"{details['icon']} {details['label']}", key=f"btn_{page_id}", use_container_width=True, type="primary" if is_active else "secondary"):
                    st.session_state.active_page = page_id
                    st.rerun()

        for expander_label, page_ids in MENU_STRUCTURE["expanders"].items():
            visible_submenu_pages = [pid for pid in page_ids if pid in visible_page_ids]
            if not visible_submenu_pages:
                continue

            is_expander_active = st.session_state.active_page in visible_submenu_pages
            with st.expander(expander_label, expanded=is_expander_active):
                for page_id in visible_submenu_pages:
                    details = visible_pages_details[page_id]
                    is_active = st.session_state.active_page == page_id
                    if st.button(f"{details['icon']} {details['label']}", key=f"btn_{page_id}", use_container_width=True, type="primary" if is_active else "secondary"):
                        st.session_state.active_page = page_id
                        st.rerun()

        # 4. SYSTEM ACTIONS
        st.write("")
        if st.button("🚪 Logout", use_container_width=True):
            logout_user_streamlit(st)
            st.rerun()

        # 5. RECENT ACTIVITY
        st.divider()
        st.caption("🔔 Recent Activity")
        try:
            recent_logs = pd.read_sql_query("""
                SELECT user_name, action, timestamp 
                FROM activity_logs 
                ORDER BY timestamp DESC LIMIT 3
            """, conn)
            
            for _, row in recent_logs.iterrows():
                # Extract time HH:MM
                time_val = row['timestamp'].split(" ")[1][:5] if " " in row['timestamp'] else row['timestamp']
                st.markdown(f"**{time_val}** `{row['user_name']}`  \n*{row['action']}*")
        except Exception:
            pass # Silently fail if logs are not available
        
    return st.session_state.active_page