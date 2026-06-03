import streamlit as st
from core.database import get_connection

# Mapping from page ID to the help tab name in pages/help.py
HELP_TAB_MAP = {
    "Dashboard": "Overview & submission",
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

    st.markdown(
        """
        <style>
            .gs-page-header {
                display:flex;
                justify-content:space-between;
                align-items:flex-start;
                gap:1rem;
                margin-bottom:0.9rem;
                padding:0.15rem 0 0 0;
            }
            .gs-page-header-copy {
                display:grid;
                gap:0.2rem;
            }
            .gs-page-header-eyebrow {
                font-size:0.76rem;
                font-weight:700;
                text-transform:uppercase;
                letter-spacing:0.08em;
                color:#0b5ed7;
            }
            .gs-page-header-title {
                margin:0;
                font-size:1.85rem;
                line-height:1.1;
                color:#111827;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    action_count = int(alert_count > 0) + int(help_tab_name is not None)
    if action_count == 2:
        col1, col2, col3 = st.columns([0.78, 0.11, 0.11], vertical_alignment="bottom")
        alert_col, help_col = col2, col3
    elif alert_count > 0:
        col1, col2 = st.columns([0.89, 0.11], vertical_alignment="bottom")
        alert_col, help_col = col2, None
    elif help_tab_name is not None:
        col1, col2 = st.columns([0.89, 0.11], vertical_alignment="bottom")
        alert_col, help_col = None, col2
    else:
        col1 = st.container()
        alert_col, help_col = None, None

    section_name = page_id or "Workspace"
    with col1:
        st.markdown(
            f"""
            <div class="gs-page-header">
                <div class="gs-page-header-copy">
                    <div class="gs-page-header-eyebrow">{section_name}</div>
                    <h1 class="gs-page-header-title">{title}</h1>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
