import streamlit as st
import pandas as pd
import os
from pathlib import Path

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
            
            st.markdown(f"**Opus GentStationAI**")
            st.caption(f"👤 `{username}` | {user_role}")
        
        # Spacer to separate branding from navigation
        st.write("") 

        # 2. NAVIGATION MENU DEFINITION
        menu_items = {"🏠 Dashboard": "Dashboard"}
        
        if user_role == "General Manager":
            menu_items.update({
                "🌍 Regions": "Regions",
                "⛽ Stations": "Stations",
                "👥 Employees": "Employees",
                "📈 AI Reports": "AI Reports",
                "🛡️ Audit Log": "Audit Log",
                "📊 GM Dashboard": "GM Dashboard",
                "👤 Admin Users": "Admin Users"
            })
        elif user_role in ["Region Director", "Region Manager"]:
            menu_items.update({
                "⛽ Stations": "Stations", 
                "📈 AI Reports": "AI Reports"
            })

        if "active_page" not in st.session_state:
            st.session_state.active_page = "Dashboard"

        # 3. RENDER MENU BUTTONS
        # The 1.2rem gap from app.py will apply between these elements
        for label, page_id in menu_items.items():
            is_active = st.session_state.active_page == page_id
            
            if st.button(label, key=f"btn_{page_id}", 
                         use_container_width=True, 
                         type="primary" if is_active else "secondary"):
                st.session_state.active_page = page_id
                st.rerun()

        # 4. SYSTEM ACTIONS
        # Adding some space before logout to keep it distinct
        st.write("")
        if st.button("🚪 Logout", use_container_width=True):
            for k in list(st.session_state.keys()): 
                del st.session_state[k]
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
            pass
        
    return st.session_state.active_page