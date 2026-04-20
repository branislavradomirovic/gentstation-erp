from pathlib import Path

import streamlit as st

from core.comm_service import send_support_email
from ui.header import render_page_header

HELP_IMAGE_DIR = Path(__file__).resolve().parents[1] / "assets"


def _help_topics():
    return [
        {
            "category": "Overview & submission",
            "title": "Telegram Video Submission",
            "summary": "Employees link their chat, send video clips, and the AI worker queues them for inspection.",
            "details": [
                "Use the registration link sent by email to connect the Telegram chat to the employee record.",
                "Send a video as either a Telegram video message or a file/document upload.",
                "The bot stores the file, writes a new submission row, and marks it as pending for AI analysis.",
                "Once the AI worker finishes, the results appear in AI Reports, the Dashboard, and any relevant alert feeds.",
            ],
            "tips": [
                "If a video is not accepted, resend it as an MP4 file to avoid Telegram compression issues.",
                "For the best results, keep clips short and focused on one station area at a time.",
            ],
            "screenshots": [
                {"file": "LogIn.png", "label": "Application login screen"},
                {"file": "Screenshot 2026-04-18 at 16.54.56.png", "label": "Employee directory and Telegram-linked profiles"},
                {"file": "Screenshot 2026-04-18 at 16.54.46.png", "label": "Station audit history and QR onboarding"},
            ],
        },
        {
            "category": "Overview & submission",
            "title": "Dashboard",
            "summary": "The main landing page shows KPIs, station health, recent activity, and a quick view of open work.",
            "details": [
                "KPI cards summarize the most important numbers for the current session.",
                "Regional and station status sections highlight where work is pending or where risk is building up.",
                "The map and recent activity panels help managers spot changes without drilling into every module.",
                "This is usually the best first stop after login because it gives the fastest operational snapshot.",
            ],
            "tips": [
                "Use Dashboard when you want a quick sense of whether the network is stable or under pressure.",
                "If a metric looks wrong, jump to AI Reports or GM Dashboard to inspect the underlying data.",
            ],
            "screenshots": [
                {"file": "Screenshot 2026-04-18 at 16.53.28.png", "label": "Dashboard KPI summary and station overview"},
                {"file": "Screenshot 2026-04-18 at 16.53.44.png", "label": "Dashboard map and operational layout"},
                {"file": "Screenshot 2026-04-18 at 16.54.26.png", "label": "Regional status and merchandising performance"},
            ],
        },
        {
            "category": "Management Modules",
            "title": "Regions",
            "summary": "General Managers use Regions to model the organization and assign responsibility boundaries.",
            "details": [
                "Create regions for each operational territory the company manages.",
                "Edit names, contact information, and ownership details as the organization changes.",
                "Use region assignments to keep stations and managers grouped correctly.",
                "The module is the foundation for reporting, access control, and executive rollups.",
            ],
            "tips": [
                "Keep region names consistent and short so the rest of the app remains easy to scan.",
                "Assign managers before adding stations if you want the hierarchy to stay clean from the start.",
            ],
            "screenshots": [
                {"file": "Screenshot 2026-04-18 at 16.54.03.png", "label": "Region directory"},
                {"file": "Screenshot 2026-04-18 at 16.54.10.png", "label": "Edit or delete a region"},
                {"file": "Screenshot 2026-04-18 at 16.54.14.png", "label": "Stations in the selected region"},
            ],
        },
        {
            "category": "Management Modules",
            "title": "Stations",
            "summary": "Stations stores the operational details for each site, including ownership, location, and QR onboarding.",
            "details": [
                "Add or edit station names, geographic coordinates, category, and regional assignment.",
                "Use the station detail view to review historical AI submissions and audit the performance trail.",
                "The QR code workflow helps employees connect quickly to the correct Telegram reporting bot.",
                "A station can also be linked to a manager for email notifications and escalation routing.",
            ],
            "tips": [
                "Double-check coordinates so map views and risk overlays render in the right location.",
                "The QR code is most useful when you are onboarding a new site or replacing a manager.",
            ],
            "screenshots": [
                {"file": "Screenshot 2026-04-18 at 16.54.20.png", "label": "Stations management list"},
                {"file": "Screenshot 2026-04-18 at 16.54.37.png", "label": "Edit or delete station"},
                {"file": "Screenshot 2026-04-18 at 16.54.46.png", "label": "Station audit history and QR code"},
            ],
        },
        {
            "category": "Management Modules",
            "title": "Employees",
            "summary": "Employees links personnel records to Telegram, station assignment, and reporting permissions.",
            "details": [
                "Create a record for each employee and assign the correct role immediately.",
                "When an employee is linked to Telegram, the bot can accept media from that chat and associate it with the correct station.",
                "Password reset and access updates are centralized here so the user profile stays synchronized with the system account.",
                "Use this module to control who can submit, view, or administer operational data.",
            ],
            "tips": [
                "If someone changes station, update the employee record before the next reporting cycle starts.",
                "Keeping email and Telegram fields accurate makes support and escalation much easier.",
            ],
            "screenshots": [
                {"file": "Screenshot 2026-04-18 at 16.54.56.png", "label": "Employees list and access state"},
                {"file": "Screenshot 2026-04-18 at 16.55.03.png", "label": "Edit or delete employee"},
            ],
        },
        {
            "category": "Management Modules",
            "title": "Shifts & Attendance",
            "summary": "Shifts lets managers schedule coverage per station and lets employees clock in and out from the same place.",
            "details": [
                "Managers can create scheduled shifts for a specific station and employee.",
                "Employees can clock in from their personal shift view when they start work and clock out when the shift ends.",
                "Each shift record stores the planned window, actual clock-in/out times, and optional notes for handover or coverage.",
                "Use this page whenever you need a clear coverage picture for a station or a personal work history for an employee.",
            ],
            "tips": [
                "Create the planned shift before the workday starts so the clock-in record stays tied to the correct station.",
                "If someone forgets to clock out, you can still audit the shift from the shift register.",
            ],
            "screenshots": [],
        },
        {
            "category": "Dashboards & Reporting",
            "title": "Map View",
            "summary": "The map shows where stations are located and helps managers spot geographic patterns at a glance.",
            "details": [
                "Color and marker state summarize operational status across the network.",
                "Use the map to compare nearby stations, identify clusters, and understand regional spread.",
                "The view is especially useful during incidents because it combines location context with operational urgency.",
            ],
            "tips": [
                "Zoom out for regional context, then zoom in to inspect a single station.",
                "Use the map with AI Alerts to understand whether risk is isolated or spreading.",
            ],
            "screenshots": [
                {"file": "Screenshot 2026-04-18 at 16.53.44.png", "label": "Station location map"},
            ],
        },
        {
            "category": "Dashboards & Reporting",
            "title": "AI Reports",
            "summary": "AI Reports is the inspection console for processed video submissions and score breakdowns.",
            "details": [
                "Pending submissions appear in the queue until the worker finishes analysis.",
                "Completed reports include the AI summary, numerical scores, and the JSON detail payload.",
                "Failed submissions can be retried from the page if a temporary processing issue occurred.",
                "Trend charts help managers see whether a station is improving or drifting over time.",
            ],
            "tips": [
                "Review AI Reports first when you want the raw evidence behind a dashboard metric.",
                "The JSON payload is useful when you need to compare two reports field by field.",
            ],
            "screenshots": [
                {"file": "Screenshot 2026-04-18 at 16.55.15.png", "label": "AI reports processing queue"},
                {"file": "Screenshot 2026-04-18 at 16.55.20.png", "label": "Retry failed submissions and trend charts"},
            ],
        },
        {
            "category": "Dashboards & Reporting",
            "title": "AI Alerts",
            "summary": "AI Alerts surfaces critical findings such as low scores, hazards, and station anomalies.",
            "details": [
                "Alerts are prioritized by severity so urgent issues stand out immediately.",
                "The alert feed is the best place to track unresolved incidents and operational exceptions.",
                "Alerts can be acknowledged or resolved depending on the operational workflow in use.",
            ],
            "tips": [
                "Use the alert feed after reviewing AI Reports if you need to act on something immediately.",
                "Treat repeated alerts at the same station as a sign that process or training may need attention.",
            ],
            "screenshots": [
                {"file": "Screenshot 2026-04-18 at 16.55.28.png", "label": "AI alerts and incidents"},
            ],
        },
        {
            "category": "Dashboards & Reporting",
            "title": "GM Dashboard",
            "summary": "The executive dashboard combines station ranking, risk concentration, and alert summaries.",
            "details": [
                "Risk ranking compares station outcomes so leaders can focus on the most exposed sites first.",
                "The executive map highlights clusters of higher risk across the network.",
                "Recent anomalies help the General Manager see where action is needed without reading every report.",
            ],
            "tips": [
                "Use GM Dashboard for leadership reviews, weekly status meetings, or escalations.",
                "If a station jumps into the top risk bucket, open AI Reports immediately to inspect the cause.",
            ],
            "screenshots": [
                {"file": "Screenshot 2026-04-18 at 16.55.35.png", "label": "Executive dashboard and KPI view"},
                {"file": "Screenshot 2026-04-18 at 16.55.39.png", "label": "Risk map and employee performance snapshot"},
                {"file": "Screenshot 2026-04-18 at 16.55.45.png", "label": "Employee performance snapshot and anomalies"},
            ],
        },
        {
            "category": "System Administration",
            "title": "Admin Users",
            "summary": "Admin Users controls login accounts, lockouts, and maintenance-mode access.",
            "details": [
                "Create system-level logins for staff who need direct application access.",
                "Deactivate, unlock, or reset access based on security policy and employment status.",
                "Maintenance mode protects the system during upgrades or emergency work.",
            ],
            "tips": [
                "Use the smallest number of admin accounts possible.",
                "Review locked accounts before assuming a password issue.",
            ],
            "screenshots": [
                {"file": "Screenshot 2026-04-18 at 16.55.58.png", "label": "Admin user management"},
            ],
        },
        {
            "category": "System Administration",
            "title": "Audit Log",
            "summary": "Audit Log records who changed what and when so actions remain traceable.",
            "details": [
                "The log is designed for accountability and troubleshooting.",
                "Use filters to find a specific user, action, or date range quickly.",
                "When investigating an issue, pair the audit trail with AI Reports and settings history.",
            ],
            "tips": [
                "Audit logs are most useful when you already know the time window or the user involved.",
                "If you cannot find an action, check whether it was performed by a background worker instead of a human user.",
            ],
            "screenshots": [
                {"file": "Screenshot 2026-04-18 at 16.56.03.png", "label": "System audit log"},
            ],
        },
        {
            "category": "System Administration",
            "title": "Settings",
            "summary": "Settings contains personal preferences plus live health indicators for the Telegram bot and AI worker.",
            "details": [
                "Users can change password and theme preferences from this page.",
                "The Telegram Bot and AI Worker status cards help you confirm the background services are alive.",
                "Force AI Processing is useful when you want the worker to run immediately instead of waiting for the next cycle.",
            ],
            "tips": [
                "If the bot status looks stale, restart the app and ensure only one polling process is running.",
                "When debugging, Settings is the fastest place to confirm whether the workers are actually online.",
            ],
            "screenshots": [
                {"file": "LogIn.png", "label": "Login and system status"},
            ],
        },
    ]


def _render_screenshot_card(image_path: Path, caption: str):
    if image_path.exists():
        st.image(str(image_path))
        st.caption(caption)
    else:
        st.markdown(
            f"""
            <div style="
                border:1px dashed rgba(120,130,150,0.35);
                border-radius:14px;
                padding:1rem;
                min-height:180px;
                background: linear-gradient(180deg, rgba(245,247,252,0.95), rgba(255,255,255,1));
            ">
                <strong>{caption}</strong><br><br>
                Screenshot not found yet.<br>
                Drop a PNG or JPG into <code>assets/help_screenshots</code> with the matching filename.
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_topic(topic):
    st.markdown(f"### {topic['title']}")
    st.caption(topic["summary"])

    col_text, col_media = st.columns([1.4, 1.0], gap="large")
    with col_text:
        st.markdown("**How it works**")
        for item in topic["details"]:
            st.markdown(f"- {item}")

        st.markdown("**Practical tips**")
        for tip in topic["tips"]:
            st.markdown(f"- {tip}")

    with col_media:
        st.markdown("**Visual guide**")
        if topic["screenshots"]:
            for shot in topic["screenshots"]:
                image_path = HELP_IMAGE_DIR / shot["file"]
                _render_screenshot_card(image_path, shot["label"])
                st.write("")
        else:
            st.info("No screenshot captured for this workflow yet.")


def _render_asset_gallery():
    st.markdown("### Asset Gallery")
    st.caption("These are the actual screenshots already stored in the `assets/` folder.")
    gallery_files = [
        ("LogIn.png", "Login screen"),
        ("Screenshot 2026-04-18 at 16.53.28.png", "Dashboard overview"),
        ("Screenshot 2026-04-18 at 16.53.44.png", "Map view"),
        ("Screenshot 2026-04-18 at 16.54.03.png", "Regions"),
        ("Screenshot 2026-04-18 at 16.54.20.png", "Stations"),
        ("Screenshot 2026-04-18 at 16.54.56.png", "Employees"),
        ("Screenshot 2026-04-18 at 16.55.15.png", "AI reports"),
        ("Screenshot 2026-04-18 at 16.55.28.png", "AI alerts"),
        ("Screenshot 2026-04-18 at 16.55.35.png", "GM dashboard"),
        ("Screenshot 2026-04-18 at 16.55.58.png", "Admin users"),
        ("Screenshot 2026-04-18 at 16.56.03.png", "Audit log"),
    ]
    cols = st.columns(2)
    for idx, (filename, caption) in enumerate(gallery_files):
        with cols[idx % 2]:
            _render_screenshot_card(HELP_IMAGE_DIR / filename, caption)
            st.write("")


def render(conn):
    render_page_header("❓ Help & Documentation")
    st.markdown(
        "Welcome to the **GentStation Opus ERP** help center. This page is organized around real workflows so you can move from setup to daily operations without hunting through the app."
    )

    topics = _help_topics()
    search_query = st.text_input("🔍 Search Documentation", placeholder="Type keywords like telegram, risk, settings, or stations").strip()

    if search_query:
        st.subheader(f"Search results for '{search_query}'")
        found_any = False
        for item in topics:
            haystack = " ".join([item["category"], item["title"], item["summary"], " ".join(item["details"]), " ".join(item["tips"])])
            if search_query.lower() in haystack.lower():
                found_any = True
                with st.expander(f"{item['category']} > {item['title']}", expanded=True):
                    _render_topic(item)

        if not found_any:
            st.warning("No matching documentation found.")
            if st.button("Clear Search", width="stretch"):
                st.rerun()
        return

    tab_names = ["Overview & submission", "Management Modules", "Dashboards & Reporting", "System Administration", "Contact Support"]
    target_tab_name = st.session_state.pop("help_target_tab", tab_names[0])
    default_index = tab_names.index(target_tab_name) if target_tab_name in tab_names else 0

    selected_tab = st.radio(
        "Help Topics",
        options=tab_names,
        index=default_index,
        horizontal=True,
        label_visibility="collapsed",
    )

    st.divider()

    if selected_tab == "Contact Support":
        st.header("Contact & Support")
        st.markdown(
            """
            If something looks wrong or a workflow is not behaving as expected, send the support team a short message with:

            - the page you were using,
            - what you expected to happen,
            - what actually happened,
            - and a screenshot if available.
            """
        )
        st.subheader("Support details")
        st.markdown(
            """
            **Address:**  
            Nikolajevska 2  
            Novi Sad, 21000  
            Serbia

            **Customer Care:**  
            office@opus.rs

            **Support:**  
            support@opus.rs

            **General Inquiries:**  
            +381641323706
            """
        )

        st.divider()
        st.subheader("Send a Support Request")
        with st.form("support_form", clear_on_submit=True):
            subject = st.text_input("Subject")
            message = st.text_area("Your Message", height=160)

            if st.form_submit_button("Send Email to Support", width="stretch"):
                if not subject or not message:
                    st.error("Please provide a subject and a message.")
                else:
                    current_user = st.session_state.get("username", "Unknown User")
                    if send_support_email(from_user=current_user, subject=subject, message=message):
                        st.success("Your message has been sent. Our support team will get back to you shortly.")
                        st.toast("Support request sent!", icon="✅")
        return

    with st.expander("Screenshot Gallery", expanded=False):
        _render_asset_gallery()

    filtered_items = [item for item in topics if item["category"] == selected_tab]

    if selected_tab == "Overview & submission":
        st.header("Getting Started")
        st.markdown(
            "This section explains how the Telegram bot, dashboard, and AI workers fit together. It is the fastest way to understand the end-to-end reporting flow."
        )
    elif selected_tab == "Management Modules":
        st.header("Operational Management")
        st.markdown("Use these modules to maintain the company structure, stations, and employee access.")
    elif selected_tab == "Dashboards & Reporting":
        st.header("Analytics & Insights")
        st.markdown("These pages help managers interpret the AI output, spot risk, and act on anomalies.")
    elif selected_tab == "System Administration":
        st.header("Administration")
        st.markdown("Use these tools when you need to manage access, review the audit trail, or check service health.")

    st.markdown("### Visual overview")
    gallery_topics = filtered_items[:2]
    if gallery_topics:
        gallery_cols = st.columns(len(gallery_topics))
        for col, topic in zip(gallery_cols, gallery_topics):
            with col:
                first_shot = topic["screenshots"][0] if topic["screenshots"] else None
                if first_shot:
                    _render_screenshot_card(HELP_IMAGE_DIR / first_shot["file"], first_shot["label"])
                else:
                    st.info("No screenshot configured for this section yet.")

    st.divider()
    for item in filtered_items:
        with st.expander(item["title"], expanded=selected_tab == "Overview & submission"):
            _render_topic(item)
