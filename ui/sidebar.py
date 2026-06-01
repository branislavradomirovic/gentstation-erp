from pathlib import Path

import streamlit as st

from core.auth import logout_user_streamlit
from core.access_control import PAGE_CONFIG, has_access


def get_logo_path():
    base_path = Path(__file__).resolve().parents[1]
    # Look for common logo filename variants (PNG or SVG), prefer compact
    # sidebar-specific asset then the horizontal branding.
    candidates = [
        base_path / "assets" / "GSI_SideBar.png",
        base_path / "assets" / "GSI_SideBar.svg",
        base_path / "assets" / "GSAI_Horizontal.png",
        base_path / "assets" / "GSAI_Horizontal.svg",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def display_sidebar(conn):
    """Render a simplified, robust sidebar and return the currently selected page id."""
    user_role = st.session_state.get("user_role", "Employee")
    username = st.session_state.get("username", "User")

    if "active_page" not in st.session_state:
        st.session_state.active_page = "Dashboard"
    elif st.session_state.active_page == "Role Center":
        # One-time compatibility migration from the old route key.
        st.session_state.active_page = "Personal Dashboard"

    with st.sidebar:
        st.markdown(
            """
            <style>
                .gs-user-meta {
                    margin-top: 0.25rem;
                    margin-bottom: 0.4rem;
                    display: grid;
                    gap: 0.35rem;
                }
                .gs-meta-row {
                    border: 1px solid rgba(13, 110, 253, 0.22);
                    border-radius: 10px;
                    background: rgba(13, 110, 253, 0.08);
                    padding: 0.35rem 0.5rem;
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
                    font-size: 0.9rem;
                    font-weight: 600;
                    color: #1f2937;
                    word-break: break-word;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )

        logo = get_logo_path()
        if logo:
            logo_path = Path(logo)
            try:
                # Render with explicit dimensions so the logo is clear and centered
                if logo_path.suffix.lower() == ".svg":
                    svg = logo_path.read_text()
                    svg_escaped = svg.replace("\n", "").replace('"', "'")
                    st.markdown(
                        f"<div style='text-align:center;padding:6px 0;'><img src=\"data:image/svg+xml;utf8,{svg_escaped}\" style='width:160px;height:auto;display:inline-block;border-radius:6px;' /></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    # For PNG/JPG, use an <img> tag so we can control max-width
                    st.markdown(
                        f"<div style='text-align:center;padding:6px 0;'><img src=\"{logo_path.as_posix()}\" style='max-width:160px;height:auto;display:inline-block;border-radius:6px;' /></div>",
                        unsafe_allow_html=True,
                    )
            except Exception:
                # Last-resort fallback
                st.image(str(logo_path), use_container_width=True)
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
            if not has_access(pid, user_role):
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

        # Home Dashboard is a direct menu item (no submenu).
        _nav_button("Dashboard", "Home Dashboard", "home_dashboard")

        menu_groups = [
            {
                "title": "🕒 Time Management",
                "pages": [
                    (
                        "Personal Dashboard",
                        "Personal Dashboard",
                        "time_personal_dashboard",
                    ),
                    ("Shifts", "Shifts & Attendance", "time_shifts_attendance"),
                ],
            },
            {
                "title": "🏢 Organization Management",
                "pages": [
                    ("Regions", "Regions", "org_regions"),
                    ("Stations", "Stations", "org_stations"),
                    ("Employees", "Employees", "org_employees"),
                    ("Map View", "Map View", "org_map_view"),
                ],
            },
            {
                "title": "🤖 AI Management",
                "pages": [
                    ("AI Reports", "AI Reports", "ai_reports"),
                    ("AI Alerts", "AI Alerts", "ai_alerts"),
                    ("AI Monitoring", "AI Monitoring", "ai_monitoring"),
                ],
            },
            {
                "title": "⚙️ Settings Management",
                "pages": [
                    ("Settings", "General Settings", "setting_root"),
                    ("Admin Users", "Admin Users", "setting_admin_users"),
                    ("Audit Log", "System Audit Log", "setting_audit_log"),
                    ("Help", "Help", "setting_help"),
                ],
            },
        ]

        for group in menu_groups:
            visible_pages = [
                item for item in group["pages"] if has_access(item[0], user_role)
            ]
            if not visible_pages:
                continue
            expanded = st.session_state.active_page in [
                pid for pid, _, _ in visible_pages
            ]
            with st.expander(group["title"], expanded=expanded):
                for pid, label, key_suffix in visible_pages:
                    _nav_button(pid, label, key_suffix)
                if group["title"] == "⚙️ Settings Management":
                    if st.button("🚪 Logout", key="sidebar_logout", width="stretch"):
                        logout_user_streamlit(st)
                        st.rerun()

    return st.session_state.active_page
