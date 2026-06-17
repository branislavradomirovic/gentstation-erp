import streamlit as st
import pandas as pd
from core.database import get_connection
from core.access_control import require_platform_superadmin
from core.observability import (
    get_observability_snapshot,
    get_recent_operational_failures,
    get_worker_resource_rows,
)
from ui.header import render_page_header

def render(conn):
    """Global observability dashboard for Platform Superadmins."""
    require_platform_superadmin(st.session_state.get("username"))
    render_page_header("🏥 Platform Health")

    st.markdown('<div class="gs-page-intro">Global infrastructure monitoring. Inspect system-wide queue depths, worker heartbeats, and database pool health across all tenants.</div>', unsafe_allow_html=True)

    # 1. Global Queue Depth
    with get_connection(platform_access=True) as p_conn:
        snapshot = get_observability_snapshot(p_conn)
        queue = snapshot["queue"]
        workers = snapshot["workers"]
        disk = snapshot["disk"]
        pool = snapshot["pool"]
        redis_online = snapshot["redis_online"]

        st.subheader("📊 Global System Load")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Pending Submissions", queue["pending_submissions"])
        q2.metric("Pending CCTV Jobs", queue["pending_cctv_jobs"])
        q3.metric("Failed Queue Items", queue["failed_submissions"])
        q4.metric("Unresolved Alerts", queue["new_alerts"])

        # 2. Worker Fleet Status
        st.divider()
        st.subheader("🤖 Background Services")
        w_cols = st.columns(4)
        for index, item in enumerate(workers):
            with w_cols[index]:
                status = str(item["status"] or "offline").upper()
                if status in {"ONLINE", "IDLE", "RUNNING", "PROCESSING"}:
                    color = "green"
                elif status == "STALE":
                    color = "red"
                else:
                    color = "orange" if status not in {"OFFLINE"} else "gray"
                age_seconds = item.get("age_seconds")
                age_str = f"Seen {age_seconds}s ago" if age_seconds is not None else "No heartbeat"
                st.markdown(f"**{item['worker_name']}**")
                st.markdown(
                    f'<span style="color:{color}; font-weight:bold;">{status}</span>',
                    unsafe_allow_html=True,
                )
                st.caption(age_str)
                if item.get("details"):
                    st.caption(str(item["details"]))

        # 3. Platform Infrastructure
        st.divider()
        st.subheader("💾 Infrastructure Health")
        i1, i2, i3, i4 = st.columns(4)
        i1.metric("Disk Usage", f"{disk['used_pct']}%")
        i2.metric(
            "DB Pool",
            f"{pool.get('checkedout', 0)}/{pool.get('total_capacity', 0)}",
            f"{pool.get('usage_pct', 0)}% load" if pool else "Unavailable",
        )
        i3.metric("Redis", "ONLINE" if redis_online else "OFFLINE")
        stale_workers = sum(1 for item in workers if item["status"] == "stale")
        i4.metric("Stale Workers", stale_workers)

        st.progress(min(max(float(disk["used_pct"]) / 100.0, 0.0), 1.0))
        st.caption(
            f"Disk free: {round(disk['free_bytes'] / (1024 ** 3), 2)} GB on {disk['path']}"
        )

        st.divider()
        st.subheader("📈 Worker Resource History")
        resource_rows = get_worker_resource_rows(p_conn, limit=20)
        if resource_rows:
            st.dataframe(pd.DataFrame(resource_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No worker resource samples recorded yet.")

        # 4. Global Error Log (Recent failures across any tenant)
        st.divider()
        st.subheader("🛡️ Recent System Anomalies")
        err_df = pd.DataFrame(
            get_recent_operational_failures(p_conn, limit=20),
            columns=["timestamp", "user_name", "action", "details"],
        )
        if err_df.empty:
            st.success("No system-level errors recorded in the last 24 hours.")
        else:
            st.dataframe(err_df, use_container_width=True, hide_index=True)

    if st.button("🔄 Refresh Health Data", use_container_width=True):
        st.rerun()
