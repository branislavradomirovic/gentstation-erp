from datetime import datetime, date, time as dt_time

import pandas as pd
import streamlit as st

from core.activity_logger import log_activity
from core.database import fetch_df
from ui.header import render_page_header


def _fmt_name(name, surname):
    parts = [part for part in [name, surname] if part]
    return " ".join(parts) if parts else "Unknown"


def _get_current_user(conn):
    if "user_id" not in st.session_state:
        return None
    return (
        st.session_state.user_id,
        st.session_state.username,
        st.session_state.get("email"),
        st.session_state.user_role,
        st.session_state.user_id,
        st.session_state.get("name"),
        st.session_state.get("surname"),
        st.session_state.get("user_station_id"),
        st.session_state.get("user_region_id"),
    )


def _scope_clause(user_role, employee_row):
    if user_role == "General Manager":
        return "", ()
    if not employee_row:
        return "es.employee_id IS NULL", ()
    if user_role in ("Region Director", "Region Manager"):
        return "u.region_id = %s", (employee_row[8],)  # employee_row[8] is u.region_id
    if user_role in ("Gas Station Manager", "Gas Station Supervisor"):
        return "es.station_id = %s", (employee_row[7],)
    return "es.employee_id = %s", (employee_row[4],)


def _employee_options(conn, user_role, employee_row):
    if user_role == "General Manager":
        sql = """
            SELECT u.id, u.name || ' ' || COALESCE(u.surname, '') AS fullname, s.name AS station_name
            FROM users u
            LEFT JOIN stations s ON s.id = u.station_id
            ORDER BY e.name, e.surname
        """
        return fetch_df(conn, sql)

    if not employee_row:
        return pd.DataFrame(columns=["id", "fullname", "station_name"])

    if user_role in ("Region Director", "Region Manager"):
        return fetch_df(
            conn,
            """
            SELECT u.id, u.name || ' ' || COALESCE(u.surname, '') AS fullname, s.name AS station_name
            FROM users u
            LEFT JOIN stations s ON s.id = u.station_id
            WHERE u.region_id = %s
            ORDER BY e.name, e.surname
            """,
            (employee_row[8],),
        )

    if user_role in ("Gas Station Manager", "Gas Station Supervisor"):
        return fetch_df(
            conn,
            """
            SELECT u.id, u.name || ' ' || COALESCE(u.surname, '') AS fullname, s.name AS station_name
            FROM users u
            LEFT JOIN stations s ON s.id = u.station_id
            WHERE u.station_id = %s
            ORDER BY e.name, e.surname
            """,
            (employee_row[7],),
        )

    return fetch_df(
        conn,
        """
            SELECT u.id, u.name || ' ' || COALESCE(u.surname, '') AS fullname, s.name AS station_name
            FROM users u
            LEFT JOIN stations s ON s.id = u.station_id
            WHERE u.id = %s
        """,
        (employee_row[4],),
    )


def _station_options(conn, user_role, employee_row):
    if user_role == "General Manager":
        return fetch_df(conn, "SELECT id, name FROM stations ORDER BY name")

    if not employee_row:
        return pd.DataFrame(columns=["id", "name"])

    if user_role in ("Region Director", "Region Manager"):
        return fetch_df(
            conn,
            "SELECT id, name FROM stations WHERE region_id = %s ORDER BY name",
            (employee_row[8],),
        )

    if user_role in ("Gas Station Manager", "Gas Station Supervisor"):
        return fetch_df(
            conn,
            "SELECT id, name FROM stations WHERE id = %s ORDER BY name",
            (employee_row[7],),
        )

    return fetch_df(
        conn,
        "SELECT id, name FROM stations WHERE id = %s ORDER BY name",
        (employee_row[7],),
    )


def _load_shift_data(conn, user_role, employee_row):
    scope_where, scope_params = _scope_clause(user_role, employee_row)
    query = """
        SELECT es.id,
               es.employee_id,
               e.name || ' ' || COALESCE(e.surname, '') AS employee_name,
               es.station_id,
               st.name AS station_name,
               es.shift_type,
               es.scheduled_start_at,
               es.scheduled_end_at,
               es.clock_in_at,
               es.clock_out_at,
               es.status,
               es.notes
        FROM employee_shifts es
        LEFT JOIN users e ON e.id = es.employee_id
        LEFT JOIN stations st ON st.id = es.station_id
    """
    if scope_where:
        query += f" WHERE {scope_where}"
    query += " ORDER BY COALESCE(es.scheduled_start_at, es.shift_started_at) DESC, es.id DESC"
    return fetch_df(conn, query, scope_params)


def _current_active_shift(conn, employee_id):
    return conn.execute(
        """
                SELECT id, scheduled_start_at, scheduled_end_at, clock_in_at, clock_out_at, status, station_id,
                             break_started_at, break_ended_at, break_duration_minutes, is_on_break
        FROM employee_shifts
        WHERE employee_id = %s
          AND clock_in_at IS NOT NULL
          AND clock_out_at IS NULL
          AND status = 'active'
        ORDER BY COALESCE(clock_in_at, scheduled_start_at, shift_started_at) DESC
        LIMIT 1
        """,
        (employee_id,),
    ).fetchone()


def _upcoming_scheduled_shift(conn, employee_id):
    return conn.execute(
        """
        SELECT id, scheduled_start_at, scheduled_end_at, station_id, shift_type, notes
        FROM employee_shifts
        WHERE employee_id = %s
          AND clock_in_at IS NULL
          AND status = 'scheduled'
        ORDER BY scheduled_start_at ASC, id ASC
        LIMIT 1
        """,
        (employee_id,),
    ).fetchone()


def _start_shift(
    conn,
    employee_id,
    station_id,
    shift_id=None,
    scheduled_start=None,
    scheduled_end=None,
    shift_type="standard",
    notes=None,
    break_duration_minutes=None,
):
    if shift_id:
        conn.execute(
            """
            UPDATE employee_shifts
            SET clock_in_at = COALESCE(clock_in_at, CURRENT_TIMESTAMP),
                shift_started_at = COALESCE(shift_started_at, CURRENT_TIMESTAMP),
                station_id = COALESCE(station_id, %s),
                scheduled_start_at = COALESCE(scheduled_start_at, %s),
                scheduled_end_at = COALESCE(scheduled_end_at, %s),
                shift_type = COALESCE(shift_type, %s),
                break_duration_minutes = COALESCE(%s, break_duration_minutes),
                status = 'active',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (
                station_id,
                scheduled_start,
                scheduled_end,
                shift_type,
                break_duration_minutes,
                shift_id,
            ),
        )
        return shift_id

    cur = conn.execute(
        """
        INSERT INTO employee_shifts (
            employee_id, station_id, shift_type, scheduled_start_at, scheduled_end_at,
            clock_in_at, shift_started_at, status, notes, break_duration_minutes
        ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'active', %s, %s)
        RETURNING id
        """,
        (
            employee_id,
            station_id,
            shift_type,
            scheduled_start,
            scheduled_end,
            notes,
            break_duration_minutes,
        ),
    )
    return cur.fetchone()[0]


def _create_scheduled_shift(
    conn,
    employee_id,
    station_id,
    scheduled_start,
    scheduled_end,
    shift_type="standard",
    notes=None,
    break_duration_minutes=None,
):
    cur = conn.execute(
        """
        INSERT INTO employee_shifts (
            employee_id, station_id, shift_type, scheduled_start_at, scheduled_end_at,
            shift_started_at, status, notes, break_duration_minutes
        ) VALUES (%s, %s, %s, %s, %s, %s, 'scheduled', %s, %s)
        RETURNING id
        """,
        (
            employee_id,
            station_id,
            shift_type,
            scheduled_start,
            scheduled_end,
            scheduled_start,
            notes,
            break_duration_minutes,
        ),
    )
    return cur.fetchone()[0]


def _clock_out_shift(conn, shift_id):
    conn.execute(
        """
        UPDATE employee_shifts
        SET clock_out_at = COALESCE(clock_out_at, CURRENT_TIMESTAMP),
            shift_ended_at = COALESCE(shift_ended_at, CURRENT_TIMESTAMP),
            status = 'completed',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (shift_id,),
    )


def _start_break(conn, shift_id, duration_minutes=15):
    """Mark a break start for a shift and set duration."""
    conn.execute(
        """
        UPDATE employee_shifts
        SET break_started_at = COALESCE(break_started_at, CURRENT_TIMESTAMP),
            break_duration_minutes = COALESCE(%s, break_duration_minutes),
            is_on_break = TRUE,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (duration_minutes, shift_id),
    )


def _end_break(conn, shift_id):
    """Mark a break end for a shift."""
    conn.execute(
        """
        UPDATE employee_shifts
        SET break_ended_at = COALESCE(break_ended_at, CURRENT_TIMESTAMP),
            is_on_break = FALSE,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (shift_id,),
    )


def render(conn):
    render_page_header("🕒 Shifts & Attendance")

    user_role = st.session_state.get("user_role", "Employee")
    user_row = _get_current_user(conn)
    employee_row = user_row
    focus_employee_id = st.session_state.pop("target_shift_employee_id", None)
    focus_station_id = st.session_state.pop("target_shift_station_id", None)

    st.markdown(
        "Use this page to plan station coverage, assign people to shifts, and clock in or out from one place."
    )

    if user_row:
        st.caption(
            f"Signed in as **{_fmt_name(user_row[5], user_row[6])}** | Role: **{user_role}**"
        )

    today = date.today()
    shift_df = _load_shift_data(conn, user_role, employee_row)
    if (
        focus_employee_id is not None
        and not shift_df.empty
        and "employee_id" in shift_df
    ):
        shift_df = shift_df[shift_df["employee_id"] == focus_employee_id]
    elif (
        focus_station_id is not None and not shift_df.empty and "station_id" in shift_df
    ):
        shift_df = shift_df[shift_df["station_id"] == focus_station_id]

    total_shifts = len(shift_df)
    active_shifts = (
        int((shift_df["status"] == "active").sum())
        if not shift_df.empty and "status" in shift_df
        else 0
    )
    completed_shifts = (
        int((shift_df["status"] == "completed").sum())
        if not shift_df.empty and "status" in shift_df
        else 0
    )
    scheduled_today = 0
    if not shift_df.empty and "scheduled_start_at" in shift_df:
        scheduled_today = int(
            pd.to_datetime(shift_df["scheduled_start_at"], errors="coerce")
            .dt.date.eq(today)
            .sum()
        )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Shifts Visible", total_shifts)
    metric_cols[1].metric("Scheduled Today", scheduled_today)
    metric_cols[2].metric("Active", active_shifts)
    metric_cols[3].metric("Completed", completed_shifts)

    st.divider()

    if employee_row and employee_row[4]:
        st.subheader("My Clock")
        active_shift = _current_active_shift(conn, employee_row[4])
        if active_shift:
            st.success(
                f"Active shift #{active_shift[0]} started at {active_shift[3] or active_shift[1]} "
                f"for station {active_shift[6] or 'N/A'}."
            )
            # show break status and controls
            try:
                is_on_break = bool(active_shift[10])
                bstart = active_shift[7]
                bdur = int(active_shift[9]) if active_shift[9] is not None else 15
            except Exception:
                is_on_break = False
                bstart = None
                bdur = 15

            if bstart and is_on_break:
                try:
                    bstart_dt = (
                        bstart
                        if hasattr(bstart, "timestamp")
                        else datetime.fromisoformat(str(bstart))
                    )
                    remaining = bstart_dt + pd.Timedelta(minutes=bdur) - datetime.now()
                except Exception:
                    remaining = None
            else:
                remaining = None

            st.caption(f"Break remaining: {remaining if remaining else '--:--:--'}")

            col_a, col_b = st.columns([1, 1])
            with col_a:
                if not is_on_break:
                    if st.button(
                        "Take Break", key="take_break_my_shift", width="stretch"
                    ):
                        # use DB-persisted break
                        _start_break(conn, active_shift[0], duration_minutes=bdur)
                        conn.commit()
                        log_activity(
                            conn,
                            "BREAK_START",
                            f"Employee {employee_row[4]} started break on shift {active_shift[0]}",
                        )
                        st.toast("Break started.", icon="✅")
                        st.rerun()
                else:
                    if st.button(
                        "End Break", key="end_break_my_shift", width="stretch"
                    ):
                        _end_break(conn, active_shift[0])
                        conn.commit()
                        log_activity(
                            conn,
                            "BREAK_END",
                            f"Employee {employee_row[4]} ended break on shift {active_shift[0]}",
                        )
                        st.toast("Break ended.", icon="✅")
                        st.rerun()
            with col_b:
                if st.button(
                    "Clock Out",
                    key="clock_out_my_shift",
                    type="primary",
                    width="stretch",
                ):
                    _clock_out_shift(conn, active_shift[0])
                    conn.commit()
                    log_activity(
                        conn,
                        "CLOCK_OUT",
                        f"Employee {employee_row[4]} clocked out of shift {active_shift[0]}",
                    )
                    st.toast("Clock-out saved.", icon="✅")
                    st.rerun()
        else:
            scheduled_shift = _upcoming_scheduled_shift(conn, employee_row[4])
            if scheduled_shift:
                st.info(
                    f"Upcoming shift #{scheduled_shift[0]} is scheduled for **{scheduled_shift[1]}** at station **{scheduled_shift[3] or 'N/A'}**."
                )
                if st.button(
                    "Clock In",
                    key="clock_in_scheduled_shift",
                    type="primary",
                    width="stretch",
                ):
                    _start_shift(
                        conn,
                        employee_row[4],
                        scheduled_shift[3] or employee_row[7],
                        shift_id=scheduled_shift[0],
                        scheduled_start=scheduled_shift[1],
                        scheduled_end=scheduled_shift[2],
                        shift_type=scheduled_shift[4] or "standard",
                        notes=scheduled_shift[5],
                    )
                    conn.commit()
                    log_activity(
                        conn,
                        "CLOCK_IN",
                        f"Employee {employee_row[4]} clocked into shift {scheduled_shift[0]}",
                    )
                    st.toast("Clock-in saved.", icon="🟢")
                    st.rerun()
            else:
                st.info("No active or scheduled shift is running right now.")
                if st.button(
                    "Clock In", key="clock_in_my_shift", type="primary", width="stretch"
                ):
                    station_id = employee_row[7]
                    shift_id = _start_shift(
                        conn,
                        employee_row[4],
                        station_id,
                        notes="Clocked in from personal view",
                    )
                    conn.commit()
                    log_activity(
                        conn,
                        "CLOCK_IN",
                        f"Employee {employee_row[4]} clocked into shift {shift_id}",
                    )
                    st.toast("Clock-in saved.", icon="🟢")
                    st.rerun()

        my_shifts = fetch_df(
            conn,
            """
            SELECT id, station_id, shift_type, scheduled_start_at, scheduled_end_at,
                   clock_in_at, clock_out_at, status, notes
            FROM employee_shifts
            WHERE employee_id = %s
            ORDER BY COALESCE(scheduled_start_at, shift_started_at) DESC
            LIMIT 10
            """,
            (employee_row[4],),
        )
        if not my_shifts.empty:
            st.dataframe(my_shifts, width="stretch", hide_index=True)

    st.divider()

    if user_role == "General Manager" or user_role in (
        "Region Director",
        "Region Manager",
        "Gas Station Manager",
        "Gas Station Supervisor",
    ):
        st.subheader("Schedule a Shift")
        employees_df = _employee_options(conn, user_role, employee_row)
        stations_df = _station_options(conn, user_role, employee_row)

        if employees_df.empty or stations_df.empty:
            st.info("No employees or stations available for the current scope.")
        else:
            with st.form("schedule_shift_form", clear_on_submit=True):
                col_a, col_b = st.columns(2)
                employee_ids = employees_df["id"].tolist()
                station_ids = stations_df["id"].tolist()
                employee_index = (
                    employee_ids.index(focus_employee_id)
                    if focus_employee_id in employee_ids
                    else 0
                )
                station_index = (
                    station_ids.index(focus_station_id)
                    if focus_station_id in station_ids
                    else 0
                )

                employee_label = col_a.selectbox(
                    "Employee",
                    options=employee_ids,
                    index=employee_index,
                    format_func=lambda x: employees_df.loc[
                        employees_df["id"] == x, "fullname"
                    ].values[0],
                )
                station_label = col_b.selectbox(
                    "Station",
                    options=station_ids,
                    index=station_index,
                    format_func=lambda x: stations_df.loc[
                        stations_df["id"] == x, "name"
                    ].values[0],
                )

                col_c, col_d = st.columns(2)
                shift_date = col_c.date_input("Shift date", value=today)
                start_time = col_d.time_input("Start time", value=dt_time(8, 0))
                col_e, col_f = st.columns(2)
                end_time = col_e.time_input("End time", value=dt_time(16, 0))
                shift_type = col_f.selectbox(
                    "Shift type",
                    ["standard", "morning", "afternoon", "night", "custom"],
                )
                # fetch system default for break duration if present
                try:
                    srow = conn.execute(
                        "SELECT value FROM system_settings WHERE key=%s",
                        ("default_break_minutes",),
                    ).fetchone()
                    default_break = int(srow[0]) if srow and srow[0] else 15
                except Exception:
                    default_break = 15

                break_minutes = st.number_input(
                    "Break duration (minutes)",
                    min_value=1,
                    max_value=240,
                    value=default_break,
                )
                notes = st.text_area(
                    "Notes",
                    placeholder="Optional handover notes, coverage instructions, or special conditions.",
                )

                if st.form_submit_button("Create Shift", width="stretch"):
                    scheduled_start = datetime.combine(shift_date, start_time)
                    scheduled_end = datetime.combine(shift_date, end_time)
                    if scheduled_end <= scheduled_start:
                        st.error("End time must be after start time.")
                    else:
                        shift_id = _create_scheduled_shift(
                            conn,
                            int(employee_label),
                            int(station_label),
                            scheduled_start=scheduled_start,
                            scheduled_end=scheduled_end,
                            shift_type=shift_type,
                            notes=notes.strip() or None,
                            break_duration_minutes=int(break_minutes),
                        )
                        conn.commit()
                        log_activity(
                            conn,
                            "CREATE_SHIFT",
                            f"Created shift {shift_id} for employee {employee_label}",
                        )
                        st.success("Shift created successfully.")
                        st.rerun()

    st.divider()
    st.subheader("Shift Register")
    if shift_df.empty:
        st.info("No shifts found for the current scope.")
    else:
        st.dataframe(shift_df, width="stretch", hide_index=True)
