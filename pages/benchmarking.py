import streamlit as st
import pandas as pd
try:
    import plotly.express as px
except ImportError:
    px = None

from sqlalchemy import select
from core.cctv_reports import get_region_benchmark_rows, get_station_benchmark_rows
from core.database import get_session
from core.models import CCTVMetricHourly, Region
from ui.header import render_page_header
from core.subscription import FEATURE_CCTV_INTELLIGENCE, require_feature
from core.tenant_context import current_tenant_id

def render(conn):
    # 1. Permission Check
    require_feature(conn, FEATURE_CCTV_INTELLIGENCE)
    render_page_header("📊 Performance Benchmarking")

    st.markdown(
        '<div class="gs-page-intro">Compare station and regional performance metrics across your network. Identify top performers and sites requiring operational support based on CCTV intelligence.</div>',
        unsafe_allow_html=True,
    )

    if not px:
        st.error("Plotly is required for benchmarking charts. Please install it.")
        return

    tenant_id = current_tenant_id()
    with get_session() as session:
        # 2. Global Filters
        metric_keys = session.execute(
            select(CCTVMetricHourly.metric_key).distinct()
        ).scalars().all()

        if not metric_keys:
            st.info("📡 No CCTV metrics available yet. Rankings will appear once the CCTV Worker processes footage.")
            return

        c1, c2, c3 = st.columns(3)
        selected_metric = c1.selectbox(
            "Metric to Compare",
            metric_keys,
            format_func=lambda x: x.replace("count_", "").replace("_", " ").title()
        )

        regions = session.execute(select(Region.name)).scalars().all()
        selected_region = c2.selectbox("Region Filter", ["All Regions"] + regions)

        # 3. Rank Query
        results = get_station_benchmark_rows(
            session,
            tenant_id,
            selected_metric,
            region_name=selected_region,
        )
        df = pd.DataFrame(results, columns=["Station", "Value", "Confidence"])

        if df.empty:
            st.warning("No data found for the selected criteria.")
            return

        # 4. Visualization
        st.subheader(f"Station Ranking: {selected_metric.replace('count_', '').replace('_', ' ').title()}")

        fig = px.bar(
            df[["Station", "Value"]],
            x="Station",
            y="Value",
            color="Value",
            color_continuous_scale="Blues",
            labels={"Value": "Metric Total", "Station": "Gas Station"},
            template="plotly_white"
        )
        st.plotly_chart(fig, use_container_width=True)
        avg_confidence = round(
            sum(float(row[2] or 0) for row in results) / len(results),
            2,
        ) if results else 0.0
        st.caption(f"Average model confidence for this ranking: {avg_confidence:.2f}")

        # 5. Regional Rollup
        st.divider()
        st.subheader("Regional Market Share")
        reg_df = pd.DataFrame(
            get_region_benchmark_rows(session, tenant_id, selected_metric),
            columns=["Region", "Value", "Confidence"],
        )
        st.plotly_chart(px.pie(reg_df, values='Value', names='Region', hole=.4), use_container_width=True)
