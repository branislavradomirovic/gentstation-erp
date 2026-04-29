import streamlit as st
from core.database import get_connection

# Mapping from page ID to the help tab name in pages/help.py
HELP_TAB_MAP = {
    "Dashboard": "Overview & submission",
    "Personal Dashboard": "Overview & submission",
    "Shifts": "Management Modules",
    "Regions": "Management Modules",
    "Stations": "Management Modules",
    "Employees": "Management Modules",
    "Map View": "Dashboards & Reporting",
    "AI Reports": "Dashboards & Reporting",
    "GM Dashboard": "Dashboards & Reporting",
    "Admin Users": "System Administration",
    "Audit Log": "System Administration",
    "Settings": "System Administration",
    "Help": None,  # No help button on the help page itself
}


def render_page_header(title: str):
    """
    Renders the page title and a context-sensitive help button.
    """
    page_id = st.session_state.get("active_page")
    help_tab_name = HELP_TAB_MAP.get(page_id)

    # Fetch unresolved alerts count (new + acknowledged)
    alert_count = 0
    try:
        # Use a transient connection for the header check to avoid affecting passed connections
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) FROM ai_alerts WHERE status IN ('new', 'acknowledged')"
        ).fetchone()
        if row:
            alert_count = row[0]
        conn.close()
    except Exception:
        pass

    # Determine layout based on visible elements
    show_alerts = alert_count > 0
    show_help = help_tab_name is not None

    if show_alerts and show_help:
        col1, col2, col3 = st.columns([0.8, 0.1, 0.1])
        alert_col, help_col = col2, col3
    elif show_alerts:
        col1, col2 = st.columns([0.9, 0.1])
        alert_col, help_col = col2, None
    elif show_help:
        col1, col2 = st.columns([0.9, 0.1])
        alert_col, help_col = None, col2
    else:
        col1 = st.container()
        alert_col, help_col = None, None

    with col1:
        st.title(title)

    if alert_col:
        with alert_col:
            if st.button(
                f"🔔 {alert_count}",
                key="header_alert_btn",
                width="stretch",
                type="primary",
                help="Unresolved Alerts",
            ):
                st.session_state["active_page"] = "AI Alerts"
                st.rerun()

    if help_col:
        with help_col:
            if st.button(
                "❓ Help",
                key=f"help_btn_{page_id}",
                width="stretch",
                help=f"Help: {page_id}",
            ):
                st.session_state["active_page"] = "Help"
                st.session_state["help_target_tab"] = help_tab_name
                st.rerun()
