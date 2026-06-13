import streamlit as st

from core.auth import logout_user_streamlit
from core.tenant_context import TenantContext
from core.access_control import PAGE_CONFIG, has_access


def display_sidebar(conn, current_tenant_context: TenantContext | None):
    """Render a simplified, robust sidebar and return the currently selected page id."""
    user_role = st.session_state.get("user_role", "Employee")
    username = st.session_state.get("username", "User")

    if "active_page" not in st.session_state:
        st.session_state.active_page = "Dashboard"
    elif st.session_state.active_page not in PAGE_CONFIG:
        st.session_state.active_page = "Dashboard"

    with st.sidebar:
        st.markdown(
            """
            <style>
                .gs-sidebar-section {
                    margin-top: 0.7rem;
                    margin-bottom: 0.1rem;
                    font-size: 0.72rem;
                    text-transform: uppercase;
                    letter-spacing: 0.08em;
                    font-weight: 800;
                    color: #5b6474;
                }
                .gs-app-meta {
                    border: 1px solid rgba(15, 23, 42, 0.08);
                    border-radius: 14px;
                    background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(244,248,252,0.95));
                    padding: 0.75rem 0.8rem;
                    margin-top: 0.35rem;
                    margin-bottom: 0.15rem;
                }
                .gs-app-name {
                    font-size: 0.98rem;
                    font-weight: 800;
                    color: #111827;
                }
                .gs-app-desc {
                    margin-top: 0.2rem;
                    font-size: 0.82rem;
                    line-height: 1.45;
                    color: #5b6474;
                }
                .gs-user-meta {
                    margin-top: 0.2rem;
                    margin-bottom: 0.35rem;
                    display: grid;
                    gap: 0.3rem;
                }
                .gs-meta-row {
                    border: 1px solid rgba(13, 110, 253, 0.14);
                    border-radius: 12px;
                    background: linear-gradient(180deg, rgba(13, 110, 253, 0.08), rgba(13, 110, 253, 0.04));
                    padding: 0.42rem 0.55rem;
                    line-height: 1.2;
                }
                .gs-meta-label {
                    font-size: 0.72rem;
                    text-transform: uppercase;
                    letter-spacing: 0.04em;
                    color: #0b5ed7;
                    font-weight: 700;
                }
                .gs-meta-value {
                    margin-top: 0.1rem;
                    font-size: 0.88rem;
                    font-weight: 600;
                    color: #1f2937;
                    word-break: break-word;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="gs-app-meta">
                <div class="gs-app-name">GentStation AI</div>
                <div class="gs-app-desc">Video reporting, operational risk scoring, and AI-driven station assessment in one workspace.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="gs-user-meta">
                <div class="gs-meta-row">
                    <div class="gs-meta-label">Signed in</div>
                    <div class="gs-meta-value">{username}</div>
                </div>
                <div class="gs-meta-row">
                    <div class="gs-meta-label">Role</div>
                    <div class="gs-meta-value">{user_role}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        def _nav_button(pid: str, label: str, key_suffix: str = ""):
            if not has_access(
                pid,
                user_role,
                username,
                tenant_context=current_tenant_context,
                conn=conn,
            ):
                return
            icon = PAGE_CONFIG[pid].get("icon", "")
            is_active = st.session_state.active_page == pid
            key = f"sidebar_{pid}_{key_suffix}" if key_suffix else f"sidebar_{pid}"
            if st.button(
                f"{icon} {label}",
                key=key,
                type=("primary" if is_active else "secondary"),
                width="stretch",
            ):
                st.session_state.active_page = pid
                st.rerun()

        _nav_button("Dashboard", "Home Dashboard", "home_dashboard")

        menu_groups = [
            {
                "title": "Network",
                "pages": [
                    ("Regions", "Regions", "org_regions"),
                    ("Stations", "Stations", "org_stations"),
                    ("Employees", "Employees", "org_employees"),
                    ("Map View", "Map View", "org_map_view"),
                ],
            },
            {
                "title": "AI Workspace",
                "pages": [
                    ("AI Reports", "AI Reports", "ai_reports"),
                    ("AI Alerts", "AI Alerts", "ai_alerts"),
                    ("AI Monitoring", "AI Monitoring", "ai_monitoring"),
                    ("CCTV Intelligence", "CCTV Intelligence", "cctv_intelligence"),
                ],
            },
            {
                "title": "Administration",
                "pages": [
                    ("Tenant Plan", "Tenant Plan", "tenant_plan"),
                    ("Settings", "Settings", "setting_root"),
                    ("Admin Users", "Admin Users", "setting_admin_users"),
                    ("Audit Log", "Audit Log", "setting_audit_log"),
                    ("Help", "Help", "setting_help"),
                ],
            },
        ]

        for group in menu_groups:
            visible_pages = [
                item
                for item in group["pages"]
                if has_access(
                    item[0],
                    user_role,
                    username,
                    tenant_context=current_tenant_context,
                    conn=conn,
                )
            ]
            if not visible_pages:
                continue
            st.markdown(
                f'<div class="gs-sidebar-section">{group["title"]}</div>',
                unsafe_allow_html=True,
            )
            for pid, label, key_suffix in visible_pages:
                _nav_button(pid, label, key_suffix)

        st.divider()
        if st.button("🚪 Logout", key="sidebar_logout", width="stretch"):
            logout_user_streamlit(st)
            st.rerun()

    return st.session_state.active_page
