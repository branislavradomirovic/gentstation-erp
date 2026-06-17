import secrets

import pandas as pd
import streamlit as st

from core.access_control import require_platform_superadmin
from core.activity_logger import log_activity
from core.comm_service import send_activation_email
from core.database import get_connection
from core.platform_admin import (
    TIER_1_AI_DAILY_OPERATIONS,
    TIER_2_CCTV_INTELLIGENCE,
    create_tenant_with_company_admin,
    slugify_tenant_name,
)
from ui.header import render_page_header


def _generate_temp_password(length: int = 12) -> str:
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # pragma: allowlist secret
    return "".join(secrets.choice(alphabet) for _ in range(length))


def render(conn):
    render_page_header("🧭 Platform Administration")
    require_platform_superadmin(st.session_state.get("username"))
    st.markdown(
        '<div class="gs-page-intro">Create new company tenants, assign the first General Manager, and review multi-tenant rollout status from one platform-only workspace.</div>',
        unsafe_allow_html=True,
    )

    platform_conn = get_connection(platform_access=True)
    try:
        overview_query = """
            SELECT
                t.id,
                t.name,
                t.slug,
                t.status,
                ts.tier_code,
                ts.station_limit,
                ts.employee_limit,
                ts.camera_limit,
                COALESCE(u.email, u.username) AS company_admin,
                COALESCE(region_counts.region_count, 0) AS region_count,
                COALESCE(station_counts.station_count, 0) AS station_count,
                COALESCE(user_counts.user_count, 0) AS user_count
            FROM tenants t
            LEFT JOIN tenant_subscriptions ts ON ts.tenant_id = t.id
            LEFT JOIN LATERAL (
                SELECT email, username
                FROM users
                WHERE tenant_id = t.id AND role = 'General Manager'
                ORDER BY id
                LIMIT 1
            ) u ON TRUE
            LEFT JOIN (
                SELECT tenant_id, COUNT(*) AS region_count
                FROM regions
                GROUP BY tenant_id
            ) region_counts ON region_counts.tenant_id = t.id
            LEFT JOIN (
                SELECT tenant_id, COUNT(*) AS station_count
                FROM stations
                GROUP BY tenant_id
            ) station_counts ON station_counts.tenant_id = t.id
            LEFT JOIN (
                SELECT tenant_id, COUNT(*) AS user_count
                FROM users
                GROUP BY tenant_id
            ) user_counts ON user_counts.tenant_id = t.id
            ORDER BY t.id
        """
        overview_df = pd.read_sql_query(overview_query, platform_conn)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Tenants", int(len(overview_df)))
        k2.metric(
            "Tier 1 Companies",
            int((overview_df["tier_code"] == TIER_1_AI_DAILY_OPERATIONS).sum())
            if not overview_df.empty
            else 0,
        )
        k3.metric(
            "Tier 2 Companies",
            int((overview_df["tier_code"] == TIER_2_CCTV_INTELLIGENCE).sum())
            if not overview_df.empty
            else 0,
        )
        k4.metric(
            "Company Admins",
            int(overview_df["company_admin"].notna().sum()) if not overview_df.empty else 0,
        )

        st.divider()
        st.markdown("### Tenant Creation & Company Admin Onboarding")

        suggested_password = _generate_temp_password()
        with st.form("platform_tenant_onboarding_form", clear_on_submit=False):
            c1, c2 = st.columns(2)
            tenant_name = c1.text_input("Company Name")
            tenant_slug_input = c2.text_input("Company Slug", help="Leave blank to auto-generate from company name.")
            c3, c4 = st.columns(2)
            tier_code = c3.selectbox(
                "Service Tier",
                [TIER_1_AI_DAILY_OPERATIONS, TIER_2_CCTV_INTELLIGENCE],
                format_func=lambda value: {
                    TIER_1_AI_DAILY_OPERATIONS: "Tier 1 - AI Daily Operations",
                    TIER_2_CCTV_INTELLIGENCE: "Tier 2 - CCTV Intelligence",
                }[value],
            )
            billing_email = c4.text_input("Billing Email")

            c5, c6, c7 = st.columns(3)
            timezone = c5.text_input("Timezone", value="UTC")
            locale = c6.text_input("Locale", value="en")
            station_limit = c7.number_input(
                "Station Limit",
                min_value=0,
                value=0,
                help="Use 0 and leave the checkbox off below for unlimited plans.",
            )

            c8, c9, c10 = st.columns(3)
            unlimited_stations = c8.checkbox("Unlimited Stations", value=True)
            employee_limit = c9.number_input("Employee Limit", min_value=0, value=0)
            unlimited_employees = c10.checkbox("Unlimited Employees", value=True)

            c11, c12 = st.columns(2)
            camera_limit = c11.number_input("Camera Limit", min_value=0, value=0)
            unlimited_cameras = c12.checkbox(
                "Unlimited Cameras",
                value=(tier_code == TIER_2_CCTV_INTELLIGENCE),
            )

            st.markdown("#### First Company Admin")
            a1, a2 = st.columns(2)
            admin_first_name = a1.text_input("First Name")
            admin_surname = a2.text_input("Surname")
            a3, a4 = st.columns(2)
            admin_email = a3.text_input("Admin Email")
            admin_username = a4.text_input("Admin Username", help="Defaults to admin email if left blank.")
            admin_password = st.text_input(
                "Temporary Password",
                value=suggested_password,
                type="password",
            )
            send_invite = st.checkbox(
                "Send activation email after onboarding",
                value=False,
            )

            submitted = st.form_submit_button("Create Tenant & Onboard Admin", width="stretch")
            if submitted:
                clean_tenant_name = (tenant_name or "").strip()
                clean_admin_email = (admin_email or "").strip()
                clean_admin_username = (admin_username or "").strip() or clean_admin_email
                if not clean_tenant_name:
                    st.error("Company name is required.")
                elif not clean_admin_email:
                    st.error("Admin email is required.")
                elif not clean_admin_username:
                    st.error("Admin username is required.")
                elif not admin_password:
                    st.error("Temporary password is required.")
                else:
                    try:
                        result = create_tenant_with_company_admin(
                            platform_conn,
                            tenant_name=clean_tenant_name,
                            tenant_slug=(tenant_slug_input or "").strip() or slugify_tenant_name(clean_tenant_name),
                            tier_code=tier_code,
                            billing_email=(billing_email or "").strip() or None,
                            timezone=(timezone or "UTC").strip() or "UTC",
                            locale=(locale or "en").strip() or "en",
                            station_limit=None if unlimited_stations else int(station_limit),
                            employee_limit=None if unlimited_employees else int(employee_limit),
                            camera_limit=None if unlimited_cameras else int(camera_limit),
                            admin_username=clean_admin_username,
                            admin_password=admin_password,
                            admin_email=clean_admin_email,
                            admin_first_name=(admin_first_name or "").strip() or None,
                            admin_surname=(admin_surname or "").strip() or None,
                            metadata_json={"source": "platform_admin_ui"},
                        )
                        platform_conn.commit()
                        invite_message = "Invite not sent."
                        if send_invite:
                            sent, msg = send_activation_email(
                                platform_conn,
                                result.admin_user_id,
                                reset_password=False,
                                tenant_id=result.tenant_id,
                            )
                            invite_message = "Invite sent." if sent else f"Invite not sent: {msg}"
                        log_activity(
                            conn, # This conn is platform_conn, so it has platform_access=True
                            "CREATE_TENANT",
                            f"Created tenant {result.tenant_name} ({result.tenant_slug}) with admin {result.admin_username}",
                            tenant_id=-1 # Explicitly set for platform activity
                        )
                        st.success(
                            f"Tenant '{result.tenant_name}' created with admin '{result.admin_username}'. {invite_message}"
                        )
                        st.info(
                            f"Tenant ID: {result.tenant_id} | Slug: {result.tenant_slug} | Temporary Password: {admin_password}"
                        )
                        st.rerun()
                    except Exception as exc:
                        platform_conn.rollback()
                        st.error(f"Tenant onboarding failed: {exc}")

        st.divider()
        st.markdown("### Existing Tenants")
        if overview_df.empty:
            st.info("No tenants provisioned yet.")
        else:
            st.dataframe(
                overview_df.rename(
                    columns={
                        "id": "Tenant ID",
                        "name": "Company",
                        "slug": "Slug",
                        "status": "Status",
                        "tier_code": "Tier",
                        "station_limit": "Station Limit",
                        "employee_limit": "Employee Limit",
                        "camera_limit": "Camera Limit",
                        "company_admin": "Company Admin",
                        "region_count": "Regions",
                        "station_count": "Stations",
                        "user_count": "Users",
                    }
                ),
                hide_index=True,
                use_container_width=True,
            )
    finally:
        platform_conn.close()
