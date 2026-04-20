GentStationAI - Project Overview

GentStationAI is an AI-powered gas station operations platform built by Opus Labs d.o.o. Novi Sad.
It combines role-based management, operational dashboards, AI video analysis, alerting, and audit controls to help multi-site fuel retail teams run safer and more consistent operations.

====================================================================
1) CORE PURPOSE
====================================================================

The app helps organizations:
- Monitor station performance across regions.
- Detect operational and safety risks earlier.
- Standardize supervision and follow-up actions.
- Improve accountability with traceable logs and role-based governance.


====================================================================
2) MAIN FEATURES
====================================================================

A) Secure Authentication and Session Control
- Login with username/email and password.
- Session token validation and persistence.
- Password hashing and security controls (including failed-attempt handling and lock rules).
- Password reset workflow by email.
- Maintenance mode restriction for controlled access windows.

B) Role-Based Access and Navigation
- Dynamic sidebar and page visibility by role.
- Supported role hierarchy includes:
  General Manager, Region Director, Region Manager,
  Gas Station Manager, Gas Station Supervisor, Employee.
- Access to pages and actions is constrained by role policy.

C) Operational Dashboards
- Main dashboard with organization metrics and overview indicators.
- General Manager dashboard for executive-level monitoring.
- Visibility into station and regional status for decision making.

D) Region and Station Administration
- Create and manage regions and stations.
- Store location attributes (address, latitude, longitude).
- Organize stations under region structure.

E) Interactive Map View
- Visual map representation of station network.
- Color/status-driven station monitoring.
- Faster geo-based triage of high-risk locations.

F) Employee and User Administration
- Manage employee records and assignments.
- User account administration for system access.
- Role assignment and governance controls.

G) AI Video Analysis Pipeline
- Video submissions are collected and queued for processing.
- AI worker analyzes operational footage.
- Structured outputs are generated for operational review.
- Risk scoring engine translates observations into actionable risk levels.

H) AI Reports
- Centralized view of AI analysis outcomes.
- Queue/processing tracking for report lifecycle.
- Retrying of failed processing jobs.

I) AI Alerts and Incident Tracking
- AI-driven alert generation by risk severity.
- Alert status flow (new, acknowledged, resolved).
- Follow-up workflow support for operational incidents.

J) Audit Logging and Traceability
- System actions are logged with user context and timestamps.
- Supports accountability, internal controls, and compliance reviews.

K) Communications and Notifications
- Email notifications for key operational and account events.
- Telegram bot integration for field submission workflows.
- Background workers for continuous automated processing.

L) Settings and User Preferences
- User profile controls (for example password updates).
- UI preference options such as dark mode.

M) Help and In-App Guidance
- Dedicated Help page for end-user orientation and usage support.


====================================================================
3) BUSINESS VALUE CREATED BY THE APP
====================================================================

1. Faster Risk Detection
- AI-assisted video review reduces time-to-detection for safety and process violations.
- High-risk stations can be prioritized before incidents escalate.

2. Better Operational Consistency
- Standardized review and alert workflows reduce supervision variability across regions.
- Centralized metrics make station performance easier to compare.

3. Stronger Management Visibility
- Multi-level dashboards give both local and executive users relevant insights.
- Map and report views turn distributed station data into actionable oversight.

4. Improved Accountability
- Audit trails and role-based actions help trace who did what and when.
- Supports internal governance and post-incident analysis.

5. Higher Response Efficiency
- Alert lifecycle tracking (new -> acknowledged -> resolved) improves closure discipline.
- Notification channels (email/Telegram) reduce delay between detection and action.

6. Scalable Multi-Site Administration
- Region/station/employee structures support growth without losing control.
- Access permissions align responsibilities with organizational hierarchy.

7. Human-in-the-Loop AI Operations
- AI recommendations support decision-making while preserving human oversight.
- Encourages safer adoption of AI in daily operational management.


====================================================================
4) TECHNICAL CAPABILITY SNAPSHOT
====================================================================

- Frontend/App Layer: Streamlit-based multi-page management interface.
- Data Layer: PostgreSQL schema for users, employees, regions, stations, submissions, alerts, logs, settings, and shift tracking.
- AI Layer: Automated video analysis and risk scoring.
- Automation Layer: Background workers for bot intake and AI processing.
- Integration Layer: Email service and Telegram workflow integration.
- Vision Stack: OpenCV frame sampling plus Ollama vision-model support via `OLLAMA_VISION_MODEL`.


====================================================================
5) IMPORTANT AI DISCLAIMER
====================================================================

This platform uses Generative AI to provide management suggestions and analysis.
AI outputs are probabilistic, may be inaccurate, and should not be treated as professional or safety advice.
Human oversight is required for all decisions.
Users assume responsibility for operational outcomes when using AI-generated insights.


====================================================================
6) PROJECT POSITIONING SUMMARY
====================================================================

GentStationAI is a practical AI operations control system for fuel retail networks.
It combines governance, visibility, and automation to improve station quality, reduce risk exposure, and support faster management decisions at scale.
