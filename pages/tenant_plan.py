import streamlit as st

from core.subscription import (
    RESOURCE_CAMERAS,
    RESOURCE_EMPLOYEES,
    RESOURCE_STATIONS,
    TIER_2_CCTV_INTELLIGENCE,
    build_plan_summary,
)
from ui.header import render_page_header


def _format_limit(limit_value):
    return "Unlimited" if limit_value is None else str(limit_value)


def render(conn):
    render_page_header("📦 Tenant Plan")
    st.markdown(
        '<div class="gs-page-intro">Review your active service tier, operational limits, and the features available to this tenant before enabling new workflows.</div>',
        unsafe_allow_html=True,
    )

    summary = build_plan_summary(conn)
    snapshot = summary["snapshot"]
    tier = summary["tier"]
    usage = summary["usage"]
    limits = summary["limits"]
    features = summary["features"]

    tier_col, status_col, billing_col = st.columns(3)
    tier_col.metric("Current Tier", tier.label)
    status_col.metric("Subscription Status", str(snapshot.status).title())
    billing_col.metric(
        "Billing Cycle",
        (snapshot.billing_cycle or "Not set").title(),
    )

    st.caption(tier.description)
    st.divider()

    st.markdown("#### Usage & Limits")
    usage_cols = st.columns(3)
    usage_specs = [
        ("Stations", RESOURCE_STATIONS),
        ("Users", RESOURCE_EMPLOYEES),
        ("Cameras", RESOURCE_CAMERAS),
    ]
    for col, (label, key) in zip(usage_cols, usage_specs):
        col.metric(
            label,
            usage.get(key, 0),
            f"Plan limit: {_format_limit(limits.get(key))}",
        )

    st.divider()
    st.markdown("#### Included Features")
    for feature in features.values():
        with st.container(border=True):
            badge = "Enabled" if feature["enabled"] else "Upgrade required"
            st.markdown(f"**{feature['label']}**")
            st.caption(feature["description"])
            st.write(badge)

    if snapshot.tier_code != TIER_2_CCTV_INTELLIGENCE:
        st.info(
            "CCTV Intelligence is reserved for Tier 2 tenants. Upgrade before enabling CCTV routes, camera capacity, or future CCTV worker workflows."
        )
