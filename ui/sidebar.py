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
        # 1. BRANDING & USER (Wrapped in container to stay tight together)
        with st.container():
            logo = get_logo_path()
            if logo:
                st.image(logo, width=100) 
            
            st.markdown(f"**Gas Station Manager**")
            st.caption(f"👤 `{username}` | {user_role}")
        
        # Spacer to separate branding from navigation
        st.write("") 

        # 2. DYNAMIC NAVIGATION MENU
        # Filter pages from PAGE_CONFIG based on the current user's role
        visible_pages = {
            f"{page['icon']} {label}": page['id']
            for label, page in PAGE_CONFIG.items()
            if user_role in page['roles']
        }

        # Default to dashboard if active page is not set or not accessible
        if "active_page" not in st.session_state or st.session_state.active_page not in visible_pages.values():
            st.session_state.active_page = "Dashboard"

        # 3. RENDER MENU BUTTONS
        for label, page_id in visible_pages.items():
            is_active = st.session_state.active_page == page_id
            
            if st.button(label, key=f"btn_{page_id}", 
                         use_container_width=True, 
                         type="primary" if is_active else "secondary"):
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