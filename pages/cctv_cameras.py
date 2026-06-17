from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from core.activity_logger import log_activity
from core.database import get_session
from core.models import CCTVCamera, CCTVZone, Station
from core.subscription import FEATURE_CCTV_INTELLIGENCE, require_feature
from core.tenant_context import current_tenant_id
from ui.header import render_page_header


def _parse_json_text(value: str, default):
    text = (value or "").strip()
    if not text:
        return default
    return json.loads(text)


def render(conn):
    """Render the tenant-scoped CCTV camera registry and zone editor."""
    require_feature(conn, FEATURE_CCTV_INTELLIGENCE)
    tenant_id = current_tenant_id()
    render_page_header("🎥 Camera Registry")

    st.markdown(
        '<div class="gs-page-intro">Register tenant cameras, edit stream metadata, and store analytical zone rules for each feed.</div>',
        unsafe_allow_html=True,
    )

    if "selected_cctv_camera_id" not in st.session_state:
        st.session_state.selected_cctv_camera_id = None

    with get_session() as session:
        stations = (
            session.query(Station)
            .filter(Station.tenant_id == tenant_id)
            .order_by(Station.name)
            .all()
        )
        station_lookup = {station.id: station.name for station in stations}

        cameras = (
            session.query(CCTVCamera)
            .filter(CCTVCamera.tenant_id == tenant_id)
            .order_by(CCTVCamera.id.desc())
            .all()
        )
        camera_labels = {
            camera.id: f"{station_lookup.get(camera.station_id, f'Station {camera.station_id}')} - {camera.name}"
            for camera in cameras
        }
        if cameras and st.session_state.selected_cctv_camera_id is None:
            st.session_state.selected_cctv_camera_id = cameras[0].id

        tab_registry, tab_zones = st.tabs(["📡 Camera Registry", "📐 Zone Configuration"])

        with tab_registry:
            c_metrics = st.columns(3)
            c_metrics[0].metric("Registered Cameras", len(cameras))
            c_metrics[1].metric("Stations with Cameras", len({camera.station_id for camera in cameras}))
            c_metrics[2].metric("Defined Zones", session.query(CCTVZone).filter(CCTVZone.tenant_id == tenant_id).count())

            if cameras:
                df = pd.DataFrame(
                    [
                        {
                            "ID": camera.id,
                            "Station": station_lookup.get(camera.station_id, f"Station {camera.station_id}"),
                            "Name": camera.name,
                            "Type": camera.camera_type,
                            "Status": camera.status,
                            "Timezone": camera.timezone or "UTC",
                            "Zones": len(camera.zones),
                            "Last Seen": camera.last_seen_at,
                        }
                        for camera in cameras
                    ]
                )
                selection_event = st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="cctv_camera_directory",
                )
                rows = selection_event.get("selection", {}).get("rows", [])
                if rows:
                    st.session_state.selected_cctv_camera_id = int(df.iloc[rows[0]]["ID"])
            else:
                st.info("No cameras registered for this tenant yet.")

            st.divider()
            st.markdown("#### Register a new camera")
            with st.form("add_camera_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                if stations:
                    station_id = c1.selectbox(
                        "Station Assignment",
                        options=[station.id for station in stations],
                        format_func=lambda x: station_lookup.get(x, f"Station {x}"),
                    )
                else:
                    station_id = None
                    c1.info("Create a station first before registering cameras.")
                name = c2.text_input("Friendly Name", placeholder="e.g. Pump 1-4 Overlook")
                c_type = st.selectbox("Camera Hardware Type", ["dome", "bullet", "360", "ptz"])
                status = st.selectbox("Status", ["active", "inactive", "maintenance"], index=0)
                timezone = st.text_input("Timezone", value="UTC")
                stream_url = st.text_input(
                    "Stream URL Secret Reference",
                    help="Reference name for the RTSP/HLS credential stored in the secure environment.",
                )

                if st.form_submit_button("Register Camera", use_container_width=True):
                    if not stations:
                        st.error("Create a station first before registering cameras.")
                    elif not name.strip():
                        st.error("Camera name is required.")
                    else:
                        new_cam = CCTVCamera(
                            tenant_id=tenant_id,
                            station_id=station_id,
                            name=name.strip(),
                            camera_type=c_type,
                            status=status,
                            timezone=(timezone or "UTC").strip() or "UTC",
                            stream_url_secret_ref=(stream_url or "").strip() or None,
                        )
                        session.add(new_cam)
                        session.commit()
                        log_activity(conn, "CCTV_CAMERA_CREATE", f"Added camera '{name.strip()}' to station ID {station_id}")
                        st.success(f"Camera '{name.strip()}' successfully registered.")
                        st.rerun()

        with tab_zones:
            if not cameras:
                st.warning("Register a camera first before defining zones.")
            else:
                selected_cam_id = st.selectbox(
                    "Select Camera",
                    [camera.id for camera in cameras],
                    format_func=lambda x: camera_labels[x],
                    index=0 if st.session_state.selected_cctv_camera_id is None else next(
                        (idx for idx, camera in enumerate(cameras) if camera.id == st.session_state.selected_cctv_camera_id),
                        0,
                    ),
                    key="cctv_zone_camera_selector",
                )
                st.session_state.selected_cctv_camera_id = int(selected_cam_id)
                selected_camera = (
                    session.query(CCTVCamera)
                    .filter(CCTVCamera.tenant_id == tenant_id, CCTVCamera.id == selected_cam_id)
                    .one_or_none()
                )

                if not selected_camera:
                    st.error("Selected camera is no longer available.")
                    return

                c_edit1, c_edit2 = st.columns(2)
                with c_edit1:
                    with st.form(f"edit_camera_form_{selected_cam_id}"):
                        cam_name = st.text_input("Camera Name", value=selected_camera.name)
                        cam_type = st.selectbox(
                            "Camera Type",
                            ["dome", "bullet", "360", "ptz"],
                            index=["dome", "bullet", "360", "ptz"].index(selected_camera.camera_type or "dome"),
                        )
                        cam_status = st.selectbox(
                            "Status",
                            ["active", "inactive", "maintenance"],
                            index=["active", "inactive", "maintenance"].index(selected_camera.status or "active"),
                        )
                        cam_timezone = st.text_input("Timezone", value=selected_camera.timezone or "UTC")
                        cam_station_id = st.selectbox(
                            "Station",
                            options=[station.id for station in stations],
                            format_func=lambda x: station_lookup.get(x, f"Station {x}"),
                            index=next(
                                (idx for idx, station in enumerate(stations) if station.id == selected_camera.station_id),
                                0,
                            ),
                        )
                        cam_stream_ref = st.text_input(
                            "Stream URL Secret Reference",
                            value=selected_camera.stream_url_secret_ref or "",
                        )
                        if st.form_submit_button("Save Camera Changes", use_container_width=True):
                            if not cam_name.strip():
                                st.error("Camera name is required.")
                            else:
                                selected_camera.name = cam_name.strip()
                                selected_camera.camera_type = cam_type
                                selected_camera.status = cam_status
                                selected_camera.timezone = (cam_timezone or "UTC").strip() or "UTC"
                                selected_camera.station_id = cam_station_id
                                selected_camera.stream_url_secret_ref = (cam_stream_ref or "").strip() or None
                                session.commit()
                                log_activity(conn, "CCTV_CAMERA_UPDATE", f"Updated camera ID {selected_cam_id}")
                                st.success("Camera updated.")
                                st.rerun()

                with c_edit2:
                    st.markdown("#### Camera Controls")
                    if st.button("Delete Camera", type="secondary", use_container_width=True, key=f"delete_cctv_camera_{selected_cam_id}"):
                        session.query(CCTVCamera).filter(
                            CCTVCamera.tenant_id == tenant_id,
                            CCTVCamera.id == selected_cam_id,
                        ).delete(synchronize_session=False)
                        session.commit()
                        st.session_state.selected_cctv_camera_id = None
                        log_activity(conn, "CCTV_CAMERA_DELETE", f"Deleted camera ID {selected_cam_id}")
                        st.success("Camera deleted.")
                        st.rerun()

                    st.caption("Zones are stored as tenant-scoped JSON configuration for each camera.")

                zones = (
                    session.query(CCTVZone)
                    .filter(
                        CCTVZone.tenant_id == tenant_id,
                        CCTVZone.camera_id == selected_cam_id,
                    )
                    .order_by(CCTVZone.id.asc())
                    .all()
                )

                if zones:
                    df_zones = pd.DataFrame(
                        [
                            {
                                "ID": zone.id,
                                "Name": zone.name,
                                "Type": zone.zone_type,
                                "Active": bool(zone.active),
                                "Polygon": json.dumps(zone.polygon_json or []),
                                "Rules": json.dumps(zone.rules_json or {}),
                            }
                            for zone in zones
                        ]
                    )
                    st.dataframe(df_zones, use_container_width=True, hide_index=True)
                else:
                    st.info("No zones defined for this camera yet.")

                st.divider()
                st.markdown("#### Add Zone")
                with st.form(f"add_zone_form_{selected_cam_id}", clear_on_submit=True):
                    z_name = st.text_input("Zone Name", placeholder="e.g. Entrance Lane")
                    z_type = st.selectbox("Type", ["pump", "entrance", "shop", "restricted"])
                    z_active = st.checkbox("Active", value=True)
                    z_polygon = st.text_area(
                        "Polygon Coordinates (JSON)",
                        value='[[0,0], [100,0], [100,100], [0,100]]',
                    )
                    z_rules = st.text_area("Zone Rules (JSON)", value='{"alert_on_entry": true}')

                    if st.form_submit_button("Save Zone", use_container_width=True):
                        if not z_name.strip():
                            st.error("Zone name is required.")
                        else:
                            try:
                                polygon_json = _parse_json_text(z_polygon, [])
                                rules_json = _parse_json_text(z_rules, {})
                            except json.JSONDecodeError as exc:
                                st.error(f"Invalid JSON: {exc}")
                            else:
                                new_zone = CCTVZone(
                                    tenant_id=tenant_id,
                                    camera_id=selected_cam_id,
                                    name=z_name.strip(),
                                    zone_type=z_type,
                                    polygon_json=polygon_json,
                                    active=z_active,
                                    rules_json=rules_json,
                                )
                                session.add(new_zone)
                                session.commit()
                                log_activity(conn, "CCTV_ZONE_CREATE", f"Defined zone '{z_name.strip()}' for camera ID {selected_cam_id}")
                                st.success(f"Zone '{z_name.strip()}' defined.")
                                st.rerun()
