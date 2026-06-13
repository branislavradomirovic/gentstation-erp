import streamlit as st

from ui.header import render_page_header


def render(conn):
    del conn
    render_page_header("🎥 CCTV Intelligence")
    st.markdown(
        '<div class="gs-page-intro">This Tier 2 workspace is reserved for CCTV-specific intelligence flows, camera-aware worker pipelines, and future multi-camera analytics.</div>',
        unsafe_allow_html=True,
    )
    st.info(
        "Tier 2 is active for this tenant. Use this space for CCTV rollout tasks, camera onboarding, and future CCTV worker operations as they land."
    )
