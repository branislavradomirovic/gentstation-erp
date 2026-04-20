import json
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

from core.auth import logout_user_streamlit
from core.activity_logger import log_activity
from pages.shifts import (
    _get_current_user,
    _current_active_shift,
    _upcoming_scheduled_shift,
    _start_shift,
    _clock_out_shift,
    _start_break,
    _end_break,
)

# Centralized definition for pages, their icons, and access roles.
PAGE_CONFIG = {
    "Dashboard": {
        "id": "Dashboard",
        "icon": "🏠",
        "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager", "Gas Station Supervisor", "Employee"],
    },
    "Role Center": {
        "id": "Role Center",
        "icon": "🧭",
        "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager", "Gas Station Supervisor", "Employee"],
    },
    "Shifts": {
        "id": "Shifts",
        "icon": "🕒",
        "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager", "Gas Station Supervisor", "Employee"],
    },
    "Regions": {
        "id": "Regions",
        "icon": "🌍",
        "roles": ["General Manager"],
    },
    "Stations": {
        "id": "Stations",
        "icon": "⛽",
        "roles": ["General Manager", "Region Director", "Region Manager"],
    },
    "Map View": {
        "id": "Map View",
        "icon": "🗺️",
        "roles": ["General Manager", "Region Director", "Region Manager"],
    },
    "Employees": {
        "id": "Employees",
        "icon": "👥",
        "roles": ["General Manager"],
    },
    "AI Reports": {
        "id": "AI Reports",
        "icon": "📈",
        "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager"],
    },
    "AI Alerts": {
        "id": "AI Alerts",
        "icon": "🚨",
        "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager"],
    },
    "Audit Log": {
        "id": "Audit Log",
        "icon": "🛡️",
        "roles": ["General Manager"],
    },
    "GM Dashboard": {
        "id": "GM Dashboard",
        "icon": "📊",
        "roles": ["General Manager"],
    },
    "Admin Users": {
        "id": "Admin Users",
        "icon": "👤",
        "roles": ["General Manager"],
    },
    "Settings": {
        "id": "Settings",
        "icon": "⚙️",
        "roles": ["General Manager", "Region Director", "Region Manager", "Gas Station Manager", "Gas Station Supervisor", "Employee"],
    },
    # Help removed from sidebar config per UX request
}


def get_logo_path():
    base_path = Path(__file__).resolve().parents[1]
    logo_file = base_path / "assets" / "OpusLogo.png"
    return str(logo_file) if logo_file.exists() else None


def _status_badge(label: str, status: str, details: str = None):
    palette = {
        "online": ("#e8f8ef", "#157347"),
        "starting": ("#fff8e1", "#856404"),
        "idle": ("#eef6ff", "#0d6efd"),
        "stale": ("#fff3cd", "#856404"),
        "error": ("#fdecea", "#b02a37"),
        "offline": ("#f1f3f5", "#6c757d"),
        "unknown": ("#f1f3f5", "#6c757d"),
    }
    bg, fg = palette.get(status, palette["unknown"])
    suffix = f"<div class='gs-status-detail'>{details}</div>" if details else ""
    return f"""
        <div class="gs-status-card" style="background:{bg};color:{fg};">
            <div class="gs-status-label">{label}</div>
            <div class="gs-status-value">{status.replace('_', ' ').title()}</div>
            {suffix}
        </div>
    """


def _read_status(conn, key):
    row = conn.execute("SELECT value FROM system_settings WHERE key=%s", (key,)).fetchone()
    if not row or not row[0]:
        return {}
    try:
        return json.loads(row[0])
    except Exception:
        return {}


def display_sidebar(conn):
    user_role = st.session_state.get("user_role", "Employee")
    username = st.session_state.get("username", "User")

    with st.sidebar:
        st.markdown(
            """
            <style>
                .gs-sidebar-shell {
                    border: 1px solid rgba(120, 130, 150, 0.18);
                    border-radius: 18px;
                    padding: 1rem;
                    background: linear-gradient(180deg, rgba(255,255,255,0.94), rgba(245,247,252,0.98));
                    box-shadow: 0 14px 42px rgba(15, 23, 42, 0.08);
                }
                .gs-brand {
                    display: flex;
                    gap: 0.9rem;
                    align-items: center;
                    padding: 0.3rem 0 0.9rem 0;
                }
                .gs-brand h2 {
                    margin: 0;
                    font-size: 1.15rem;
                    line-height: 1.1;
                }
                .gs-brand p {
                    margin: 0.18rem 0 0 0;
                    color: #5f6b7a;
                    font-size: 0.82rem;
                }
                .gs-pill {
                    display: inline-block;
                    padding: 0.2rem 0.55rem;
                    border-radius: 999px;
                    background: rgba(13, 110, 253, 0.10);
                    color: #0b5ed7;
                    font-size: 0.74rem;
                    font-weight: 600;
                    letter-spacing: 0.02em;
                }
                .gs-section-title {
                    margin: 0.9rem 0 0.45rem;
                    font-size: 0.8rem;
                    text-transform: uppercase;
                    letter-spacing: 0.08em;
                    color: #6b7280;
                    font-weight: 700;
                }
                .gs-status-grid {
                    display: grid;
                    grid-template-columns: 1fr;
                    gap: 0.55rem;
                }
                .gs-status-card {
                    border-radius: 14px;
                    padding: 0.75rem 0.8rem;
                    border: 1px solid rgba(15, 23, 42, 0.06);
                }
                .gs-status-label {
                    font-size: 0.72rem;
                    text-transform: uppercase;
                    letter-spacing: 0.08em;
                    opacity: 0.8;
                    margin-bottom: 0.2rem;
                }
                .gs-status-value {
                    font-size: 0.92rem;
                    font-weight: 700;
                }
                .gs-status-detail {
                    font-size: 0.74rem;
                    margin-top: 0.2rem;
                    opacity: 0.85;
                    word-break: break-word;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )

        logo_col, title_col = st.columns([0.7, 2.3], vertical_alignment="center")
        with logo_col:
            logo = get_logo_path()
            if logo:
                st.image(logo, width=72)
        with title_col:
            st.markdown("<div class='gs-brand'><div><h2>Gas Station Manager</h2><p>Operational control center</p></div></div>", unsafe_allow_html=True)
            st.markdown(f"<span class='gs-pill'>{user_role}</span>", unsafe_allow_html=True)
            st.caption(f"Signed in as {username}")

        active_page = st.session_state.get("active_page", "Dashboard")
        st.markdown("<div class='gs-section-title'>Workspace</div>", unsafe_allow_html=True)
        st.caption(f"Active page: **{active_page}**")

        # Top-pinned persistent shift controls and timers (always visible)
        def _fmt_delta(delta):
            try:
                total = int(delta.total_seconds())
                if total < 0:
                    return "--:--:--"
                h = total // 3600
                m = (total % 3600) // 60
                s = total % 60
                return f"{h:02d}:{m:02d}:{s:02d}"
            except Exception:
                return "--:--:--"

        st.markdown("<div class='gs-section-title'>My Shift</div>", unsafe_allow_html=True)
        try:
            user_row = _get_current_user(conn)
            if user_row and user_row[4]:
                employee_id = user_row[4]
                active_shift = _current_active_shift(conn, employee_id)
                now = datetime.now()

                # Read persistent break state from active_shift if present
                break_state = None
                if active_shift:
                    clock_in = active_shift[3] or active_shift[1]
                    try:
                        if hasattr(clock_in, "timestamp"):
                            elapsed = now - clock_in
                        else:
                            elapsed = now - datetime.fromisoformat(str(clock_in))
                    except Exception:
                        elapsed = None

                    elapsed_str = _fmt_delta(elapsed) if elapsed else "--:--:--"

                    # Time until scheduled end (if known)
                    scheduled_end = active_shift[2]
                    if scheduled_end:
                        try:
                            if hasattr(scheduled_end, "timestamp"):
                                remaining = scheduled_end - now
                            else:
                                remaining = datetime.fromisoformat(str(scheduled_end)) - now
                        except Exception:
                            remaining = None
                    else:
                        remaining = None

                    st.markdown(f"**Active shift #{active_shift[0]}** — worked: {elapsed_str}")
                    st.caption(f"Time till end: {_fmt_delta(remaining) if remaining else '--:--:--'}")

                    # Determine persistent break values
                    try:
                        bstart = active_shift[7]
                        bend = active_shift[8]
                        bdur = int(active_shift[9]) if active_shift[9] is not None else 15
                        is_on_break = bool(active_shift[10])
                    except Exception:
                        bstart = bend = None
                        bdur = 15
                        is_on_break = False

                    if bstart:
                        try:
                            if hasattr(bstart, "timestamp"):
                                bstart_dt = bstart
                            else:
                                bstart_dt = datetime.fromisoformat(str(bstart))
                        except Exception:
                            bstart_dt = None
                    else:
                        bstart_dt = None

                    if is_on_break and bstart_dt:
                        break_remaining = bstart_dt + pd.Timedelta(minutes=bdur) - now
                    else:
                        break_remaining = None

                    st.caption(f"Break remaining: {_fmt_delta(break_remaining) if break_remaining else '--:--:--'}")

                    bcol1, bcol2 = st.columns([1, 1])
                    with bcol1:
                        if not is_on_break:
                            default_break = 15
                            # try system setting for default break duration
                            try:
                                srow = conn.execute("SELECT value FROM system_settings WHERE key=%s", ("default_break_minutes",)).fetchone()
                                if srow and srow[0]:
                                    default_break = int(srow[0])
                            except Exception:
                                pass
                            if st.button("⏸️ Take Break", key="sidebar_take_break", width="stretch"):
                                _start_break(conn, active_shift[0], duration_minutes=default_break)
                                conn.commit()
                                log_activity(conn, "BREAK_START", f"Employee {employee_id} started break on shift {active_shift[0]}")
                                st.toast("Break started.", icon="✅")
                                st.rerun()
                        else:
                            if st.button("▶️ End Break", key="sidebar_end_break", width="stretch"):
                                _end_break(conn, active_shift[0])
                                conn.commit()
                                log_activity(conn, "BREAK_END", f"Employee {employee_id} ended break on shift {active_shift[0]}")
                                st.toast("Break ended.", icon="✅")
                                st.rerun()
                    with bcol2:
                        if st.button("🛑 Stop Shift", key="sidebar_clock_out", type="primary", width="stretch"):
                            _clock_out_shift(conn, active_shift[0])
                            conn.commit()
                            log_activity(conn, "CLOCK_OUT", f"Employee {employee_id} clocked out of shift {active_shift[0]} (sidebar)")
                            st.toast("Clock-out saved.", icon="✅")
                            st.rerun()
                else:
                    # No active shift: show scheduled or quick clock-in
                    upcoming = _upcoming_scheduled_shift(conn, employee_id)
                    if upcoming:
                        st.markdown(f"**Upcoming shift #{upcoming[0]}** — starts: {upcoming[1]}")
                        if st.button("▶️ Clock In (Scheduled)", key="sidebar_clock_in_scheduled", type="primary", width="stretch"):
                            _start_shift(conn, employee_id, upcoming[3] or user_row[7], shift_id=upcoming[0], scheduled_start=upcoming[1], scheduled_end=upcoming[2], shift_type=upcoming[4] or "standard", notes=upcoming[5])
                            conn.commit()
                            log_activity(conn, "CLOCK_IN", f"Employee {employee_id} clocked into shift {upcoming[0]} (sidebar)")
                            st.toast("Clock-in saved.", icon="🟢")
                            st.rerun()
                    else:
                        st.markdown("No active or scheduled shift.")
                        if st.button("▶️ Clock In", key="sidebar_clock_in", width="stretch"):
                            station_id = user_row[7]
                            shift_id = _start_shift(conn, employee_id, station_id, notes="Clocked in from sidebar")
                            conn.commit()
                            log_activity(conn, "CLOCK_IN", f"Employee {employee_id} clocked into shift {shift_id} (sidebar)")
                            st.toast("Clock-in saved.", icon="🟢")
                            st.rerun()
            else:
                st.caption("Not linked to an employee record.")
        except Exception:
            st.caption("Shift controls unavailable.")

        bot_status = _read_status(conn, "telegram_bot_status")
        ai_status = _read_status(conn, "ai_processing_status")
        alerts_count = 0
        try:
            row = conn.execute("SELECT COUNT(*) FROM ai_alerts WHERE status IN ('new', 'acknowledged')").fetchone()
            alerts_count = row[0] if row else 0
        except Exception:
            pass

        bot_state = bot_status.get("status", "offline")
        if bot_status.get("last_update_ts") and bot_state == "online":
            try:
                age_seconds = time.time() - float(bot_status["last_update_ts"])
                if age_seconds > 90:
                    bot_state = "stale"
            except Exception:
                bot_state = "unknown"

        ai_state = ai_status.get("status", "idle")
        if ai_status.get("last_run_ts") and ai_state == "idle":
            try:
                age_seconds = time.time() - float(ai_status["last_run_ts"])
                if age_seconds > 7200:
                    ai_state = "stale"
            except Exception:
                ai_state = "unknown"

        st.markdown("<div class='gs-section-title'>System Health</div>", unsafe_allow_html=True)
        st.markdown(_status_badge("Telegram Bot", bot_state, bot_status.get("details")), unsafe_allow_html=True)
        st.markdown(_status_badge("AI Worker", ai_state, ai_status.get("details")), unsafe_allow_html=True)
        st.markdown(_status_badge("Open Alerts", "online" if alerts_count else "idle", f"{alerts_count} unresolved"), unsafe_allow_html=True)

        st.markdown("<div class='gs-section-title'>Navigation</div>", unsafe_allow_html=True)

        menu_groups = [
            {"title": "Core", "icon": "🏠", "caption": "Daily overview and support", "pages": ["Role Center", "Shifts"]},
            {"title": "Operations", "icon": "🏢", "caption": "Org structure and facilities", "pages": ["Regions", "Stations", "Employees"]},
            {"title": "AI & Risk", "icon": "🤖", "caption": "Reports, alerts, and executive analytics", "pages": ["AI Reports", "AI Alerts", "GM Dashboard", "Map View"]},
            {"title": "Administration", "icon": "⚙️", "caption": "Users, audit trail, and preferences", "pages": ["Admin Users", "Audit Log", "Settings"]},
        ]

        visible_pages_details = {
            page_id: {"label": label, "icon": page["icon"]}
            for label, page in PAGE_CONFIG.items()
            if user_role in page["roles"]
            for page_id in [page["id"]]
        }
        visible_page_ids = set(visible_pages_details.keys())

        if "active_page" not in st.session_state or st.session_state.active_page not in visible_page_ids:
            st.session_state.active_page = "Dashboard"

        for page_id in ["Dashboard", "Role Center", "Shifts"]:
            if page_id in visible_page_ids:
                details = visible_pages_details[page_id]
                is_active = st.session_state.active_page == page_id
                if st.button(
                    f"{details['icon']} {details['label']}",
                    key=f"sidebar_main_{page_id}",
                    width="stretch",
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state.active_page = page_id
                    st.rerun()

        # Persistent shift controls and timers (always visible when user is linked to an employee)
        st.markdown("<div class='gs-section-title'>Shifts</div>", unsafe_allow_html=True)
        try:
            user_row = _get_current_user(conn)
            if user_row and user_row[4]:
                employee_id = user_row[4]
                active_shift = _current_active_shift(conn, employee_id)
                if active_shift:
                    clock_in = active_shift[3] or active_shift[1]
                    if hasattr(clock_in, "timestamp"):
                        elapsed = datetime.now() - clock_in
                    else:
                        try:
                            elapsed = datetime.now() - datetime.fromisoformat(str(clock_in))
                        except Exception:
                            elapsed = None

                    elapsed_str = (
                        f"{int(elapsed.total_seconds()//3600):02d}:{int((elapsed.total_seconds()%3600)//60):02d}:{int(elapsed.total_seconds()%60):02d}"
                        if elapsed
                        else "--:--:--"
                    )
                    st.markdown(f"**Active shift #{active_shift[0]}** — worked: {elapsed_str}")
                    # Use persistent break fields if present on the active shift
                    try:
                        is_on_break = bool(active_shift[10])
                    except Exception:
                        is_on_break = False

                    if not is_on_break:
                        if st.button("⏸️ Take Break", key="sidebar_take_break_alt", width="stretch"):
                            # use system default if available
                            default_break = 15
                            try:
                                srow = conn.execute("SELECT value FROM system_settings WHERE key=%s", ("default_break_minutes",)).fetchone()
                                if srow and srow[0]:
                                    default_break = int(srow[0])
                            except Exception:
                                pass
                            _start_break(conn, active_shift[0], duration_minutes=default_break)
                            conn.commit()
                            log_activity(conn, "BREAK_START", f"Employee {employee_id} started break (sidebar)")
                            st.toast("Break started.", icon="✅")
                            st.rerun()
                    else:
                        if st.button("▶️ End Break", key="sidebar_end_break_alt", width="stretch"):
                            _end_break(conn, active_shift[0])
                            conn.commit()
                            log_activity(conn, "BREAK_END", f"Employee {employee_id} ended break (sidebar)")
                            st.toast("Break ended.", icon="✅")
                            st.rerun()

                    if st.button("🛑 Clock Out", key="sidebar_clock_out", type="primary", width="stretch"):
                        _clock_out_shift(conn, active_shift[0])
                        conn.commit()
                        log_activity(conn, "CLOCK_OUT", f"Employee {employee_id} clocked out of shift {active_shift[0]}")
                        st.toast("Clock-out saved.", icon="✅")
                        st.rerun()
                else:
                    upcoming = _upcoming_scheduled_shift(conn, employee_id)
                    if upcoming:
                        st.markdown(f"**Upcoming shift #{upcoming[0]}** — starts: {upcoming[1]}")
                        if st.button("▶️ Clock In (Scheduled)", key="sidebar_clock_in_scheduled", type="primary", width="stretch"):
                            _start_shift(conn, employee_id, upcoming[3] or user_row[7], shift_id=upcoming[0], scheduled_start=upcoming[1], scheduled_end=upcoming[2], shift_type=upcoming[4] or "standard", notes=upcoming[5])
                            conn.commit()
                            log_activity(conn, "CLOCK_IN", f"Employee {employee_id} clocked into shift {upcoming[0]}")
                            st.toast("Clock-in saved.", icon="🟢")
                            st.rerun()
                    else:
                        st.markdown("No active or scheduled shift.")
                        if st.button("▶️ Clock In", key="sidebar_clock_in", width="stretch"):
                            station_id = user_row[7]
                            shift_id = _start_shift(conn, employee_id, station_id, notes="Clocked in from sidebar")
                            conn.commit()
                            log_activity(conn, "CLOCK_IN", f"Employee {employee_id} clocked into shift {shift_id}")
                            st.toast("Clock-in saved.", icon="🟢")
                            st.rerun()
            else:
                st.caption("Not linked to an employee record.")
        except Exception:
            st.caption("Shift controls unavailable.")

        for group in menu_groups:
            visible_submenu_pages = [pid for pid in group["pages"] if pid in visible_page_ids]
            if not visible_submenu_pages:
                continue
            is_expander_active = st.session_state.active_page in visible_submenu_pages
            with st.expander(f"{group['icon']} {group['title']}", expanded=is_expander_active):
                st.caption(group["caption"])
                for page_id in visible_submenu_pages:
                    details = visible_pages_details[page_id]
                    is_active = st.session_state.active_page == page_id
                    if st.button(
                        f"{details['icon']} {details['label']}",
                        key=f"sidebar_group_{group['title'].lower().replace(' ', '_')}_{page_id}",
                        width="stretch",
                        type="primary" if is_active else "secondary",
                    ):
                        st.session_state.active_page = page_id
                        st.rerun()

        st.markdown("<div class='gs-section-title'>Actions</div>", unsafe_allow_html=True)
        if st.button("🚪 Logout", width="stretch"):
            logout_user_streamlit(st)
            st.rerun()

        st.markdown("<div class='gs-section-title'>Recent Activity</div>", unsafe_allow_html=True)
        try:
            recent_logs = pd.read_sql_query(
                """
                SELECT user_name, action, timestamp
                FROM activity_logs
                ORDER BY timestamp DESC
                LIMIT 3
                """,
                conn,
            )

            if recent_logs.empty:
                st.caption("No recent activity yet.")
            else:
                for _, row in recent_logs.iterrows():
                    timestamp_value = row["timestamp"]
                    if hasattr(timestamp_value, "strftime"):
                        time_val = timestamp_value.strftime("%H:%M")
                    else:
                        time_val = str(timestamp_value).split(" ")[-1][:5]
                    st.markdown(f"**{time_val}** `{row['user_name']}`  \n*{row['action']}*")
        except Exception:
            st.caption("Activity feed unavailable.")

    return st.session_state.active_page
