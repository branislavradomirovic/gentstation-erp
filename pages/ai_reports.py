# gentstation_opus/pages/ai_reports.py
import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from ui.header import render_page_header
from core.database import get_session
from core.models import Station
from core.activity_logger import log_activity  # Keep this import
from ai_engine.risk_engine import compute_station_risk_from_metrics
from core.report_scope import get_scope_filter_clause

QUEUE_STALLED_AFTER_MINUTES = 10


def _ensure_dict(payload):
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except Exception:
        return {}


def _resolve_column(df: pd.DataFrame, *candidates: str):
    """Return the first matching column name (case-insensitive), else None."""
    if df is None or df.empty:
        return None
    direct = set(df.columns)
    for name in candidates:
        if name in direct:
            return name
    lowered = {str(col).lower(): col for col in df.columns}
    for name in candidates:
        col = lowered.get(str(name).lower())
        if col is not None:
            return col
    return None


def _risk_band(risk_score: float) -> str:
    if risk_score >= 70:
        return "Visok"
    if risk_score >= 40:
        return "Srednji"
    return "Nizak"


def _derive_summary(payload: dict) -> str:
    summary = str(payload.get("summary", "") or "").strip()
    if summary and summary not in {"No summary provided.", "Sažetak nije dostupan."}:
        return summary

    hazards = payload.get("hazards") or []
    stock_issues = payload.get("stock_issues") or []
    risk = float(payload.get("overall_risk_score") or compute_station_risk_from_metrics(payload))
    if hazards:
        return f"Ukupan rizik iznosi {risk:.1f}/100. Prioritetni problem: {hazards[0]}."
    if stock_issues:
        return f"Ukupan rizik iznosi {risk:.1f}/100. Glavni komercijalni problem: {stock_issues[0]}."
    return f"Ukupan rizik iznosi {risk:.1f}/100. Snimak zahteva dodatnu menadžersku proveru jer AI sažetak nije bio potpun."


def _derive_improvements(payload: dict):
    existing = payload.get("improvement_actions") or []
    if isinstance(existing, list) and existing:
        return [str(item).strip() for item in existing if str(item).strip()][:3]

    actions = []
    score_map = [
        ("safety_score", "Otkloni vidljive bezbednosne rizike i proveri usklađenost na platou."),
        ("cleanliness_score", "Sprovedi ciljano čišćenje svih zona koje su vidljive kupcima."),
        ("staff_score", "Usmeri tim u smeni na disciplinu rada, spremnost i nivo usluge."),
        ("merchandising_score", "Doteraj rafove i ispravi low-stock ili promo propuste."),
    ]
    for key, message in score_map:
        try:
            if float(payload.get(key, 5) or 5) <= 7:
                actions.append(message)
        except Exception:
            actions.append(message)
    for field, prefix in (("hazards", "Fix the top hazard: "), ("stock_issues", "Resolve the most visible stock issue: ")):
        values = payload.get(field) or []
        if values:
            localized_prefix = "Prvo otkloni prijavljeni rizik: " if field == "hazards" else "Reši najuočljiviji stock problem: "
            actions.append(localized_prefix + str(values[0]).strip())
    if not actions:
        actions.append("Zadrži postojeći standard i potvrdi ga na sledećem audit snimku.")
    while len(actions) < 3:
        actions.append("Obavi menadžerski obilazak i potvrdi korekciju tokom sledeće smene.")
    return actions[:3]


def _scope_risk_average(rows):
    if not rows:
        return None
    scores = []
    for row in rows:
        payload = _ensure_dict(row[0] if isinstance(row, tuple) else row)
        if payload:
            scores.append(float(payload.get("overall_risk_score") or compute_station_risk_from_metrics(payload)))
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def render(conn):
    render_page_header("📈 AI Reports & Processing Queue")
    st.markdown(
        '<div class="gs-page-intro">Monitor live processing, review finished audits, and reopen only the reports that genuinely need attention.</div>',
        unsafe_allow_html=True,
    )

    user_role = st.session_state.user_role
    current_user_id = st.session_state.user_id

    ai_status_row = conn.execute(
        "SELECT value FROM system_settings WHERE key='ai_processing_status'"
    ).fetchone()
    ai_last_update_ts = None
    if ai_status_row and ai_status_row[0]:
        try:
            ai_last_update_ts = json.loads(ai_status_row[0]).get("last_update_ts")
        except Exception:
            ai_last_update_ts = None

    # --- Build the base WHERE clause with role-based filtering ---
    where_clause = ""
    params = []

    if current_user_id and user_role in {"Region Manager", "Gas Station Manager", "General Manager"}:
        where_clause, params = get_scope_filter_clause(user_role, current_user_id, conn)
    elif user_role != "General Manager":
        where_clause = "AND 1=0"

    aggregate_where_clause = where_clause.replace("s.", "sub.")

    queue_query = f"""
        SELECT
            s.id, s.timestamp, st.name as station_name,
            COALESCE(NULLIF(TRIM(COALESCE(e.name,'') || ' ' || COALESCE(e.surname,'')), ''), e.email, e.username) as employee_name,
            s.processed, s.retry_count, s.status, s.processing_started_ts, s.video_path
        FROM submissions s
        JOIN stations st ON s.station_id = st.id
        JOIN users e ON s.employee_id = e.id -- submissions.employee_id now references users.id
        WHERE (s.processed IN (0, -1) OR (s.status = 'done' AND COALESCE(s.processed, 0) = 0)) {where_clause}
        ORDER BY s.timestamp DESC
    """
    queue_df = pd.read_sql_query(queue_query, conn, params=params)
    if not queue_df.empty:
        queue_df["raw_status"] = queue_df["status"]

    completed_count_query = f"""
        SELECT COUNT(*)
        FROM submissions s
        JOIN stations st ON s.station_id = st.id
        WHERE s.processed = 1 AND s.data_json IS NOT NULL {where_clause}
    """
    completed_count_row = conn.execute(completed_count_query, params).fetchone()
    completed_count = completed_count_row[0] if completed_count_row else 0

    stalled_cutoff = datetime.utcnow() - timedelta(minutes=QUEUE_STALLED_AFTER_MINUTES)

    def _display_queue_status(row):
        raw_status = str(row.get("status") or "").strip().lower()
        processed = int(row.get("processed") or 0)
        processing_started_ts = row.get("processing_started_ts")
        if raw_status == "done" and processed == 0:
            return "Inconsistent (done but unprocessed)"
        if (
            raw_status == "processing"
            and processing_started_ts is not None
            and pd.Timestamp(processing_started_ts).to_pydatetime() < stalled_cutoff
        ):
            return "Stalled"
        if raw_status == "processing":
            return "Processing"
        if raw_status == "pending":
            return "Pending"
        if raw_status == "failed" or processed == -1:
            return "Failed"
        if raw_status == "done" and processed == 1:
            return "Done"
        return raw_status.title() if raw_status else "Unknown"

    if not queue_df.empty:
        queue_df["status"] = queue_df.apply(_display_queue_status, axis=1)

    pending_count = 0 if queue_df.empty else int((queue_df["status"] == "Pending").sum())
    processing_count = 0 if queue_df.empty else int((queue_df["status"] == "Processing").sum())
    stalled_count = 0 if queue_df.empty else int((queue_df["status"] == "Stalled").sum())
    failed_count = 0 if queue_df.empty else int((queue_df["status"] == "Failed").sum())

    latest_company_query = """
        SELECT sub.data_json
        FROM submissions sub
        JOIN (
            SELECT station_id, MAX(timestamp) as max_ts
            FROM submissions
            WHERE processed = 1 AND data_json IS NOT NULL
            GROUP BY station_id
        ) latest
            ON latest.station_id = sub.station_id AND latest.max_ts = sub.timestamp
        WHERE sub.data_json IS NOT NULL
    """
    latest_company_rows = conn.execute(latest_company_query).fetchall()
    company_risk = _scope_risk_average(latest_company_rows)

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Completed Reports", completed_count)
    m2.metric("Pending", pending_count)
    m3.metric("Processing", processing_count)
    m4.metric("Stalled", stalled_count)
    m5.metric("Failed", failed_count)
    m6.metric("Company Risk", f"{company_risk:.1f}/100" if company_risk is not None else "N/A")

    queue_tab, trends_tab, reports_tab = st.tabs(
        ["Queue", "Trends", "Completed Reports"]
    )

    with queue_tab:
        st.subheader("Processing Queue")
        if queue_df.empty:
            st.info("No pending or failed submissions in the queue for your scope.")
        else:
            if stalled_count:
                last_signal = "unknown"
                if ai_last_update_ts:
                    age_sec = max(0, int(datetime.utcnow().timestamp() - float(ai_last_update_ts)))
                    last_signal = f"{age_sec // 60}m {age_sec % 60}s ago"
                st.warning(
                    f"{stalled_count} submission(s) look stalled. The AI worker last heartbeat was {last_signal}."
                )

            st.dataframe(
                queue_df[
                    [
                        "id",
                        "timestamp",
                        "station_name",
                        "employee_name",
                        "retry_count",
                        "processing_started_ts",
                        "status",
                    ]
                ],
                column_config={
                    "processing_started_ts": "Processing Started",
                },
                width="stretch",
                hide_index=True,
            )

            action_col1, action_col2, action_col3 = st.columns(3)
            with action_col1:
                if st.button("Repair Inconsistent Queue Rows", width="stretch"):
                    conn.execute(
                        """
                        UPDATE submissions
                        SET status='pending', retry_count=0
                        WHERE status='done' AND COALESCE(processed, 0)=0
                        """
                    )
                    conn.commit()
                    st.success("Inconsistent rows moved back to the pending queue.")
                    st.rerun()

            stalled_submissions = queue_df[queue_df["status"] == "Stalled"]
            if not stalled_submissions.empty:
                with action_col2:
                    stalled_id = st.selectbox(
                        "Reset stalled submission",
                        options=stalled_submissions["id"].tolist(),
                        key="reset_stalled_submission_id",
                    )
                    if st.button("Move Stalled Job Back to Pending", width="stretch"):
                        conn.execute(
                            """
                            UPDATE submissions
                            SET status = 'pending',
                                retry_count = 0
                            WHERE id = %s
                            """,
                            (stalled_id,),
                        )
                        conn.commit()
                        log_activity(
                            conn,
                            "AI_REQUEUE_STALLED",
                            f"Moved stalled submission ID {stalled_id} back to pending",
                        )
                        st.success(
                            f"Submission ID {stalled_id} has been returned to the pending queue."
                        )
                        st.rerun()

            failed_submissions = queue_df[queue_df["processed"] == -1]
            if not failed_submissions.empty:
                with action_col3:
                    selected_id = st.selectbox(
                        "Retry failed submission",
                        options=failed_submissions["id"].tolist(),
                    )
                    if st.button("Reset Retries & Re-queue", type="primary", width="stretch"):
                        if selected_id:
                            conn.execute(
                                """
                                UPDATE submissions
                                SET processed = 0,
                                    status = 'pending',
                                    retry_count = 0
                                WHERE id = %s
                            """,
                                (selected_id,),
                            )
                            conn.commit()
                            log_activity(
                                conn,
                                "AI_RETRY_RESET",
                                f"Manually reset retries for submission ID {selected_id}",
                            )
                            st.success(
                                f"Submission ID {selected_id} has been re-queued for processing."
                            )
                            st.rerun()

                cleanup_col1, cleanup_col2 = st.columns(2)
                with cleanup_col1:
                    failed_delete_id = st.selectbox(
                        "Delete failed submission",
                        options=failed_submissions["id"].tolist(),
                        key="delete_failed_submission_id",
                    )
                with cleanup_col2:
                    if st.button(
                        "Delete Failed Submission & Media",
                        type="secondary",
                        width="stretch",
                    ):
                        failed_row = failed_submissions[
                            failed_submissions["id"] == failed_delete_id
                        ].iloc[0]
                        media_path = failed_row.get("video_path")
                        if media_path:
                            media_file = Path(str(media_path))
                            if media_file.exists():
                                media_file.unlink()
                        conn.execute(
                            "DELETE FROM submissions WHERE id = %s AND processed = -1",
                            (int(failed_delete_id),),
                        )
                        conn.commit()
                        log_activity(
                            conn,
                            "DELETE_FAILED_SUBMISSION",
                            f"Deleted failed submission ID {failed_delete_id} and removed its media file.",
                        )
                        st.success(
                            f"Failed submission ID {failed_delete_id} and its local media were removed."
                        )
                        st.rerun()

    analytics_query = f"""
        SELECT
            st.name as "Station",
            AVG(CAST(COALESCE(s.data_json->>'overall_risk_score', '0') AS REAL)) as "Average Risk Score"
        FROM submissions s
        JOIN stations st ON s.station_id = st.id
        WHERE s.processed = 1
          AND s.data_json IS NOT NULL
          AND s.timestamp >= NOW() - INTERVAL '30 days'
          {where_clause}
        GROUP BY st.id
        ORDER BY "Average Risk Score" DESC
    """
    analytics_df = pd.read_sql_query(analytics_query, conn, params=params)

    with trends_tab:
        st.subheader("30-Day Risk Trends")
        if not analytics_df.empty:
            station_col = _resolve_column(
                analytics_df, "Station", "station", "station_name"
            )
            score_col = _resolve_column(
                analytics_df, "Average Risk Score", "average risk score"
            )
            if station_col and score_col:
                chart_df = analytics_df.rename(
                    columns={station_col: "Station", score_col: "Average Risk Score"}
                )
                st.bar_chart(chart_df.set_index("Station"))
            else:
                st.caption("Analytics data is available, but expected columns are missing.")
        else:
            st.caption("No analytics data available for the last 30 days.")

    completed_query = f"""
        SELECT
            s.id, s.timestamp, s.station_id, st.region_id, st.name as "Station", s.data_json as kpi_json
        FROM submissions s
        JOIN stations st ON s.station_id = st.id
        WHERE s.processed = 1 AND s.data_json IS NOT NULL {where_clause}
        ORDER BY s.timestamp DESC LIMIT 200
    """
    df = pd.read_sql_query(completed_query, conn, params=params)

    with reports_tab:
        st.subheader("Completed Reports")
        if df.empty:
            st.info("No completed AI reports available for your scope.")
            return

        def extract_from_json(json_str, key, default=None):
            data = _ensure_dict(json_str)
            return data.get(key, default)

        df["safety_score"] = df["kpi_json"].apply(
            lambda x: extract_from_json(x, "safety_score")
        )
        df["cleanliness_score"] = df["kpi_json"].apply(
            lambda x: extract_from_json(x, "cleanliness_score")
        )
        df["staff_score"] = df["kpi_json"].apply(
            lambda x: extract_from_json(x, "staff_score")
        )
        df["merchandising_score"] = df["kpi_json"].apply(
            lambda x: extract_from_json(x, "merchandising_score")
        )
        df["risk_score"] = df["kpi_json"].apply(
            lambda x: round(
                float(extract_from_json(x, "overall_risk_score", 0) or compute_station_risk_from_metrics(_ensure_dict(x))),
                2,
            )
        )
        station_col = _resolve_column(df, "Station", "station", "station_name")
        timestamp_col = _resolve_column(df, "timestamp", "Timestamp")
        if station_col and station_col != "Station":
            df["Station"] = df[station_col]
        if timestamp_col and timestamp_col != "timestamp":
            df["timestamp"] = df[timestamp_col]

        st.dataframe(
            df[
                [
                    "timestamp",
                    "Station",
                    "safety_score",
                    "cleanliness_score",
                    "staff_score",
                    "merchandising_score",
                    "risk_score",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

        idx = st.selectbox("Select report ID to preview details", df["id"].tolist())
        if idx:
            row = df[df["id"] == idx].iloc[0]
            st.subheader(f"Report Details for Submission #{idx}")
            st.write(
                f"**Station:** {row['Station']} | **Submitted:** {row['timestamp']}"
            )

            kpi_data = _ensure_dict(row["kpi_json"])
            if kpi_data:
                risk_score = float(
                    kpi_data.get("overall_risk_score")
                    or compute_station_risk_from_metrics(kpi_data)
                )
                summary_text = _derive_summary(kpi_data)
                improvements = _derive_improvements(kpi_data)

                risk_col1, risk_col2, risk_col3, risk_col4, risk_col5 = st.columns(5)
                risk_col1.metric("Overall Risk", f"{risk_score:.1f}/100", _risk_band(risk_score))
                risk_col2.metric("Safety", f"{int(float(kpi_data.get('safety_score', 5) or 5))}/10")
                risk_col3.metric("Cleanliness", f"{int(float(kpi_data.get('cleanliness_score', 5) or 5))}/10")
                risk_col4.metric("Staff", f"{int(float(kpi_data.get('staff_score', 5) or 5))}/10")
                risk_col5.metric("Merchandising", f"{int(float(kpi_data.get('merchandising_score', 5) or 5))}/10")

                station_rows = conn.execute(
                    """
                    SELECT data_json FROM submissions
                    WHERE station_id = %s AND processed = 1 AND data_json IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT 10
                    """,
                    (int(row["station_id"]),),
                ).fetchall()
                station_risk = _scope_risk_average(station_rows)

                region_rows = conn.execute(
                    """
                    SELECT sub.data_json
                    FROM submissions sub
                    JOIN stations st ON st.id = sub.station_id
                    JOIN (
                        SELECT station_id, MAX(timestamp) as max_ts
                        FROM submissions
                        WHERE processed = 1 AND data_json IS NOT NULL
                        GROUP BY station_id
                    ) latest
                        ON latest.station_id = sub.station_id AND latest.max_ts = sub.timestamp
                    WHERE st.region_id = %s AND sub.data_json IS NOT NULL
                    """,
                    (int(row["region_id"]),),
                ).fetchall()
                region_risk = _scope_risk_average(region_rows)

                scope1, scope2, scope3 = st.columns(3)
                scope1.metric("Station Risk", f"{station_risk:.1f}/100" if station_risk is not None else "N/A")
                scope2.metric("Region Risk", f"{region_risk:.1f}/100" if region_risk is not None else "N/A")
                scope3.metric("Company Risk", f"{company_risk:.1f}/100" if company_risk is not None else "N/A")

                st.markdown("#### Izvršni sažetak")
                st.write(summary_text)

                st.markdown("#### Preporučene akcije")
                for action in improvements:
                    st.markdown(f"- {action}")

                hazards = kpi_data.get("hazards") or []
                stock_issues = kpi_data.get("stock_issues") or []
                detail_col1, detail_col2 = st.columns(2)
                with detail_col1:
                    st.markdown("#### Uočeni rizici")
                    if hazards:
                        for item in hazards:
                            st.markdown(f"- {item}")
                    else:
                        st.caption("U ovom izveštaju nisu izdvojeni konkretni rizici.")
                with detail_col2:
                    st.markdown("#### Stock / operativni problemi")
                    if stock_issues:
                        for item in stock_issues:
                            st.markdown(f"- {item}")
                    else:
                        st.caption("U ovom izveštaju nisu izdvojeni stock problemi.")

                st.markdown("#### Model Output")
                configured_model = os.getenv(
                    "OLLAMA_VISION_MODEL",
                    os.getenv("OLLAMA_MODEL", "bakllava:latest"),
                )
                st.caption(
                    f"AI Model: `{kpi_data.get('_model_used') or kpi_data.get('_vision_model') or kpi_data.get('_llm_model') or configured_model}`"
                )
                if kpi_data.get("_vision_error"):
                    st.warning(f"Model error: {kpi_data.get('_vision_error')}")
                elif kpi_data.get("_llm_error"):
                    st.warning(f"Model error: {kpi_data.get('_llm_error')}")

                model_output = (
                    kpi_data.get("_vision_output")
                    or kpi_data.get("_llm_output")
                )
                if model_output:
                    st.json(model_output)

                st.markdown("---")
                st.markdown("#### Active Station Alerts")
                st.caption("Current unresolved alerts for the station associated with this report.")

                with get_session() as session:
                    station_obj = session.get(Station, int(row["station_id"]))
                    if station_obj and station_obj.alerts:
                        active_alerts = [a for a in station_obj.alerts if a.status in ("new", "acknowledged")]
                        if active_alerts:
                            for alert in active_alerts:
                                icon = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "ℹ️"}.get(alert.severity, "ℹ️")
                                with st.container(border=True):
                                    st.markdown(f"**{icon} {alert.severity}** - {alert.status.upper()}")
                                    st.write(alert.message)
                                    st.caption(f"Alert Timestamp: {alert.created_at}")
                        else:
                            st.success("No active alerts currently registered for this station.")
                    else:
                        st.info("No alert history found for this station.")
            else:
                st.warning("No detailed KPI data available for this report.")
