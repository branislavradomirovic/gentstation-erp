import streamlit as st

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
    "Help": None # No help button on the help page itself
}

def render_page_header(title: str):
    """
    Renders the page title and a context-sensitive help button.
    """
    page_id = st.session_state.get("active_page")
    help_tab_name = HELP_TAB_MAP.get(page_id)

    col1, col2 = st.columns([0.9, 0.1])

    with col1:
        st.title(title)

    if help_tab_name:
        with col2:
            if st.button("❓ Help", key=f"help_btn_{page_id}", use_container_width=True, help=f"Get help for the {page_id} page"):
                st.session_state["active_page"] = "Help"
                st.session_state["help_target_tab"] = help_tab_name
                st.rerun()