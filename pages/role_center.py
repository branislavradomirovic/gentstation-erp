from datetime import datetime

import pandas as pd
import streamlit as st

from core.activity_logger import log_activity
from ui.header import render_page_header


def fetch_df(conn, query, params=None):
    cur = conn.cursor()
    cur.execute(query, params or ())
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description] if cur.description else []
    return pd.DataFrame(rows, columns=columns)


def _get_current_user(conn):
    user_id = st.session_state.get("user_id")
    if not user_id:
        return None
    row = conn.execute(
        """
        SELECT u.id, u.username, u.email, u.role,
               e.id AS employee_id, e.name, e.surname, e.station_id, e.region_id, e.telegram_chat_id
        FROM users u
        LEFT JOIN employees e
          ON e.email = COALESCE(u.email, u.username)
        WHERE u.id = %s
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    return row


def _fmt_name(name, surname):
    parts = [part for part in [name, surname] if part]
    return " ".join(parts) if parts else "Unknown"


def _scope_filter(user_role, employee_row):
    if user_role == "General Manager":
        return None, ()
    if not employee_row:
        return None, ()

    if user_role in ("Region Director", "Region Manager"):
        return "e.region_id = %s", (employee_row[8],)
    if user_role in ("Gas Station Manager", "Gas Station Supervisor"):
        return "e.station_id = %s", (employee_row[7],)
    return "sub.employee_id = %s", (employee_row[4],)


def _alert_filter(user_role, employee_row):
    if user_role == "General Manager":
        return None, ()
    if not employee_row:
        return None, ()

    if user_role in ("Region Director", "Region Manager"):
        return "st.region_id = %s", (employee_row[8],)
    if user_role in ("Gas Station Manager", "Gas Station Supervisor"):
        return "st.id = %s", (employee_row[7],)
    return "a.station_id = (SELECT station_id FROM employees WHERE id = %s)", (employee_row[4],)


def _render_metric_row(metrics):
    cols = st.columns(len(metrics))
    for col, metric in zip(cols, metrics):
        with col:
            st.metric(metric["label"], metric["value"], metric.get("delta"))


def _render_shift_panel(conn, employee_row):
    st.subheader("Shift Tracking")
    if not employee_row:
        st.info("No linked employee record was found for this user, so personal shift tracking is unavailable.")
        return

    employee_id = employee_row[4]
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
        st.success(f"Active shift started at **{started_at}** and has been running for **{hours} hours**.")
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
            log_activity(conn, "END_SHIFT", f"Employee {employee_id} ended shift {active_shift[0]}")
            st.toast("Shift ended.", icon="✅")
            st.rerun()
    else:
        st.warning("No active shift is currently running.")
        if st.button("Start My Shift", key="role_center_start_shift", width="stretch", type="primary"):
            conn.execute(
                """
                INSERT INTO employee_shifts (employee_id, shift_started_at, status)
                VALUES (%s, CURRENT_TIMESTAMP, 'active')
                """,
                (employee_id,),
            )
            conn.commit()
            log_activity(conn, "START_SHIFT", f"Employee {employee_id} started a shift")
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


def _render_scope_activity(conn, scope_where, scope_params, user_role, employee_row):
    st.subheader("Scope Activity")

    if user_role == "General Manager":
        metrics = [
            {"label": "Employees", "value": conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]},
            {"label": "Stations", "value": conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]},
            {"label": "Reports", "value": conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]},
            {"label": "Open Alerts", "value": conn.execute("SELECT COUNT(*) FROM ai_alerts WHERE status IN ('new','acknowledged')").fetchone()[0]},
        ]
        _render_metric_row(metrics)
    else:
        if not employee_row:
            st.info("No employee context is available for this account.")
            return

        if user_role in ("Region Director", "Region Manager"):
            region_id = employee_row[8]
            metrics = [
                {"label": "Region ID", "value": region_id or "N/A"},
                {"label": "Reports", "value": conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM submissions sub
                    JOIN employees e ON e.id = sub.employee_id
                    WHERE e.region_id = %s
                    """,
                    (region_id,),
                ).fetchone()[0]},
                {"label": "Stations", "value": conn.execute("SELECT COUNT(*) FROM stations WHERE region_id = %s", (region_id,)).fetchone()[0]},
                {"label": "Open Alerts", "value": conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM ai_alerts a
                    JOIN stations st ON st.id = a.station_id
                    WHERE st.region_id = %s AND a.status IN ('new','acknowledged')
                    """,
                    (region_id,),
                ).fetchone()[0]},
            ]
            _render_metric_row(metrics)
        elif user_role in ("Gas Station Manager", "Gas Station Supervisor"):
            station_id = employee_row[7]
            metrics = [
                {"label": "Station ID", "value": station_id or "N/A"},
                {"label": "Reports", "value": conn.execute(
                    "SELECT COUNT(*) FROM submissions WHERE station_id = %s",
                    (station_id,),
                ).fetchone()[0]},
                {"label": "Employees", "value": conn.execute(
                    "SELECT COUNT(*) FROM employees WHERE station_id = %s",
                    (station_id,),
                ).fetchone()[0]},
                {"label": "Open Alerts", "value": conn.execute(
                    "SELECT COUNT(*) FROM ai_alerts WHERE station_id = %s AND status IN ('new','acknowledged')",
                    (station_id,),
                ).fetchone()[0]},
            ]
            _render_metric_row(metrics)
        else:
            employee_id = employee_row[4]
            station_id = employee_row[7]
            personal_reports = conn.execute(
                "SELECT COUNT(*) FROM submissions WHERE employee_id = %s",
                (employee_id,),
            ).fetchone()[0]
            shift_reports = 0
            active_shift = conn.execute(
                """
                SELECT shift_started_at
                FROM employee_shifts
                WHERE employee_id = %s AND shift_ended_at IS NULL
                ORDER BY shift_started_at DESC
                LIMIT 1
                """,
                (employee_id,),
            ).fetchone()
            if active_shift:
                shift_reports = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM submissions
                    WHERE employee_id = %s AND timestamp >= %s
                    """,
                    (employee_id, active_shift[0]),
                ).fetchone()[0]

            risk_count = 0
            if station_id:
                risk_count = conn.execute(
                    "SELECT COUNT(*) FROM ai_alerts WHERE station_id = %s AND status IN ('new','acknowledged')",
                    (station_id,),
                ).fetchone()[0]

            metrics = [
                {"label": "My Reports", "value": personal_reports},
                {"label": "This Shift", "value": shift_reports},
                {"label": "Open Risks", "value": risk_count},
                {"label": "Station ID", "value": station_id or "N/A"},
                {"label": "Employee ID", "value": employee_id},
            ]
            _render_metric_row(metrics)

    st.markdown("#### Recent Reports")
    reports_df = fetch_df(
        conn,
        f"""
        SELECT sub.id, sub.timestamp, st.name AS station, e.name || ' ' || COALESCE(e.surname, '') AS employee,
               sub.processed,
               COALESCE((sub.data_json->>'safety_score')::text, 'N/A') AS safety_score,
               COALESCE((sub.data_json->>'merchandising_score')::text, 'N/A') AS merchandising_score,
               COALESCE((sub.data_json->>'staff_score')::text, 'N/A') AS staff_score
        FROM submissions sub
        LEFT JOIN employees e ON e.id = sub.employee_id
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
    render_page_header("🧭 Role Center")

    user_role = st.session_state.get("user_role", "Employee")
    user_row = _get_current_user(conn)
    employee_row = user_row

    st.markdown(
        "This page changes with your role. General Managers see the whole network, while employees see their own shift, submissions, and risk history."
    )

    if user_row:
        full_name = _fmt_name(user_row[5], user_row[6])
        st.caption(f"Logged in as **{full_name}** | Role: **{user_role}**")

    if employee_row and employee_row[4]:
        st.markdown("### Personal Profile")
        profile_cols = st.columns(4)
        profile_cols[0].metric("Employee", _fmt_name(employee_row[5], employee_row[6]))
        profile_cols[1].metric("Station ID", employee_row[7] or "N/A")
        profile_cols[2].metric("Region ID", employee_row[8] or "N/A")
        profile_cols[3].metric("Telegram", "Linked" if employee_row[9] else "Not linked")
    elif user_role == "General Manager":
        st.info("General Manager view has full access to network-wide role data.")
    else:
        st.warning("No linked employee record was found for this account.")

    st.divider()
    _render_shift_panel(conn, employee_row)

    st.divider()
    scope_where, scope_params = _scope_filter(user_role, employee_row)
    _render_scope_activity(conn, scope_where, scope_params, user_role, employee_row)
