import streamlit as st
import pandas as pd
from io import BytesIO
from ui.header import render_page_header
from core.data_import import process_station_import
from core.activity_logger import log_activity

def render(conn):
    render_page_header("📤 Bulk Data Import")
    st.markdown("Import large datasets for Stations and Regions using CSV files.")

    # --- 1. DOWNLOAD TEMPLATE ---
    st.subheader("1. Download Template")
    template_df = pd.DataFrame(columns=[
        "name", "region_id", "physical_address", "email", "lat", "lon"
    ])
    template_df.loc[0] = ["Example Station", 1, "123 Main St", "station@example.com", 44.21, 20.92]

    csv_buffer = BytesIO()
    template_df.to_csv(csv_buffer, index=False)

    st.download_button(
        label="📥 Download Stations CSV Template",
        data=csv_buffer.getvalue(),
        file_name="gentstation_template_stations.csv",
        mime="text/csv"
    )

    st.divider()

    # --- 2. UPLOAD & PROCESS ---
    st.subheader("2. Upload & Process")
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

    if uploaded_file is not None:
        if st.button("🚀 Start Bulk Import", type="primary", width="stretch"):
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(pct):
                progress_bar.progress(pct)
                status_text.text(f"Processing... {int(pct*100)}%")

            # Process the import
            results = process_station_import(uploaded_file, progress_callback=update_progress)

            # Log the action
            log_activity(conn, "BULK_IMPORT", f"Imported {results['success']} stations from CSV")

            # Display results
            if results["success"] > 0:
                st.success(f"✅ Successfully imported {results['success']} of {results['total']} stations.")
                st.balloons()

            if results["errors"]:
                with st.expander(f"⚠️ Encountered {len(results['errors'])} issues", expanded=True):
                    for err in results["errors"][:50]: # Show first 50 errors
                        st.error(err)
                    if len(results['errors']) > 50:
                        st.info("... and more errors. Please check your data format.")

    st.divider()
    st.info("""
    💡 **Best Practices for Bulk Import:**
    - Ensure `region_id` matches existing IDs in the Regions table.
    - Coordinates (Lat/Lon) should be in decimal format.
    - Larger files (10,000+ rows) are processed in chunks to ensure system stability.
    """)
