from datetime import datetime

import pandas as pd
import streamlit as st

from core.activity_logger import log_activity
from core.database import fetch_df
from pages.shifts import _start_shift
from ui.header import render_page_header


def _fmt_name(name, surname):
    parts = [part for part in [name, surname] if part]
    return " ".join(parts) if parts else "Unknown"


def _scope_filter():
    user_role = st.session_state.get("user_role")
    if user_role == "General Manager":
        return None, ()

    if user_role in ("Region Director", "Region Manager"):
        return "u.region_id = %s", (st.session_state.get("user_region_id"),)
    if user_role in ("Gas Station Manager", "Gas Station Supervisor"):
        return "u.station_id = %s", (st.session_state.get("user_station_id"),)
    return "sub.employee_id = %s", (st.session_state.get("user_id"),)


def _alert_filter():
    user_role = st.session_state.get("user_role")
    if user_role == "General Manager":
        return None, ()

    if user_role in ("Region Director", "Region Manager"):
        return "st.region_id = %s", (st.session_state.get("user_region_id"),)
    if user_role in ("Gas Station Manager", "Gas Station Supervisor"):
        return "st.id = %s", (st.session_state.get("user_station_id"),)
    return "a.station_id = (SELECT station_id FROM users WHERE id = %s)", (
        st.session_state.get("user_id"),
    )


def _render_metric_row(metrics):
    cols = st.columns(len(metrics))
    for col, metric in zip(cols, metrics):
        with col:
            st.metric(metric["label"], metric["value"], metric.get("delta"))


def _render_shift_panel(conn):
    st.subheader("Shift Tracking")

    employee_id = st.session_state.get("user_id")
    active_shift = conn.execute(
        """
        SELECT id, shift_started_at, status
        FROM employee_shifts
        WHERE employee_id = %s AND shift_ended_at IS NULL
        ORDER BY shift_started_at DESC
        LIMIT 1
        """,
        (employee_id,),
    ).fetchone()

    if active_shift:
        started_at = active_shift[1]
        duration = datetime.utcnow() - started_at.replace(tzinfo=None)
        hours = round(duration.total_seconds() / 3600, 2)
        st.success(
            f"Active shift started at **{started_at}** and has been running for **{hours} hours**."
        )
        if st.button("End My Shift", key="role_center_end_shift", width="stretch"):
            conn.execute(
                """
                UPDATE employee_shifts
                SET shift_ended_at = CURRENT_TIMESTAMP,
                    status = 'closed',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (active_shift[0],),
            )
            conn.commit()
            log_activity(
                conn,
                "END_SHIFT",
                f"Employee {employee_id} ended shift {active_shift[0]}",
            )
            st.toast("Shift ended.", icon="✅")
            st.rerun()
    else:
        st.warning("No active shift is currently running.")
        try:
            srow = conn.execute(
                "SELECT value FROM system_settings WHERE key=%s",
                ("default_break_minutes",),
            ).fetchone()
            rc_default = int(srow[0]) if srow and srow[0] else 15
        except Exception:
            rc_default = 15

        br = st.number_input(
            "Break (min)",
            min_value=1,
            max_value=240,
            value=rc_default,
            key="role_center_break_override",
        )
        if st.button(
            "Start My Shift",
            key="role_center_start_shift",
            width="stretch",
            type="primary",
        ):
            station_id = st.session_state.get("user_station_id")
            shift_id = _start_shift(
                conn,
                employee_id,
                station_id,
                notes="Started from role center",
                break_duration_minutes=int(br),
            )
            conn.commit()
            log_activity(
                conn,
                "START_SHIFT",
                f"Employee {employee_id} started a shift {shift_id}",
            )
            st.toast("Shift started.", icon="🟢")
            st.rerun()

    shift_history = fetch_df(
        conn,
        """
        SELECT shift_started_at, shift_ended_at, status
        FROM employee_shifts
        WHERE employee_id = %s
        ORDER BY shift_started_at DESC
        LIMIT 5
        """,
        (employee_id,),
    )
    if not shift_history.empty:
        st.markdown("**Recent shifts**")
        st.dataframe(shift_history, width="stretch", hide_index=True)


def _render_scope_activity(conn, scope_where, scope_params):
    st.subheader("Scope Activity")
    user_role = st.session_state.get("user_role")

    if user_role == "General Manager":
        metrics = [
            {
                "label": "Stations",
                "value": conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0],
            },
            {
                "label": "Users",
                "value": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            },
            {
                "label": "Total Reports",
                "value": conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0],
            },
            {
                "label": "Open Risks",
                "value": conn.execute(
                    "SELECT COUNT(*) FROM ai_alerts WHERE status IN ('new','acknowledged')"
                ).fetchone()[0],
            },
        ]
        _render_metric_row(metrics)

    elif user_role in ("Region Director", "Region Manager"):
        region_id = st.session_state.get("user_region_id")
        # ... rest of the logic using session state directly ...

    st.markdown("#### Recent Reports")
    reports_df = fetch_df(
        conn,
        f"""
        SELECT sub.id, sub.timestamp, st.name AS station, e.name || ' ' || COALESCE(e.surname, '') AS employee,
               sub.processed,
               COALESCE((sub.data_json->>'safety_score')::text, 'N/A') AS safety_score, -- These are from submissions.data_json
               COALESCE((sub.data_json->>'merchandising_score')::text, 'N/A') AS merchandising_score, -- These are from submissions.data_json
               COALESCE((sub.data_json->>'staff_score')::text, 'N/A') AS staff_score -- These are from submissions.data_json
        FROM submissions sub
        LEFT JOIN users e ON e.id = sub.employee_id
        LEFT JOIN stations st ON st.id = sub.station_id
        {"WHERE " + scope_where if scope_where else ""}
        ORDER BY sub.timestamp DESC
        LIMIT 8
        """,
        scope_params,
    )
    if reports_df.empty:
        st.info("No reports found for this scope yet.")
    else:
        st.dataframe(reports_df, width="stretch", hide_index=True)

    st.markdown("#### Open Risks")
    alert_where, alert_params = _alert_filter(user_role, employee_row)
    alerts_sql = """
        SELECT a.id, a.created_at, st.name AS station, a.severity, a.message, a.status
        FROM ai_alerts a
        LEFT JOIN stations st ON st.id = a.station_id
    """
    alerts_params = tuple()
    where_clauses = ["a.status IN ('new', 'acknowledged')"]
    if alert_where:
        where_clauses.append(alert_where)
        alerts_params = alert_params
    if where_clauses:
        alerts_sql += " WHERE " + " AND ".join(where_clauses)
    alerts_sql += " ORDER BY a.created_at DESC LIMIT 8"

    alerts_df = fetch_df(conn, alerts_sql, alerts_params)
    if alerts_df.empty:
        st.success("No unresolved alerts in this scope.")
    else:
        st.dataframe(alerts_df, width="stretch", hide_index=True)


def render(conn):
    render_page_header("🧭 Personal Dashboard")

    user_role = st.session_state.get("user_role", "Employee")

    st.markdown(
        "This page changes with your role. General Managers see the whole network, while employees see their own shift, submissions, and risk history."
    )

    st.caption(
        f"Logged in as **{st.session_state.get('user_name_full')}** | Role: **{user_role}**"
    )

    if st.session_state.get("user_id"):
        st.markdown("### Personal Profile")
        profile_cols = st.columns(4)
        profile_cols[0].metric("Employee", st.session_state.get("user_name_full"))
        profile_cols[1].metric(
            "Station ID", st.session_state.get("user_station_id") or "N/A"
        )
        profile_cols[2].metric(
            "Region ID", st.session_state.get("user_region_id") or "N/A"
        )
        profile_cols[3].metric(
            "Telegram",
            "Linked" if st.session_state.get("user_telegram_chat_id") else "Not linked",
        )

    st.divider()
    _render_shift_panel(conn)

    st.divider()
    scope_where, scope_params = _scope_filter()
    _render_scope_activity(conn, scope_where, scope_params)
