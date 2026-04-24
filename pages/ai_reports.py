# gentstation_opus/pages/ai_reports.py
import streamlit as st
import pandas as pd
import json
from ui.header import render_page_header

def get_employee_id_from_user_id(conn, user_id):
    """Helper to get employees.id from users.id for permission scoping."""
    emp_row = conn.execute("""
        SELECT e.id 
        FROM employees e
        JOIN users u ON e.email = u.username
        WHERE u.id = %s
    """, (user_id,)).fetchone()
    return emp_row[0] if emp_row else None


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

def render(conn):
    render_page_header("📈 AI Reports & Processing Queue")

    role = st.session_state.user_role
    user_id = st.session_state.user_id
    employee_id = get_employee_id_from_user_id(conn, user_id)

    # --- Build the base WHERE clause with role-based filtering ---
    where_clause = ""
    params = []

    if role == "Region Director":
        if employee_id:
            regs = conn.execute("SELECT region_id FROM director_regions WHERE employee_id = %s", (employee_id,)).fetchall()
            region_ids = [r[0] for r in regs]
            if region_ids:
                # Use %s placeholders for psycopg2
                placeholder = ",".join(["%s"]*len(region_ids))
                where_clause = f"AND st.region_id IN ({placeholder})"
                params = region_ids
            else: where_clause = "AND 1=0" # No regions assigned
    elif role == "Region Manager":
        if employee_id:
            region_id_row = conn.execute("SELECT region_id FROM employees WHERE id = %s", (employee_id,)).fetchone()
            if region_id_row:
                where_clause = "AND st.region_id = %s"
                params = [region_id_row[0]]
            else: where_clause = "AND 1=0"
    elif role == "Gas Station Manager":
        if employee_id:
            station_id_row = conn.execute("SELECT station_id FROM employees WHERE id = %s", (employee_id,)).fetchone()
            if station_id_row:
                where_clause = "AND s.station_id = %s"
                params = [station_id_row[0]]
            else: where_clause = "AND 1=0"
    elif role != "General Manager":
        where_clause = "AND 1=0" # Other roles see nothing

    # --- 1. Display Pending & Failed Submissions ---
    st.subheader("Processing Queue")
    
    queue_query = f"""
        SELECT 
            s.id, s.timestamp, st.name as station_name, 
            e.name || ' ' || e.surname as employee_name, s.processed
        FROM submissions s
        JOIN stations st ON s.station_id = st.id
        JOIN employees e ON s.employee_id = e.id
        WHERE s.processed IN (0, -1) {where_clause}
        ORDER BY s.timestamp DESC
    """
    queue_df = pd.read_sql_query(queue_query, conn, params=params)

    if queue_df.empty:
        st.info("No pending or failed submissions in the queue for your scope.")
    else:
        queue_df['status'] = queue_df['processed'].map({0: 'Pending', -1: 'Failed'})
        st.dataframe(queue_df[['id', 'timestamp', 'station_name', 'employee_name', 'status']], width="stretch", hide_index=True)

        failed_submissions = queue_df[queue_df['processed'] == -1]
        if not failed_submissions.empty:
            st.markdown("---")
            st.write("#### Retry Failed Submissions")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                selected_id = st.selectbox("Select a failed submission ID to retry:", options=failed_submissions['id'].tolist())
            with col2:
                st.write("") # for vertical alignment
                if st.button("🔄 Retry Selected Submission", type="primary", width="stretch"):
                    if selected_id:
                        conn.execute("UPDATE submissions SET processed = 0 WHERE id = %s", (selected_id,))
                        conn.commit()
                        st.success(f"Submission ID {selected_id} has been re-queued for processing.")
                        st.toast("Task re-queued!", icon="🔄")
                        st.rerun()

    st.divider()
    
    # --- 1.5 Safety Analytics Chart (Last 30 Days) ---
    st.subheader("📊 30-Day Safety Trends (Average by Station)")
    
    analytics_query = f"""
        SELECT 
            st.name as "Station", 
            AVG(CAST(s.data_json->>'safety_score' AS REAL)) as "Average Safety Score"
        FROM submissions s
        JOIN stations st ON s.station_id = st.id
        WHERE s.processed = 1 
          AND s.data_json IS NOT NULL
          AND s.timestamp >= NOW() - INTERVAL '30 days'
          {where_clause}
        GROUP BY st.id
        ORDER BY "Average Safety Score" ASC
    """
    analytics_df = pd.read_sql_query(analytics_query, conn, params=params)
    
    if not analytics_df.empty:
        station_col = _resolve_column(analytics_df, "Station", "station", "station_name")
        score_col = _resolve_column(analytics_df, "Average Safety Score", "average safety score")
        if station_col and score_col:
            chart_df = analytics_df.rename(columns={station_col: "Station", score_col: "Average Safety Score"})
            st.bar_chart(chart_df.set_index("Station"))
        else:
            st.caption("Analytics data is available, but expected columns are missing.")
    else:
        st.caption("No analytics data available for the last 30 days.")

    st.divider()

    # --- 2. Display Processed AI Reports ---
    st.subheader("Completed Reports")
    
    completed_query = f"""
        SELECT 
            s.id, s.timestamp, st.name as "Station", s.data_json as kpi_json
        FROM submissions s
        JOIN stations st ON s.station_id = st.id
        WHERE s.processed = 1 AND s.data_json IS NOT NULL {where_clause}
        ORDER BY s.timestamp DESC LIMIT 200
    """
    df = pd.read_sql_query(completed_query, conn, params=params)

    if df.empty:
        st.info("No completed AI reports available for your scope.")
    else:
        def extract_from_json(json_str, key, default=None):
            data = _ensure_dict(json_str)
            return data.get(key, default)

        df['safety_score'] = df['kpi_json'].apply(lambda x: extract_from_json(x, 'safety_score'))
        df['cleanliness_score'] = df['kpi_json'].apply(lambda x: extract_from_json(x, 'cleanliness_score'))
        df['staff_score'] = df['kpi_json'].apply(lambda x: extract_from_json(x, 'staff_score'))
        df['merchandising_score'] = df['kpi_json'].apply(lambda x: extract_from_json(x, 'merchandising_score'))
        station_col = _resolve_column(df, "Station", "station", "station_name")
        timestamp_col = _resolve_column(df, "timestamp", "Timestamp")
        if station_col and station_col != "Station":
            df["Station"] = df[station_col]
        if timestamp_col and timestamp_col != "timestamp":
            df["timestamp"] = df[timestamp_col]

        st.dataframe(
            df[['timestamp', 'Station', 'safety_score', 'cleanliness_score', 'staff_score', 'merchandising_score']],
            width="stretch",
            hide_index=True
        )
        
        if not df.empty:
            idx = st.selectbox("Select report ID to preview details", df['id'].tolist())
            if idx:
                row = df[df['id']==idx].iloc[0]
                st.subheader(f"Report Details for Submission #{idx}")
                st.write(f"**Station:** {row['Station']} | **Submitted:** {row['timestamp']}")
                
                kpi_data = _ensure_dict(row['kpi_json'])
                if kpi_data:
                    st.write(f"**Summary:** {kpi_data.get('summary', 'N/A')}")
                    st.json(kpi_data)
                else:
                    st.warning("No detailed KPI data available for this report.")
