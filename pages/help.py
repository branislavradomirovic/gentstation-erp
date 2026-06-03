import streamlit as st

from core.comm_service import send_support_email
from ui.header import render_page_header


def _help_topics():
    return [
        {
            "category": "Overview & Submission",
            "title": "Telegram Video Submission",
            "summary": "Employees submit station videos through Telegram, and the AI worker processes them into operational reports.",
            "details": [
                "Link the employee record to Telegram before expecting uploads to be accepted.",
                "Employees can send a video directly to the bot as a normal Telegram upload or document.",
                "The system stores the media temporarily, creates a submission row, and sends it to the AI queue.",
                "After processing finishes, the uploader receives a Telegram status reply and managers can review the result in AI Reports.",
            ],
            "tips": [
                "Keep videos short and focused on one station area at a time for the most useful AI output.",
                "If Telegram compresses the clip too heavily, resend it as a file upload instead of a chat video.",
            ],
        },
        {
            "category": "Overview & Submission",
            "title": "Dashboard",
            "summary": "Dashboard is the quickest way to understand network health, queue pressure, and where risk is building.",
            "details": [
                "Use the top metrics to understand network size, reporting volume, and current queue load.",
                "Regional status highlights which parts of the network have the most pending work.",
                "Merchandising and risk panels summarize operational quality without opening individual reports.",
                "This should be the first page reviewed after login for a broad operational picture.",
            ],
            "tips": [
                "Move to AI Reports when a dashboard number needs explanation.",
                "Open Map View when you want to understand whether an issue is isolated or geographically clustered.",
            ],
        },
        {
            "category": "Network Administration",
            "title": "Regions",
            "summary": "Regions define the business hierarchy used for permissions, reporting, and executive rollups.",
            "details": [
                "Create one region for each real operational territory.",
                "Keep region ownership and contact details current so escalation paths stay accurate.",
                "Regions control how station data rolls up into manager-facing views.",
            ],
            "tips": [
                "Use concise region names so analytics and dropdowns stay easy to scan.",
                "Assign region structure before bulk-loading stations whenever possible.",
            ],
        },
        {
            "category": "Network Administration",
            "title": "Stations",
            "summary": "Stations hold the core operational definition of each site, including category, location, and reporting context.",
            "details": [
                "Store the correct region, category, address, and map coordinates for each station.",
                "Station detail views are the best place to review site-specific report history.",
                "Managers use stations as the anchor point for alerts, reports, and escalation.",
            ],
            "tips": [
                "Verify map coordinates carefully, because location views depend on them.",
                "Review a station's recent AI history before changing category or operational ownership.",
            ],
        },
        {
            "category": "Network Administration",
            "title": "Employees",
            "summary": "Employees manages who can submit videos, who receives alerts, and which station each person represents.",
            "details": [
                "Assign every employee to the correct role and station before activating reporting.",
                "Keep Telegram linkage accurate so uploads and AI completion replies reach the right person.",
                "This page is also where password resets and account activation are controlled.",
            ],
            "tips": [
                "If someone moves to a new station, update their assignment before the next reporting cycle.",
                "Unlinked Telegram profiles are a common cause of failed intake or missing replies.",
            ],
        },
        {
            "category": "Dashboards & AI",
            "title": "Map View",
            "summary": "Map View combines station geography with queue pressure and recent activity.",
            "details": [
                "Station border color reflects workload pressure, while inner marker color reflects station category.",
                "Use the map to see whether recent reporting spikes are isolated or regional.",
                "Recent activity overlays help managers confirm that reporting is happening where expected.",
            ],
            "tips": [
                "Use this view during escalations when geography matters as much as score quality.",
                "If a station is missing, confirm that coordinates were entered in the station record.",
            ],
        },
        {
            "category": "Dashboards & AI",
            "title": "AI Reports",
            "summary": "AI Reports is the main review surface for queue status, report quality, risk scoring, and corrective actions.",
            "details": [
                "The Queue tab shows what is pending, processing, inconsistent, or failed.",
                "The Trends tab shows rolling risk patterns across stations.",
                "Completed Reports expose executive summary, overall risk, hazards, improvement actions, and station/region/company risk context.",
                "This is the primary page for turning uploaded footage into management decisions.",
            ],
            "tips": [
                "Use re-queue only for legitimate processing failures, not for normal completed rows.",
                "Compare station risk with region and company risk to decide whether an issue is local or systemic.",
            ],
        },
        {
            "category": "Dashboards & AI",
            "title": "AI Alerts",
            "summary": "AI Alerts highlights the most urgent findings that need human attention.",
            "details": [
                "Alerts are designed to surface high-risk or abnormal station conditions quickly.",
                "Managers can review, acknowledge, and resolve alerts as part of their operating routine.",
                "The alert feed complements AI Reports by reducing the need to inspect every report manually.",
            ],
            "tips": [
                "Repeated alerts at one station usually indicate a training or process problem, not a one-off event.",
                "Open the related AI report before resolving an alert so the context is preserved.",
            ],
        },
        {
            "category": "Dashboards & AI",
            "title": "AI Monitoring",
            "summary": "AI Monitoring is the operational screen for worker health, throughput, and service diagnostics.",
            "details": [
                "Use this page to confirm the AI worker, Telegram bot, Redis, and AI service are alive.",
                "It is the right place for deep operational troubleshooting when queue behavior looks wrong.",
                "Managers should rely on this page during rollout, recovery, or production testing.",
            ],
            "tips": [
                "If uploads are not moving, check AI Monitoring before changing settings.",
                "A healthy AI service with a stale worker usually points to process restart or deployment drift.",
            ],
        },
        {
            "category": "System Administration",
            "title": "Settings",
            "summary": "Settings centralizes production-ready controls for service health, BakLLaVA runtime policy, categories, and retention.",
            "details": [
                "Use Settings for password updates, dark mode, service health review, AI runtime memory limits, and staffing defaults.",
                "Station category administration lives here because it affects maps and reporting views across the app.",
                "Storage controls are intentionally limited to retention and visibility, keeping the page operational rather than technical.",
            ],
            "tips": [
                "If BakLLaVA is marked degraded, confirm the configured model exists in Ollama before testing uploads.",
                "This page is no longer a development toolbox; use AI Monitoring for deeper diagnostics.",
            ],
        },
        {
            "category": "System Administration",
            "title": "Admin Users & Audit Log",
            "summary": "These pages support security, accountability, and controlled operations.",
            "details": [
                "Admin Users controls account activation, lockouts, and maintenance-mode access.",
                "Audit Log provides a trace of key user actions and operational changes.",
                "Together, they give administrators the controls needed to manage access and understand what changed in the system.",
            ],
            "tips": [
                "Keep the number of high-privilege accounts small.",
                "Use Audit Log whenever you need to understand whether an issue came from a user action or an automated process.",
            ],
        },
    ]


def _render_topic(topic):
    st.markdown(f"### {topic['title']}")
    st.caption(topic["summary"])
    st.markdown("**How It Works**")
    for item in topic["details"]:
        st.markdown(f"- {item}")
    st.markdown("**Practical Tips**")
    for tip in topic["tips"]:
        st.markdown(f"- {tip}")


def render(conn):
    render_page_header("❓ Help & Documentation")
    st.markdown(
        '<div class="gs-page-intro">This guide is written for the current production-focused application: video intake through Telegram, AI assessment with BakLLaVA, and manager review through reports, alerts, and dashboards.</div>',
        unsafe_allow_html=True,
    )

    topics = _help_topics()
    search_query = st.text_input(
        "Search Help",
        placeholder="Type keywords like telegram, station, risk, alert, or settings",
    ).strip()

    if search_query:
        st.markdown("#### Search Results")
        found_any = False
        for item in topics:
            haystack = " ".join(
                [
                    item["category"],
                    item["title"],
                    item["summary"],
                    " ".join(item["details"]),
                    " ".join(item["tips"]),
                ]
            )
            if search_query.lower() in haystack.lower():
                found_any = True
                with st.expander(f"{item['category']} • {item['title']}", expanded=True):
                    _render_topic(item)
        if not found_any:
            st.warning("No matching help topic was found.")
        return

    tab_names = [
        "Overview & Submission",
        "Network Administration",
        "Dashboards & AI",
        "System Administration",
        "Contact Support",
    ]
    category_map = {
        "Overview & Submission": "Overview & Submission",
        "Network Administration": "Network Administration",
        "Dashboards & AI": "Dashboards & AI",
        "System Administration": "System Administration",
    }

    target_tab_name = st.session_state.pop("help_target_tab", "Overview & Submission")
    target_tab_name = {
        "Overview & submission": "Overview & Submission",
        "Management Modules": "Network Administration",
        "Dashboards & Reporting": "Dashboards & AI",
        "System Administration": "System Administration",
    }.get(target_tab_name, target_tab_name)

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
        st.markdown("#### Support Guidance")
        st.markdown(
            "When reporting a problem, include the page name, what you expected to happen, what actually happened, and whether the issue affects uploads, AI scoring, or visibility in reports."
        )
        contact_col1, contact_col2 = st.columns(2, gap="large")
        with contact_col1:
            st.markdown("**Support Contacts**")
            st.markdown(
                "- Office: `office@opus.rs`\n- Support: `support@opus.rs`\n- General inquiries: `+381641323706`"
            )
        with contact_col2:
            st.markdown("**Address**")
            st.markdown("Nikolajevska 2\n\nNovi Sad, 21000\n\nSerbia")

        st.divider()
        st.markdown("#### Send a Support Request")
        with st.form("support_form", clear_on_submit=True):
            subject = st.text_input("Subject")
            message = st.text_area("Message", height=160)
            if st.form_submit_button("Send Email to Support", width="stretch"):
                if not subject or not message:
                    st.error("Please provide both a subject and a message.")
                else:
                    current_user = st.session_state.get("username", "Unknown User")
                    if send_support_email(
                        from_user=current_user, subject=subject, message=message
                    ):
                        st.success("Your support request has been sent.")
        return

    filtered_items = [
        item for item in topics if item["category"] == category_map[selected_tab]
    ]

    if selected_tab == "Overview & Submission":
        st.markdown("#### Operating Flow")
        st.markdown(
            "Start here if you want to understand how video moves from Telegram intake into AI scoring and management review."
        )
    elif selected_tab == "Network Administration":
        st.markdown("#### Network Setup")
        st.markdown(
            "These topics explain how to maintain the core business structure that supports AI reporting."
        )
    elif selected_tab == "Dashboards & AI":
        st.markdown("#### Analysis & Action")
        st.markdown(
            "These pages turn uploads into operational insight, risk scoring, and actionable follow-up."
        )
    elif selected_tab == "System Administration":
        st.markdown("#### Administration")
        st.markdown(
            "These controls are for service readiness, access governance, and production operations."
        )

    st.divider()
    for index, item in enumerate(filtered_items):
        with st.expander(item["title"], expanded=index == 0):
            _render_topic(item)
