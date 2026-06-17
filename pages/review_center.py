from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from core.activity_logger import log_activity
from core.cctv_review import allowed_review_actions, apply_review_transition
from core.database import get_session
from core.models import CCTVEvent, CCTVCamera, CCTVReviewAction, Station
from core.storage import get_evidence_url
from core.subscription import FEATURE_CCTV_INTELLIGENCE, require_feature
from core.tenant_context import current_tenant_id
from ui.header import render_page_header


def render(conn):
    """Render the tenant-scoped CCTV review center with audited transitions."""
    require_feature(conn, FEATURE_CCTV_INTELLIGENCE)
    tenant_id = current_tenant_id()
    render_page_header("🎬 Review Center")

    st.markdown(
        '<div class="gs-page-intro">Review AI-detected CCTV events, verify findings, and manage operational follow-up. Border colors reflect event severity.</div>',
        unsafe_allow_html=True,
    )

    with get_session() as session:
        c1, c2, c3, c4, c5 = st.columns(5)
        status_filter = c1.multiselect(
            "Status",
            ["new", "acknowledged", "reviewed", "false_positive", "resolved", "escalated"],
            default=["new", "acknowledged"],
        )
        severity_filter = c2.multiselect("Severity", ["low", "medium", "high"], default=["medium", "high"])

        stations = (
            session.query(Station)
            .filter(Station.tenant_id == tenant_id)
            .order_by(Station.name)
            .all()
        )
        station_map = {station.name: station.id for station in stations}
        selected_stations = c3.multiselect("Stations", list(station_map.keys()))

        cameras = (
            session.query(CCTVCamera)
            .filter(CCTVCamera.tenant_id == tenant_id)
            .order_by(CCTVCamera.name)
            .all()
        )
        camera_map = {camera.name: camera.id for camera in cameras}
        selected_cameras = c4.multiselect("Cameras", list(camera_map.keys()))

        event_types = [
            row[0]
            for row in session.query(CCTVEvent.event_type)
            .filter(CCTVEvent.tenant_id == tenant_id)
            .distinct()
            .order_by(CCTVEvent.event_type)
            .all()
        ]
        selected_types = c5.multiselect("Event Type", event_types)

        c6, c7 = st.columns(2)
        default_range = (date.today() - timedelta(days=7), date.today())
        start_date, end_date = c6.date_input("Occurred Between", value=default_range)
        review_required_only = c7.toggle("Review required only", value=False)

        query = session.query(CCTVEvent).filter(CCTVEvent.tenant_id == tenant_id)
        if status_filter:
            query = query.filter(CCTVEvent.status.in_(status_filter))
        if severity_filter:
            query = query.filter(CCTVEvent.severity.in_(severity_filter))
        if selected_stations:
            query = query.filter(CCTVEvent.station_id.in_([station_map[name] for name in selected_stations]))
        if selected_cameras:
            query = query.filter(CCTVEvent.camera_id.in_([camera_map[name] for name in selected_cameras]))
        if selected_types:
            query = query.filter(CCTVEvent.event_type.in_(selected_types))
        if review_required_only:
            query = query.filter(CCTVEvent.review_required.is_(True))
        if start_date and end_date:
            query = query.filter(CCTVEvent.occurred_at >= start_date, CCTVEvent.occurred_at <= end_date + timedelta(days=1))

        events = query.order_by(CCTVEvent.occurred_at.desc()).limit(50).all()

        if not events:
            st.info("📡 No CCTV events found matching your current filters.")
            return

        for ev in events:
            with st.container(border=True):
                col_main, col_side = st.columns([2.2, 0.8])
                with col_main:
                    st.markdown(f"### {ev.event_type.replace('_', ' ').title()}")
                    st.markdown(f"**Station:** `{ev.station.name if ev.station else 'N/A'}` | **Camera:** `{ev.camera.name if ev.camera else 'N/A'}`")
                    st.markdown(f"**Occurred:** {ev.occurred_at.strftime('%Y-%m-%d %H:%M:%S')}")
                    st.markdown(f"**Confidence:** `{float(ev.confidence or 0):.1%}`")
                    st.caption(f"Current status: `{ev.status}`")

                    evidence_url = get_evidence_url(ev.evidence_path)
                    if evidence_url:
                        st.video(evidence_url)
                    else:
                        st.caption("Evidence media not available for this event.")

                with col_side:
                    st.markdown(f'<div style="text-align:right;">Status: <b>{str(ev.status).upper()}</b></div>', unsafe_allow_html=True)
                    st.divider()

                    next_actions = list(allowed_review_actions(ev.status))
                    if not next_actions:
                        st.caption("This event status is closed.")
                    else:
                        with st.form(f"review_form_{ev.id}"):
                            new_status = st.selectbox("Action", next_actions, key=f"action_{ev.id}")
                            comment = st.text_area("Comment", placeholder="Add internal note...", key=f"comment_{ev.id}")
                            if st.form_submit_button("Apply Action", use_container_width=True):
                                result = apply_review_transition(
                                    session,
                                    event=ev,
                                    tenant_id=tenant_id,
                                    reviewer_user_id=st.session_state.get("user_id"),
                                    new_status=new_status,
                                    comment=comment,
                                )
                                session.commit()
                                log_activity(
                                    conn,
                                    "CCTV_REVIEW",
                                    f"Event {ev.id} {result.previous_status} -> {result.new_status}",
                                )
                                st.success("Status updated.")
                                st.rerun()

                if ev.review_actions:
                    with st.expander("📝 View Audit Trail"):
                        for ra in ev.review_actions:
                            st.caption(
                                f"**{(ra.action or '').upper()}** {ra.from_status or 'unknown'} -> {ra.to_status or 'unknown'} by User {ra.reviewer_user_id} at {ra.created_at}"
                            )
                            if ra.comment:
                                st.write(f"> {ra.comment}")
