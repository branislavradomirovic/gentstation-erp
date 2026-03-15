import streamlit as st
from ui.header import render_page_header
from core.comm_service import send_support_email

def render(conn):
    render_page_header("❓ Help & Documentation")
    st.markdown("Welcome to the **GentStation Opus ERP** help center. Below you will find detailed guides on how to use every feature of the application.")
    
    # --- 1. HELP CONTENT DATABASE ---
    # Structured data allows for searching and dynamic rendering
    help_data = [
        {
            "category": "Overview & submission",
            "title": "📱 Video Submission (Telegram Bot)",
            "content": """The core of GentStation AI is the automated video analysis pipeline.
            
            1.  **Registration**: When an employee is registered, they receive a **Telegram Deep Link**.
            2.  **Linking**: Clicking the link opens the Telegram bot and links their Telegram account to their Employee ID.
            3.  **Submission**: Employees send video clips (CCTV footage, inspection videos) directly to the bot.
            4.  **Processing**: The AI Engine analyzes the video for **Cleanliness**, **Safety**, **Staff Behavior**, and **Merchandising**.
            5.  **Reporting**: Results appear in the **AI Reports** and **Dashboard** within minutes."""
        },
        {
            "category": "Overview & submission",
            "title": "🏠 Dashboard",
            "content": """The landing page for all users.
            - **KPI Cards**: Shows total regions, stations, employees, and pending video submissions.
            - **Regional Status**: A table showing pending tasks per region.
            - **Map Overview**: Interactive map showing station locations and recent activity (red pulses).
            - **Recent Activity**: A log of the latest system actions (logins, updates)."""
        },
        {
            "category": "Management Modules",
            "title": "🌍 Regions",
            "content": """**Access**: General Manager
            - **Create Region**: Add new operational territories.
            - **Edit/Delete**: Modify region names or remove them.
            - **Assign Manager**: Link a 'Region Manager' employee to a specific region."""
        },
        {
            "category": "Management Modules",
            "title": "⛽ Stations",
            "content": """**Access**: GM, Region Director, Region Manager
            - **Create Station**: Use the map to pin a location, name the station, and assign it to a region.
            - **Edit Station**: Update address, manager, or move the map pin.
            - **Daily Trends**: View a bar chart of video submissions for the current month.
            - **Delete**: Remove a station (only if no critical data is linked)."""
        },
        {
            "category": "Management Modules",
            "title": "👥 Employees",
            "content": """**Access**: General Manager
            - **Register**: Create new employee records. 
              - *Note*: Creating an employee automatically generates a **System User** login for them.
            - **Roles**: Assign specific access levels (e.g., Gas Station Manager, Region Director).
            - **Telegram Link**: View status of Telegram bot connection.
            - **Reset Password**: Generate a new temporary password and resend the welcome email."""
        },
        {
            "category": "Dashboards & Reporting",
            "title": "🗺️ Map View",
            "content": """**Access**: Managers & Directors
            - **Live Status**: Stations are colored by pending submission count (Green=OK, Orange=Pending, Red=High Volume).
            - **High Risk Layer**: Toggle the 'High Risk Alerts' layer to see AI-detected safety violations on the map.
            - **Navigation**: Click a station marker to jump to its details/edit page."""
        },
        {
            "category": "Dashboards & Reporting",
            "title": "📈 AI Reports",
            "content": """**Access**: All Managers
            - **Feed**: A chronological list of AI-generated reports from video submissions.
            - **Scores**: View granular scores (1-10) for Safety, Cleanliness, Staff, etc.
            - **Filtering**: Automatically filters based on your role (e.g., Station Managers only see their station)."""
        },
        {
            "category": "Dashboards & Reporting",
            "title": "📊 GM Dashboard",
            "content": """**Access**: General Manager
            - **Executive KPIs**: High-level stats on network health and safety.
            - **Risk Ranking**: A sorted list of stations from highest to lowest risk based on AI metrics.
            - **Risk Heatmap**: Visual density map of high-risk locations.
            - **Anomalies**: Recent alerts triggered by significant deviations in metrics."""
        },
        {
            "category": "System Administration",
            "title": "👤 Admin Users",
            "content": """**Access**: General Manager
            - **User Management**: Create/Edit/Deactivate system login accounts.
            - **Lockouts**: Unlock users who have failed login attempts too many times.
            - **Maintenance Mode**: A toggle to lock the system for non-admins during updates."""
        },
        {
            "category": "System Administration",
            "title": "🛡️ Audit Log",
            "content": """**Access**: General Manager
            - **Traceability**: View a filterable history of who did what and when.
            - **Filters**: Search by username, action type, or date range."""
        },
        {
            "category": "System Administration",
            "title": "⚙️ Settings",
            "content": """**Access**: All Users
            - **Profile**: Change your own login password."""
        },
        {
            "category": "Contact Support",
            "title": "Contact Information",
            "content": """
            **Address:**  
            Nikolajevska 2  
            Novi Sad, 21000  
            Serbia

            **Customer Care:**  
            <office@opus.rs>

            **Support:**  
            <support@opus.rs>

            **General Inquiries:**  
            +381641323706
            """
        }
    ]

    # --- 2. SEARCH BAR ---
    search_query = st.text_input("🔍 Search Documentation", placeholder="Type keywords (e.g., 'telegram', 'risk')...").strip()

    if search_query:
        st.subheader(f"Search Results for '{search_query}'")
        found_any = False
        for item in help_data:
            if search_query.lower() in item['title'].lower() or search_query.lower() in item['content'].lower():
                found_any = True
                with st.expander(f"{item['category']} > {item['title']}", expanded=True):
                    st.markdown(item['content'])
        
        if not found_any:
            st.warning("No matching documentation found.")
            if st.button("Clear Search"):
                st.rerun()

    else:
        # --- 3. CATEGORY NAVIGATION ---
        tab_names = ["Overview & submission", "Management Modules", "Dashboards & Reporting", "System Administration", "Contact Support"]
        
        # Check for a target tab from another page and set the default index for the radio button
        target_tab_name = st.session_state.pop("help_target_tab", tab_names[0])
        default_index = 0
        if target_tab_name in tab_names:
            default_index = tab_names.index(target_tab_name)

        selected_tab = st.radio(
            "Help Topics",
            options=tab_names,
            index=default_index,
            horizontal=True,
            label_visibility="collapsed"
        )
        
        st.divider()

        # Special handling for Contact Support tab
        if selected_tab == "Contact Support":
            st.header("Contact & Support")
            
            # Display static info
            info_item = next((item for item in help_data if item['title'] == "Contact Information"), None)
            if info_item:
                st.markdown(info_item['content'])
            
            st.divider()
            
            # Display form
            st.subheader("Send a Support Request")
            with st.form("support_form", clear_on_submit=True):
                subject = st.text_input("Subject")
                message = st.text_area("Your Message", height=150)
                
                if st.form_submit_button("Send Email to Support"):
                    if not subject or not message:
                        st.error("Please provide a subject and a message.")
                    else:
                        current_user = st.session_state.get("username", "Unknown User")
                        if send_support_email(from_user=current_user, subject=subject, message=message):
                            st.success("Your message has been sent. Our support team will get back to you shortly.")
                            st.toast("Support request sent!", icon="✅")
        else:
            # Render items for the selected category
            filtered_items = [item for item in help_data if item['category'] == selected_tab]
            
            # Formatting headers
            if selected_tab == "Overview & submission":
                st.header("Getting Started")
            elif selected_tab == "Management Modules":
                st.header("Operational Management")
            elif selected_tab == "Dashboards & Reporting":
                st.header("Analytics & Insights")
            elif selected_tab == "System Administration":
                st.header("Administration")
        
            for item in filtered_items:
                # Overview items are shown directly, others in expanders
                if selected_tab == "Overview & submission":
                    st.markdown(f"### {item['title']}")
                    st.markdown(item['content'])
                    st.divider()
                else:
                    with st.expander(item['title']):
                        st.markdown(item['content'])