# Source Input: GentStationAI Production Readiness and Multi-Tenant Upgrade Plan

> Converted from the uploaded DOCX file for use as a plain Markdown source input in coding assistants.

**GentStationAI**

**Production Readiness and Multi-Tenant Upgrade Plan for Codex**

Dedicated Ubuntu Server Architecture \| Two-Tier Commercial Model \| Professional Landing Page \| CCTV Intelligence Roadmap

[Embedded image omitted: GentStationAI tier/positioning poster from page 1.]

**Prepared for:** Branislav Radomirovic
**Purpose:** A Codex-ready implementation plan to transform the current GentStationAI project into a production-ready, multi-tenant platform for multiple fuel-retail companies.

# 1. Executive Summary

This document defines a detailed, implementation-ready plan for upgrading GentStationAI from the current single-company operations platform into a production-ready multi-tenant SaaS-style environment hosted on a dedicated Ubuntu server. The plan removes Render from the target architecture and focuses on a clean professional deployment using Docker Compose, PostgreSQL, Redis, reverse proxy, background workers, object storage, backups, monitoring, and hardened security practices.

The new commercial model introduces two service levels: Tier 1 - AI Daily Operations and Tier 2 - CCTV Intelligence. Tier 1 keeps the current value proposition around daily AI-assisted operations, manual or Telegram-based video submissions, reports, dashboards, alerts, and staff/station workflows. Tier 2 extends the product into CCTV camera integration, zone-based video intelligence, vehicle and shop conversion analytics, safety/security event detection, review workflows, benchmarking, and future POS, pump, loyalty, and inventory integrations.

- **Primary goal:** create a professional, maintainable, secure, multi-tenant architecture that can support multiple client companies without data leakage.

- **Deployment goal:** run the full system on a dedicated Ubuntu server, not Render, with repeatable infrastructure and operations documentation.

- **Commercial goal:** support service tier enforcement, feature gating, per-company billing metadata, camera/employee/station limits, and upgrade paths.

- **User-experience goal:** add a simple but powerful landing page before login that explains the product, tiers, outcomes, pilot offer, and trust/security posture.

- **Engineering goal:** provide Codex with precise implementation phases, database changes, service boundaries, acceptance criteria, and testing requirements.

# 2. Source Inputs and Product Direction

| **Input**                         | **Key meaning for this plan**                                                                                                                                                                                                                       |
|-----------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Current project archive           | Existing Streamlit/Python app with PostgreSQL, Redis, workers, Telegram, AI video processing, reporting, audit logs, station/region/user management, Docker assets, and deployment handoff docs.                                                    |
| Attached CCTV functional document | Defines GentStationAI CCTV Intelligence as a module that transforms existing station CCTV into structured events, operational KPIs, safety/security alerts, sales insights, loyalty analytics, and company reports for networks of 10-100 stations. |
| Attached tier poster/image        | Defines product positioning and the two commercial tiers: Tier 1 - AI Daily Operations and Tier 2 - CCTV Intelligence, including price anchors, setup fees, benefits, and pilot offer.                                                              |
| User requirement                  | Create a Codex-ready plan for a multi-tenant, production-ready, dedicated Ubuntu deployment with no Render dependency and a professional pre-login landing page.                                                                                    |

# 3. Target Product Model

## 3.1 Tenant model

The upgraded system must treat every client company as a separate tenant. A tenant is a paying client organization, for example an oil and gas operator, franchise network, regional retail group, or station owner. All operational entities must belong to exactly one tenant unless explicitly global/system-level.

| **Entity**              | **Tenant behavior**                                                                                                                                                                 |
|-------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Company / Tenant        | Top-level account. Holds subscription tier, billing metadata, feature flags, limits, timezone, locale, branding, retention rules, and security settings.                            |
| Regions                 | Tenant-scoped. Each company can define its own regional structure.                                                                                                                  |
| Stations                | Tenant-scoped. Stations belong to tenant and optionally region.                                                                                                                     |
| Users                   | Tenant-scoped except platform superadmin. Each user should operate within one tenant initially; future multi-tenant support for reseller/platform staff may use scoped memberships. |
| Submissions             | Tenant-scoped. Manual/Telegram video reports must be isolated by tenant.                                                                                                            |
| Cameras and zones       | Tenant-scoped. Only available when Tier 2 or add-on enabled.                                                                                                                        |
| Events, metrics, alerts | Tenant-scoped. Must never be visible across tenants.                                                                                                                                |
| Reports and audit logs  | Tenant-scoped. Audit logs must record tenant_id and actor details.                                                                                                                  |
| Settings                | Split into global platform settings and tenant settings. Avoid a single shared settings table for tenant-specific configuration.                                                    |

## 3.2 Service tiers

| **Capability**       | **Tier 1 - AI Daily Operations**                                                      | **Tier 2 - CCTV Intelligence**                                                                                        |
|----------------------|---------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| Pricing model        | Monthly price per employee; one-time onboarding/setup can be zero for basic adoption. | Monthly price per CCTV camera; one-time setup per station because camera mapping, zones, and validation are required. |
| AI video reports     | Yes. Daily employee/station report workflow.                                          | Yes. Includes everything from Tier 1.                                                                                 |
| CCTV integration     | No.                                                                                   | Yes. Connect existing cameras/feeds where technically possible.                                                       |
| Vehicle analytics    | No.                                                                                   | Yes. Zone-based detection and metrics.                                                                                |
| Conversion analytics | No.                                                                                   | Yes. Entry, pump, shop, cashier/product-zone conversion.                                                              |
| Dashboard and alarms | Basic operational dashboards and alerts.                                              | Advanced review center, CCTV events, benchmarking, station/regional ranking.                                          |
| Benchmarking         | Basic.                                                                                | Advanced station, region, and company benchmarking.                                                                   |
| Initial MVP focus    | Employees, stations, daily reports, Telegram intake, AI review, audit log.            | Cameras, zones, vehicle/pump/shop/safety events, manager review workflow, executive reports.                          |

## 3.3 Responsible AI and privacy boundaries

- Avoid face recognition and customer identification in the initial phases.

- Avoid license-plate loyalty unless a client has a specific legal basis and written approval.

- Use language such as estimated fueling, possible incident, suspected risk, requires manager review, and detected object/person/vehicle.

- Do not present CCTV-only results as confirmed sales, confirmed theft, or confirmed rule violations.

- Store structured events and short evidence clips/images only when needed; avoid retaining continuous video unless a client explicitly requires it and legal review supports it.

- Every AI-generated safety/security event must support human review, false-positive marking, comments, resolution, and escalation.

# 4. Target Production Architecture on Dedicated Ubuntu Server

The deployment target is a dedicated Ubuntu server running a containerized environment. Render must be removed from the operational target. The production architecture should be simple enough to operate, but clean enough to support growth, backup, monitoring, and security hardening.

## 4.1 Service layout

| **Service**            | **Container/process**                                       | **Responsibility**                                                                                                 |
|------------------------|-------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------|
| Reverse proxy          | nginx or Traefik                                            | TLS termination, HTTP to HTTPS redirect, routing to Streamlit app, optional basic rate limiting, security headers. |
| Web app                | gentstation-web                                             | Streamlit UI, landing page, login, admin, dashboards, reports, review center.                                      |
| PostgreSQL             | postgres                                                    | System of record with tenant isolation. Dedicated volume and backups.                                              |
| Redis                  | redis                                                       | Queues, worker coordination, locks, job state, rate-limit counters.                                                |
| AI worker              | gentstation-ai-worker                                       | Processes Tier 1 submissions and Tier 2 video/CCTV event jobs.                                                     |
| Telegram worker        | gentstation-telegram-worker                                 | Receives Telegram submissions and maps chat IDs/users to tenant/station.                                           |
| Report scheduler       | gentstation-report-scheduler                                | Daily/weekly reports, scheduled emails, executive summaries.                                                       |
| Ollama / model runtime | ollama                                                      | Local LLM/vision inference service for controlled deployments; optionally replace with external AI provider later. |
| Object/file storage    | local mounted volume initially; MinIO optional              | Stores uploads, event evidence snapshots, generated reports, temporary clips.                                      |
| Monitoring/logging     | Prometheus/Grafana/Loki optional or lightweight first phase | Health checks, logs, queue depth, worker heartbeat, DB/storage metrics.                                            |
| Backup job             | backup container or host cron                               | Encrypted DB dumps and file backups with retention policy.                                                         |

## 4.2 Recommended directory layout on Ubuntu host

/opt/gentstationai/
app/ \# Git checkout
deploy/
docker-compose.prod.yml
nginx/
gentstationai.conf
env/
.env.production \# not committed
.env.production.example \# committed template only
data/
postgres/
redis/
uploads/
reports/
evidence/
ollama/
backups/
logs/
scripts/
deploy.sh
backup.sh
restore.sh
healthcheck.sh
rotate-logs.sh

## 4.3 Production Docker Compose principles

- Use one production compose file for Ubuntu server. Do not rely on Render configuration.

- Run web, AI worker, Telegram worker, and report scheduler as separate containers.

- Do not start background workers from app.py in production.

- Mount persistent volumes only where needed: PostgreSQL, Redis if persistence is desired, uploads, reports, evidence, Ollama model cache, backups.

- Use a dedicated Docker network, health checks, restart policies, and resource limits.

- Keep secrets in environment files or a proper secret manager; never commit actual production .env values.

- Expose only reverse proxy ports 80/443 publicly. PostgreSQL, Redis, Ollama, and workers must be private to the Docker network.

# 5. Required Architecture Refactor

## 5.1 Immediate repository cleanup

| **Task**                        | **Codex instruction**                                                                                           | **Acceptance criteria**                                                                |
|---------------------------------|-----------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| Remove macOS artifacts          | Delete \_\_MACOSX folders and .DS_Store files from project and archives.                                        | No \_\_MACOSX or .DS_Store appears in git status or deployment packages.               |
| Remove sensitive env files      | Remove .env.production.actual and any real secret material from repository.                                     | Only .env.example / .env.production.example remain; actual secrets are on server only. |
| Update .gitignore/.dockerignore | Ignore .env\*, uploads, reports, evidence, backups, pycache, macOS files, local DB dumps, IDE files.            | Sensitive/local files cannot be accidentally committed or included in Docker context.  |
| Archive Render config           | Move render.yaml to docs/legacy/render.yaml or remove from production docs.                                     | Deployment docs point only to Ubuntu/Docker Compose path.                              |
| Add README production note      | Document that production is dedicated Ubuntu server, Docker Compose, nginx/Traefik, PostgreSQL, Redis, workers. | New developer can understand the intended deployment model in less than 10 minutes.    |

## 5.2 Application structure target

gentstationai/
app.py \# Streamlit router only, not business logic
pages/
landing.py \# public pre-login page
login.py
dashboard.py
review_center.py
tenant_admin.py
billing_and_plan.py
cctv_cameras.py
cctv_zones.py
cctv_events.py
core/
config.py
database.py
tenancy.py \# tenant resolution and enforcement helpers
permissions.py
feature_flags.py
subscription.py
audit.py
storage.py
migrations/
domain/
tenants.py
stations.py
users.py
submissions.py
cctv.py
reports.py
alerts.py
workers/
ai_worker.py
telegram_worker.py
report_scheduler.py
cctv_ingestion_worker.py
services/
email_service.py
telegram_service.py
ollama_service.py
cctv_service.py
report_service.py
tests/
unit/
integration/
e2e_smoke/

Codex should not perform a risky big-bang refactor. First introduce tenant-safe models, feature flags, and tests around current behavior. Then gradually move logic out of large Streamlit pages into core/domain/services modules.

# 6. Data Model Upgrade

The most important production upgrade is tenant isolation. Every operational table must either include tenant_id or be explicitly classified as global. All read/write paths must filter by tenant_id. This must be tested, not trusted by convention.

## 6.1 New core tables

| **Table**            | **Purpose**                                       | **Important fields**                                                                                                             |
|----------------------|---------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| tenants              | Client companies.                                 | id, name, slug, legal_name, status, timezone, locale, default_currency, created_at, updated_at                                   |
| tenant_subscriptions | Commercial tier and limits.                       | tenant_id, tier_code, status, starts_at, renews_at, employee_limit, station_limit, camera_limit, storage_limit_gb, features_json |
| tenant_settings      | Tenant-specific settings.                         | tenant_id, key, value_json, is_secret_reference, updated_by                                                                      |
| tenant_branding      | Optional custom branding.                         | tenant_id, logo_path, primary_color, support_email, custom_landing_enabled                                                       |
| tenant_memberships   | User-to-tenant membership for future flexibility. | tenant_id, user_id, role, status                                                                                                 |
| feature_flags        | Controlled feature rollout.                       | tenant_id nullable, flag_key, enabled, config_json                                                                               |
| audit_events         | Tenant-aware audit log.                           | tenant_id, actor_user_id, action, target_type, target_id, ip_address, metadata_json, created_at                                  |

## 6.2 CCTV Intelligence tables

| **Table**           | **Purpose**                               | **Important fields**                                                                                                           |
|---------------------|-------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| cctv_cameras        | Registered camera per station.            | tenant_id, station_id, name, stream_url_secret_ref, camera_type, status, timezone, last_seen_at                                |
| cctv_zones          | Configured analysis zones on a camera.    | tenant_id, camera_id, zone_type, polygon_json, active, rules_json                                                              |
| cctv_analysis_jobs  | Jobs for feed sampling or uploaded clips. | tenant_id, camera_id, job_type, status, started_at, completed_at, error, retry_count                                           |
| cctv_events         | Detected business/safety/security events. | tenant_id, station_id, camera_id, zone_id, event_type, severity, confidence, status, occurred_at, evidence_path, metadata_json |
| cctv_metrics_hourly | Aggregated metrics for dashboards.        | tenant_id, station_id, camera_id, metric_date, hour, metric_key, metric_value                                                  |
| cctv_review_actions | Manager review workflow.                  | tenant_id, event_id, reviewer_user_id, action, comment, created_at                                                             |
| integrations        | POS/pump/loyalty/inventory integrations.  | tenant_id, integration_type, provider, status, config_json, secret_ref                                                         |
| integration_events  | Imported POS/pump/loyalty events.         | tenant_id, integration_id, external_id, event_type, occurred_at, payload_json                                                  |

## 6.3 Modify existing tables

| **Existing area**                                     | **Required change**                                                                                                                                                   |
|-------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Region, Station, StationCategory                      | Add tenant_id. Unique names/codes should be unique within tenant, not globally.                                                                                       |
| User                                                  | Add tenant_id for simple first implementation, or add tenant_memberships for future reseller/platform staff. Keep platform_superadmin as a special global capability. |
| Submission                                            | Add tenant_id, station_id, source, service_tier_context, storage_path, retention_until.                                                                               |
| AIAlert                                               | Add tenant_id, station_id, source_type, event linkage if generated from CCTV.                                                                                         |
| ScheduledReport                                       | Add tenant_id and tier awareness. Report scope must not cross tenant boundaries.                                                                                      |
| SystemSetting                                         | Split into global_settings and tenant_settings or enforce tenant_id nullable with strict semantics.                                                                   |
| WorkerHealthLog / RedisHealthLog / AIInferenceLatency | Add tenant_id only when event is tenant-specific; otherwise keep global but do not expose raw global logs to tenant users.                                            |

## 6.4 Migration approach

- Introduce Alembic as the authoritative migration system. Existing ensure_schema() logic should not be the long-term production schema manager.

- Create migration 0001_baseline_current_schema from the existing deployed schema.

- Create migration 0002_multi_tenant_core to add tenants, subscriptions, tenant settings, tenant_id columns, indexes, and foreign keys.

- Create migration 0003_cctv_intelligence to add cameras, zones, events, metrics, review actions, and integration tables.

- Create backfill script that creates a default tenant from the current single-company data and assigns all existing regions, stations, users, submissions, alerts, and reports to it.

- Add database-level indexes for tenant_id plus common filters: station_id, region_id, occurred_at, status, severity, event_type, created_at.

- Prefer application-level tenant enforcement now; consider PostgreSQL Row Level Security later when data volume and team maturity justify the added complexity.

# 7. Tenant Isolation and Access Control

| **Role**            | **Scope**                           | **Typical permissions**                                                                           |
|---------------------|-------------------------------------|---------------------------------------------------------------------------------------------------|
| Platform Superadmin | All tenants, internal only          | Create tenants, assign plans, view platform health, impersonation only with explicit audit trail. |
| Company Admin       | One tenant                          | Manage tenant settings, users, regions, stations, subscriptions view, integrations, reports.      |
| Operations Director | One tenant                          | All station/region dashboards, reports, benchmark views, operational alerts.                      |
| Regional Manager    | Assigned regions only               | Regional dashboards, stations in region, review events, reports.                                  |
| Station Manager     | Assigned station(s)                 | Station dashboard, submissions, review station events, daily reports.                             |
| Safety Manager      | Tenant or assigned regions          | Safety events, risk dashboards, review/escalation workflow.                                       |
| Security Reviewer   | Tenant or assigned regions/stations | Security events, after-hours events, incident workflow.                                           |
| Read-only Auditor   | Configured tenant/station scope     | View-only access to dashboards, reports, audit trail, no modifications.                           |

- Create a TenantContext object resolved after login and stored in session state.

- Every query function must require tenant_id explicitly or derive it from TenantContext.

- Never use raw session user role alone to determine data access; combine role + tenant + region/station assignment + feature entitlement.

- Add automated tests proving that user A from tenant A cannot access tenant B objects by ID guessing.

- Add audit events for tenant switch, login, failed login, user creation, role changes, camera changes, integration changes, event review actions, export/download actions.

# 8. Feature Gating and Subscription Enforcement

Tier gating should be implemented centrally, not scattered across pages. Codex should create a single subscription/feature service with clean helpers and decorators. UI pages should ask whether a feature is enabled and display upgrade CTAs when appropriate.

| **Feature key**               | **Tier 1**    | **Tier 2**    | **Notes**                                                |
|-------------------------------|---------------|---------------|----------------------------------------------------------|
| daily_ai_reports              | Enabled       | Enabled       | Core current workflow.                                   |
| telegram_submission           | Enabled       | Enabled       | Map chat IDs to tenant users/stations.                   |
| basic_dashboard               | Enabled       | Enabled       | Station and region performance.                          |
| basic_alerts                  | Enabled       | Enabled       | Operational alerts.                                      |
| cctv_camera_registry          | Disabled      | Enabled       | Camera CRUD and status.                                  |
| zone_configuration            | Disabled      | Enabled       | Polygon zones on camera snapshots.                       |
| vehicle_intelligence          | Disabled      | Enabled       | Passed, entered, exited, pump-zone metrics.              |
| conversion_analytics          | Disabled      | Enabled       | Passerby-entry, entry-pump, fuel-shop.                   |
| advanced_review_center        | Basic limited | Enabled       | Status, evidence, comments, false positives, escalation. |
| advanced_benchmarking         | Basic         | Enabled       | Station/regional ranking and executive summaries.        |
| pos_pump_loyalty_integrations | Add-on/future | Add-on/future | Start with API placeholders and integration tables.      |

# 9. Landing Page Requirement

Before login, users and prospects should see a professional landing page that explains the value of GentStationAI, the two tiers, pilot offer, and trust/security posture. It must be simple, fast, responsive, and consistent with the GSAI branding.

## 9.1 Landing page goals

- Explain the product in less than 30 seconds.

- Show the problem: manual supervision is inefficient, CCTV is reactive, operational losses are invisible.

- Show the solution: four AI intelligence pillars - vehicle intelligence, conversion intelligence, sales intelligence, safety and security intelligence.

- Present Tier 1 and Tier 2 clearly with pricing model and feature differences.

- Invite the user to schedule a pilot project for 3-5 stations.

- Provide a login path for existing customers without hiding it.

- Avoid heavy animations and avoid requiring JavaScript beyond Streamlit capabilities.

## 9.2 Suggested page structure

| **Section**           | **Content**                                                                                                                                                                                                                  |
|-----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Hero                  | Logo, headline: GentStationAI - The future of intelligent gas-station management. Subheading: Transform operations, sales, and safety through AI analysis of daily reports and CCTV systems. Buttons: Login, Schedule pilot. |
| Problem cards         | Manual supervision is inefficient; CCTV is used reactively; invisible operational losses reduce sales and increase risk.                                                                                                     |
| Solution pillars      | Vehicle Intelligence, Conversion Intelligence, Sales Intelligence, Safety & Security Intelligence.                                                                                                                           |
| Tier comparison       | Tier 1 - AI Daily Operations and Tier 2 - CCTV Intelligence with professional feature comparison.                                                                                                                            |
| Business benefits     | Operational control, expansion through POS/loyalty/inventory/EV integrations, industry leadership.                                                                                                                           |
| Pilot CTA             | Test GentStationAI on 3-5 stations and see how video data becomes measurable business results.                                                                                                                               |
| Trust/security footer | Responsible AI, no facial recognition in MVP, role-based access, audit logs, tenant isolation, GDPR-conscious retention.                                                                                                     |

## 9.3 Implementation guidance for Streamlit

- Use a public unauthenticated route or state branch in app.py that renders landing content before login.

- Keep landing page code separate in pages/landing.py or ui/landing.py.

- Use the existing GSAI assets and consistent colors: dark navy, blue accent, white cards, restrained shadows.

- Make all landing copy editable through a small config dictionary or tenant branding later.

- Add a contact/pilot form only if email sending is configured; otherwise use mailto or a simple CTA placeholder.

- Ensure the login button is always visible at the top right and again near the bottom CTA.

- Do not expose internal route names, system health, or debug information on the public landing page.

# 10. CCTV Intelligence Product Implementation

## 10.1 MVP scope for Tier 2

| **Domain**         | **MVP capability**                                                                             | **Implementation note**                                                    |
|--------------------|------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| Camera registry    | Register cameras per tenant/station with status and stream metadata.                           | Store credentials as secret references, not plaintext in normal tables.    |
| Zone configuration | Define entrance, exit, pump, shop entrance, cashier, restricted, emergency access zones.       | Start with polygon JSON drawn on snapshot image; later improve UI.         |
| Vehicle traffic    | Vehicles passed, entered, exited, entered-to-pump conversion.                                  | Use batch/sampled video jobs first; live stream processing can come later. |
| Pump analytics     | Vehicle at pump, estimated fueling, dwell duration, blocked pump, long dwell.                  | Do not claim confirmed fueling unless POS/pump integration exists.         |
| Queues/congestion  | Basic queue detection and congestion scoring.                                                  | Focus on simple event + metric output, not perfect real-time control.      |
| Shop analytics     | Shop entries, cashier queue, fuel-to-shop conversion estimate.                                 | Camera placement may limit reliability; confidence score required.         |
| Safety/security    | Restricted zone, person in vehicle lane, blocked emergency access, after-hours person/vehicle. | High-value early alerts with review workflow.                              |
| Review center      | New, acknowledged, reviewed, false_positive, resolved, escalated.                              | Every event has evidence, confidence, status, comments, reviewer action.   |
| Reports            | Daily station report and weekly company report.                                                | Include top exceptions, KPI trends, and items requiring review.            |

## 10.2 Event taxonomy

| **Category**            | **Event examples**                                                                                                                           |
|-------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| Vehicle intelligence    | vehicle_passed, vehicle_entered, vehicle_exited, vehicle_at_pump, vehicle_left_without_fueling                                               |
| Conversion intelligence | entry_to_pump_conversion, fuel_to_shop_conversion, product_zone_interest, cashier_queue_detected                                             |
| Operational efficiency  | pump_blocked, long_dwell_at_pump, queue_detected, entrance_blocked, exit_blocked, forecourt_congestion                                       |
| Safety                  | person_in_vehicle_lane, restricted_zone_entry, blocked_emergency_access, unattended_object_possible, spill_possible, smoke_or_fire_suspected |
| Security                | after_hours_person, after_hours_vehicle, storage_area_access, camera_obstruction, loitering_detected                                         |
| Review workflow         | requires_manager_review, false_positive, escalated, resolved                                                                                 |

## 10.3 AI processing strategy

- Start with sampled/batch analysis of clips and snapshots. Avoid promising full real-time CCTV processing in the first production release.

- Build an abstraction layer: VideoAnalysisProvider with implementations for current Ollama vision model, future local CV model, and future external AI API.

- Persist raw AI outputs separately from normalized events so prompts/models can evolve without losing traceability.

- Every event must include confidence, model_version, prompt_version, source_video_or_snapshot, and review_required flag.

- Add false-positive feedback into metrics. Later use this feedback to tune prompts/models and thresholds.

- For dedicated Ubuntu server with limited GPU availability, set safe concurrency and frame sampling defaults. Use queue depth and worker health dashboards.

# 11. Production Security Hardening

| **Area**         | **Required action**                                                                                                                  |
|------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| Secrets          | Rotate any secrets previously included in archives. Store only on server. Use .env.production with chmod 600. Commit templates only. |
| TLS              | Use Let's Encrypt via nginx/Traefik. Redirect HTTP to HTTPS.                                                                         |
| Network          | Only 80/443 public. PostgreSQL, Redis, Ollama private to Docker network. Restrict SSH with keys only.                                |
| Authentication   | Keep bcrypt, strengthen password policy, add password reset tokens, optional 2FA later.                                              |
| Sessions         | Server-side session records, token hashing, TTL, logout invalidation, secure cookie/query handling.                                  |
| Authorization    | Central permission checks. Tenant + role + region/station scope + feature gates.                                                     |
| Uploads/evidence | Validate file types and size. Store outside web root. Generate signed/internal links only.                                           |
| Audit            | Log privileged actions, data exports, event reviews, integration changes, login failures, tenant changes.                            |
| Backups          | Encrypted DB and file backups. Test restore monthly.                                                                                 |
| Privacy          | Retention policies per tenant; avoid biometrics in MVP; add consent/legal notes for CCTV deployments.                                |

# 12. Testing Strategy

| **Test group**         | **Coverage required**                                                                                                         |
|------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| Unit tests             | Feature gating, tenant context, permissions, subscription limits, event taxonomy, report calculations.                        |
| Database tests         | Migrations, tenant_id constraints, indexes, uniqueness per tenant, default tenant backfill.                                   |
| Security tests         | Cross-tenant object access by ID, role boundaries, unauthenticated landing vs authenticated pages, secret leakage prevention. |
| Worker tests           | AI worker retry, stuck job handling, Redis locks, report scheduler idempotency, Telegram mapping.                             |
| CCTV tests             | Camera CRUD, zone validation, event creation, review transitions, metric aggregation.                                         |
| UI smoke tests         | Landing page, login, dashboard, tenant admin, tier lock pages, review center.                                                 |
| Deployment smoke tests | docker compose up, health checks, DB migration, app login, worker heartbeat, report generation, backup script.                |

# 13. Implementation Roadmap for Codex

## Phase 0: Safety, cleanup, and baseline

**Objective:** Prepare the repository so future work is safe, repeatable, and free from leaked secrets or noisy artifacts.

### Deliverables

- Remove macOS metadata and actual production secret files.

- Add complete .gitignore and .dockerignore.

- Create safe environment templates.

- Add a project health README explaining the dedicated Ubuntu target.

- Run syntax check and basic import check.

### Codex implementation tasks

1.  Delete \_\_MACOSX and .DS_Store artifacts.

2.  Remove deployment-handoff/vm/.env.production.actual from repository and document secret rotation.

3.  Update .gitignore and .dockerignore to exclude env files, uploads, reports, evidence, backups, pycache, model files, dumps.

4.  Create docs/production/README.md with the new deployment target.

5.  Add scripts/check_project.sh that runs compileall and basic dependency checks.

### Acceptance criteria

- No real secret values are present in the repository.

- Project compiles without macOS metadata errors.

- New production documentation does not mention Render as the target deployment.

- Developer can identify required env vars from examples only.

## Phase 1: Production configuration and service boundaries

**Objective:** Separate production services cleanly and prevent the web process from starting background workers in production.

### Deliverables

- Environment configuration module with typed settings.

- Production Docker Compose for Ubuntu.

- Separate web/AI/Telegram/scheduler services.

- Health endpoints or health commands.

- Deployment scripts.

### Codex implementation tasks

6.  Refactor config.py to centralize all environment settings and defaults.

7.  Add APP_ENV=production behavior that disables worker startup from app.py.

8.  Create deploy/docker-compose.prod.yml with web, postgres, redis, ai-worker, telegram-worker, report-scheduler, ollama optional, nginx/traefik.

9.  Add container health checks and restart policies.

10. Add deploy/scripts/deploy.sh and deploy/scripts/healthcheck.sh.

### Acceptance criteria

- docker compose config validates.

- Web container can run without launching workers.

- Each worker can start independently.

- Health check identifies DB, Redis, storage, worker heartbeat, and Ollama status.

- No Render files are required for production deployment.

## Phase 2: Alembic migrations and tenant core

**Objective:** Move toward production-grade schema management and introduce tenant-safe data ownership.

### Deliverables

- Alembic initialized.

- Baseline migration.

- Tenant/subscription/settings tables.

- tenant_id columns on operational tables.

- Default tenant backfill script.

### Codex implementation tasks

11. Initialize Alembic with SQLAlchemy metadata.

12. Create baseline migration matching current schema.

13. Add tenants, tenant_subscriptions, tenant_settings, tenant_branding, tenant_memberships, feature_flags.

14. Add tenant_id to regions, stations, users, submissions, alerts, scheduled reports, audit logs, and relevant settings.

15. Create scripts/backfill_default_tenant.py for existing single-company data.

16. Add indexes and uniqueness constraints scoped by tenant.

### Acceptance criteria

- Fresh DB can be built entirely via Alembic.

- Existing DB can be migrated and backfilled.

- All tenant-owned rows have tenant_id.

- Tests verify uniqueness and tenant relationships.

- ensure_schema is deprecated or limited to dev-only behavior.

## Phase 3: Tenant context, permissions, and data isolation

**Objective:** Guarantee that users only access data within their tenant and assigned scope.

### Deliverables

- TenantContext helper.

- Central permission service.

- Tenant-scoped query helpers.

- Cross-tenant isolation tests.

- Audit coverage for sensitive actions.

### Codex implementation tasks

17. Create core/tenancy.py with get_current_tenant, require_tenant, and tenant-scoped query helpers.

18. Create core/permissions.py or extend access_control.py to combine role, tenant, region/station assignment, and feature flags.

19. Update all pages and services to use tenant_id filters.

20. Add platform_superadmin handling for tenant creation only.

21. Add tests that attempt cross-tenant reads/writes by direct IDs.

### Acceptance criteria

- Tenant A users cannot read/write Tenant B data.

- All Streamlit pages resolve tenant context after login.

- Permission failures are user-friendly and audited.

- Automated tests cover the most important role/scope combinations.

## Phase 4: Subscription tiers and feature gates

**Objective:** Implement Tier 1 and Tier 2 commercial model in the product and enforce it consistently.

### Deliverables

- Tier definitions.

- Feature gate service.

- Plan management page.

- Upgrade CTAs.

- Subscription limit checks.

### Codex implementation tasks

22. Create core/subscription.py with tier constants and feature matrix.

23. Implement has_feature(tenant, feature_key), require_feature, and limit checks for employees/stations/cameras.

24. Add tenant admin page to view current tier and usage.

25. Gate CCTV pages behind Tier 2.

26. Show professional upgrade message for disabled Tier 2 features.

27. Add seed data for Tier 1 and Tier 2 test tenants.

### Acceptance criteria

- Tier 1 tenants cannot access CCTV camera/event pages.

- Tier 2 tenants can access CCTV modules.

- Limit checks prevent exceeding configured camera/station/employee limits.

- Feature-gating tests pass.

## Phase 5: Professional landing page before login

**Objective:** Add a branded public landing page that explains GentStationAI, the problem, the solution pillars, tiers, and pilot offer before login.

### Deliverables

- Public landing page.

- Tier comparison component.

- Pilot CTA.

- Login routing.

- Mobile-friendly layout.

### Codex implementation tasks

28. Create ui/landing.py with reusable components.

29. Modify app.py routing so unauthenticated users see landing page first, with clear Login button.

30. Use existing GSAI assets and professional card layout.

31. Add sections: hero, problem, four intelligence pillars, tier comparison, benefits, pilot CTA, trust/privacy footer.

32. Add configuration for CTA email/contact text.

33. Ensure no internal debug/system status appears on public page.

### Acceptance criteria

- Landing page loads without authentication.

- Login remains easy to access.

- Tier differences are clear.

- Page is visually professional at desktop and laptop widths.

- Public page does not leak internal app data.

## Phase 6: Tenant administration and onboarding

**Objective:** Allow platform operator to create and configure client companies, then allow company admins to manage their own structure.

### Deliverables

- Platform tenant admin.

- Company admin onboarding flow.

- Region/station setup scoped by tenant.

- User invite/create flow.

- Branding/settings page.

### Codex implementation tasks

34. Create platform page for superadmin to create tenants and select tier.

35. Create onboarding wizard: company details, regions, stations, users, initial plan.

36. Update existing region/station/user pages to be tenant-scoped.

37. Add tenant branding settings for logo/color/support contact, even if simple initially.

38. Add safe seed/demo data generator for one Tier 1 and one Tier 2 tenant.

### Acceptance criteria

- Superadmin can create a tenant.

- Company admin sees only their company.

- Regions/stations/users are tenant-scoped.

- Demo tenants can be created for testing and sales demos.

## Phase 7: CCTV registry, zones, and review center foundation

**Objective:** Build Tier 2 data foundations before advanced AI analytics.

### Deliverables

- Camera CRUD.

- Zone configuration storage.

- Event model and review status workflow.

- Review center UI.

- Evidence file storage abstraction.

### Codex implementation tasks

39. Add cctv_cameras, cctv_zones, cctv_events, cctv_review_actions migrations/models.

40. Create pages/cctv_cameras.py for camera registry.

41. Create basic zone definition UI using snapshot upload plus polygon JSON/text fallback if drawing UI is too heavy initially.

42. Create pages/review_center.py to filter events by station, region, type, severity, status, date.

43. Implement status transitions: new, acknowledged, reviewed, false_positive, resolved, escalated.

44. Store evidence paths via core/storage.py.

### Acceptance criteria

- Tier 2 tenant can register cameras and zones.

- Review center displays events with filters and evidence.

- Manager can comment, mark false positive, resolve, or escalate.

- Every review action is audited.

## Phase 8: CCTV MVP analytics pipeline

**Objective:** Introduce reliable batch/sampled analysis jobs that produce normalized events and metrics.

### Deliverables

- Analysis job queue.

- VideoAnalysisProvider abstraction.

- Normalized event creation.

- Hourly metric aggregation.

- Worker health and retries.

### Codex implementation tasks

45. Create workers/cctv_ingestion_worker.py or extend AI worker with cctv job type.

46. Create domain/cctv.py/service layer for jobs/events/metrics.

47. Implement provider abstraction for current Ollama-based vision analysis.

48. Create prompt versions for vehicle, pump, shop, safety/security analysis.

49. Normalize outputs into event taxonomy with confidence and review_required.

50. Aggregate metrics into cctv_metrics_hourly.

51. Add queue depth, retries, and stuck job handling.

### Acceptance criteria

- A sample clip can be processed into events/metrics.

- Events appear in review center.

- Dashboard can show basic vehicle/pump/shop/safety metrics.

- Worker failures retry safely and do not corrupt data.

- False positives can be tracked.

## Phase 9: Dashboards, benchmarking, and reports

**Objective:** Turn tenant-safe data into business value for managers and executives.

### Deliverables

- Tier-aware dashboards.

- Station and region benchmarking.

- Daily station report.

- Weekly company executive summary.

- CCTV event and metric widgets.

### Codex implementation tasks

52. Update dashboard pages to use tenant-scoped metrics.

53. Add Tier 2 dashboard cards: vehicles passed/entered/exited, entry conversion, pump utilization, blocked pump events, shop entries, fuel-to-shop conversion, safety/security events.

54. Add benchmarking page for station/regional ranking.

55. Extend report_builder.py to include Tier 2 metrics when enabled.

56. Add report scheduler tests for per-tenant reports.

### Acceptance criteria

- Tier 1 reports remain functional.

- Tier 2 reports include CCTV intelligence sections.

- No report includes another tenant data.

- Benchmarking filters by tenant and user scope.

## Phase 10: Integrations framework for POS, pump, loyalty, inventory

**Objective:** Prepare the architecture for future high-value integrations without overbuilding the first release.

### Deliverables

- Integration tables and service interfaces.

- Import job framework.

- Manual CSV/API placeholder.

- Mapping to stations and external IDs.

- Documentation for future providers.

### Codex implementation tasks

57. Create integrations and integration_events tables.

58. Create services/integration_service.py with provider interface.

59. Add admin page to register integration metadata and credentials as secret refs.

60. Implement manual CSV import placeholder for POS/pump events if useful.

61. Document mapping strategy for external station IDs, pump IDs, loyalty IDs, and product categories.

62. Do not block CCTV MVP on live integrations.

### Acceptance criteria

- Tenant can define integration metadata without exposing secrets.

- Imported events are tenant-scoped.

- Future providers can plug into common interface.

- CCTV-only metrics clearly remain estimated until integrations confirm them.

## Phase 11: Production observability, backup, and operations

**Objective:** Make the dedicated Ubuntu deployment operable and recoverable.

### Deliverables

- Logging strategy.

- Health dashboard.

- Backup and restore scripts.

- Monitoring alerts.

- Runbooks.

### Codex implementation tasks

63. Add structured logging with tenant_id where safe and no secrets.

64. Add health page for superadmin only: DB, Redis, workers, queue depth, storage, Ollama, email, Telegram.

65. Create backup.sh for PostgreSQL dumps and file/evidence backup with retention.

66. Create restore.sh documented procedure.

67. Add docs/runbooks for failed worker, full disk, DB restore, model failure, Redis failure, certificate renewal.

68. Add log rotation and disk usage alerts.

### Acceptance criteria

- Backup can be created and restored in a test environment.

- Superadmin health page shows service status.

- Runbooks exist for common incidents.

- Logs do not expose secrets or sensitive payloads unnecessarily.

## Phase 12: Final hardening and production launch checklist

**Objective:** Prepare for real client pilot and controlled production launch.

### Deliverables

- Security review.

- Load/performance baseline.

- Pilot onboarding checklist.

- Legal/privacy notes.

- Release checklist.

### Codex implementation tasks

69. Run cross-tenant security tests and manual review.

70. Run smoke tests on Ubuntu server after clean deployment.

71. Set resource limits and concurrency defaults for AI/video processing.

72. Create pilot checklist for 3-5 stations, 2-3 cameras per station, zones, responsible reviewers, report recipients.

73. Document privacy/responsible AI limitations for client contracts.

74. Create versioned release notes.

### Acceptance criteria

- Pilot can be deployed from clean server instructions.

- Tenant isolation is verified.

- AI/video workload limits are configured.

- Client-facing limitations are documented.

- Production launch decision has a checklist.

# 14. Codex Master Prompt

Use the following prompt as the starting instruction for Codex. Paste it into Codex with the current repository opened. Then execute phase by phase, not all at once.

You are working on the GentStationAI repository. Your goal is to make the project production-ready as a multi-tenant platform for multiple gas-station companies, with two service tiers: Tier 1 - AI Daily Operations and Tier 2 - CCTV Intelligence. The target deployment is a dedicated Ubuntu server using Docker Compose, PostgreSQL, Redis, separate worker containers, reverse proxy, backups, and optional local Ollama. Do not use Render as the production target.

Follow the implementation plan in GentStationAI_Production_Readiness_Codex_Plan.docx. Work phase by phase. For every phase:
1. Inspect the existing code before changing it.
2. Make small, reviewable commits.
3. Preserve current Tier 1 behavior unless the phase explicitly changes it.
4. Add or update tests for new behavior.
5. Do not commit real secrets or production .env values.
6. Enforce tenant_id in all tenant-owned data paths.
7. Use central permission and feature-gating helpers; do not scatter role/tier checks across pages.
8. Keep web, AI worker, Telegram worker, report scheduler, and future CCTV worker as separate production services.
9. Add clear acceptance criteria evidence in the final response for each phase.

Start with Phase 0 only: repository cleanup, secret removal, .gitignore/.dockerignore, safe env examples, and a short production target README. Do not implement multi-tenancy until Phase 0 is complete.

# 15. Phase-specific Codex Prompts

| **Prompt**      | **Text**                                                                                                                                                                                                                                                                                                                                                         |
|-----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Phase 0 prompt  | Implement Phase 0 only. Remove macOS artifacts and sensitive actual environment files, update ignore files, create safe env templates, and add docs/production/README.md explaining the dedicated Ubuntu deployment target. Do not change application behavior. Run compile checks and report results.                                                           |
| Phase 1 prompt  | Implement Phase 1 only. Centralize production configuration, ensure app.py never starts workers in production, create deploy/docker-compose.prod.yml for Ubuntu with separate web, AI worker, Telegram worker, report scheduler, PostgreSQL, Redis, optional Ollama, and reverse proxy. Add healthcheck scripts. Preserve current behavior in local development. |
| Phase 2 prompt  | Implement Phase 2 only. Initialize Alembic, create baseline and multi-tenant migrations, add tenant/subscription/settings/feature flag tables, add tenant_id to existing tenant-owned tables, and create a backfill_default_tenant script. Add database tests. Do not refactor all UI pages yet unless needed for migrations.                                    |
| Phase 3 prompt  | Implement Phase 3 only. Add TenantContext, tenant-scoped query helpers, central permission checks, and cross-tenant isolation tests. Update existing pages and services so all operational queries are tenant-scoped. Fail closed when tenant context is missing.                                                                                                |
| Phase 4 prompt  | Implement Phase 4 only. Add subscription tier definitions, feature gate helpers, usage limits, tenant plan page, and Tier 1/Tier 2 enforcement. Gate all CCTV routes/features behind Tier 2. Add tests for feature gates and limits.                                                                                                                             |
| Phase 5 prompt  | Implement Phase 5 only. Build the public landing page before login using existing GSAI assets. Include hero, problem, solution pillars, tier comparison, benefits, pilot CTA, trust/privacy footer, and login button. Do not expose internal status or debug data publicly.                                                                                      |
| Phase 6 prompt  | Implement Phase 6 only. Build platform superadmin tenant creation and company admin onboarding flow. Make region/station/user management tenant-scoped. Add demo seed data for one Tier 1 and one Tier 2 tenant.                                                                                                                                                 |
| Phase 7 prompt  | Implement Phase 7 only. Add CCTV camera registry, zone configuration storage, CCTV event model, review actions, review center filters, evidence storage abstraction, and audited review status transitions. Do not implement heavy video AI yet.                                                                                                                 |
| Phase 8 prompt  | Implement Phase 8 only. Add CCTV analysis job pipeline and VideoAnalysisProvider abstraction using the current Ollama-style processing as first provider. Produce normalized events/metrics with confidence, model_version, prompt_version, and review_required. Add worker retry and stuck-job handling tests.                                                  |
| Phase 9 prompt  | Implement Phase 9 only. Upgrade dashboards, benchmarking, daily station reports, and weekly company reports to include Tier 2 CCTV metrics when enabled, while preserving Tier 1 reports. Add tests proving reports are tenant-scoped.                                                                                                                           |
| Phase 10 prompt | Implement Phase 10 only. Add integration framework tables/services for POS, pump, loyalty, and inventory. Implement metadata and secret-reference storage, station/external ID mapping, and optional CSV import placeholder. Do not require live provider integrations yet.                                                                                      |
| Phase 11 prompt | Implement Phase 11 only. Add production observability, superadmin health dashboard, structured logs, backup and restore scripts, runbooks, and disk/queue/worker health checks. Do not expose platform health to tenant users.                                                                                                                                   |
| Phase 12 prompt | Implement Phase 12 only. Run final hardening, cross-tenant tests, deployment smoke tests, production launch checklist, pilot onboarding checklist, resource limits, and release notes. Report all remaining risks clearly.                                                                                                                                       |

# 16. Dedicated Ubuntu Server Deployment Blueprint

## 16.1 Server assumptions

- Ubuntu 22.04 LTS or 24.04 LTS.

- Docker Engine and Docker Compose plugin installed.

- Domain DNS A record points to server public IP.

- SSH key-only access for administrator.

- Firewall allows only 22, 80, and 443 publicly; ideally restrict 22 to trusted IPs.

- Sufficient disk for PostgreSQL, uploaded videos, evidence clips, reports, model files, and backups.

- If running local Ollama vision models, allocate adequate RAM/CPU/GPU and set safe concurrency. For smaller servers, use batch analysis and low frame sampling.

## 16.2 High-level deployment commands

\# on Ubuntu server
sudo mkdir -p /opt/gentstationai
sudo chown -R \$USER:\$USER /opt/gentstationai
cd /opt/gentstationai

git clone \<your-private-repo-url\> app
cd app
cp deploy/env/.env.production.example deploy/env/.env.production
nano deploy/env/.env.production \# fill real secrets only on server

./deploy/scripts/deploy.sh
./deploy/scripts/healthcheck.sh

## 16.3 Backup and restore minimum standard

- Nightly encrypted PostgreSQL dump retained at least 14-30 days.

- Nightly backup of uploads, reports, evidence, and tenant branding assets.

- Weekly off-server backup copy.

- Monthly restore test into a staging environment.

- Backup script must fail loudly and log result. Do not silently skip failed backups.

- Document RPO/RTO expectations for clients before production launch.

# 17. Professional UX Standards

- Use consistent labels: Company, Region, Station, Camera, Zone, Event, Metric, Alert, Report, Review.

- Use status badges and severity colors consistently across AI alerts and CCTV events.

- Always show whether an AI/CCTV conclusion is estimated, suspected, or confirmed by integration.

- For Tier 1 users, show helpful upgrade explanations instead of broken/hidden navigation.

- For Tier 2 review center, prioritize filtering, evidence preview, action buttons, and audit trail over visual complexity.

- Use professional empty states: explain what data is needed and what action the user can take.

- Keep landing page marketing copy concise; keep authenticated dashboards operational and metric-focused.

# 18. Acceptance Checklist for Production Readiness

| **Area**           | **Production-ready when...**                                                                         |
|--------------------|------------------------------------------------------------------------------------------------------|
| Repository hygiene | No actual secrets, no macOS metadata, clean Docker context, safe env examples.                       |
| Deployment         | Clean Ubuntu deployment from documented steps; no Render dependency.                                 |
| Service separation | Web, AI worker, Telegram worker, report scheduler, and future CCTV worker run separately.            |
| Database           | Alembic migrations, tenant core, tenant_id on tenant-owned data, indexes and backfill.               |
| Tenant isolation   | Automated cross-tenant access tests pass.                                                            |
| Tier enforcement   | Tier 1 and Tier 2 feature gates and limits work.                                                     |
| Landing page       | Public professional landing page before login with clear tier comparison and CTA.                    |
| CCTV foundation    | Camera registry, zones, events, review center, evidence storage.                                     |
| AI/CCTV pipeline   | Batch/sampled analysis jobs produce normalized events and metrics with confidence and review status. |
| Reports            | Daily/weekly reports are tenant-scoped and tier-aware.                                               |
| Security           | TLS, private internal services, strong auth, audit log, upload validation, retention policy.         |
| Operations         | Backups, restore procedure, health checks, runbooks, worker monitoring.                              |
| Pilot readiness    | 3-5 station pilot checklist, camera/zone setup, reviewers, reports, legal/privacy notes.             |

# 19. Recommended First Sprint

The first sprint should not attempt full multi-tenancy and CCTV in one pass. The correct first sprint is foundation and safety.

| **Day** | **Focus**                                    | **Outcome**                                                             |
|---------|----------------------------------------------|-------------------------------------------------------------------------|
| 1       | Repository cleanup and secret removal        | Safe codebase, ignore files, no real production env values.             |
| 2       | Production config review                     | APP_ENV behavior, worker startup separation plan, env templates.        |
| 3       | Docker Compose production draft              | Ubuntu-oriented compose file and deployment directory structure.        |
| 4       | Alembic planning and current schema snapshot | Migration strategy and first baseline migration branch.                 |
| 5       | Tenant data model design PR                  | Tenants/subscriptions/tenant settings model proposal and tests outline. |

# 20. Important Non-goals for the First Production Upgrade

- Do not build full real-time CCTV monitoring as the first version. Start with sampled/batch video analysis and reliable review workflows.

- Do not implement face recognition.

- Do not implement license-plate-based loyalty unless legal review and client approval exist.

- Do not turn every current function into microservices. Keep the architecture simple: web + workers + DB + Redis + storage.

- Do not overbuild billing payments initially. Store subscription/tier/limits now; payment provider integration can come later.

- Do not make the platform dependent on one AI provider. Add provider abstraction early.

- Do not let UI pages perform direct unscoped database queries after tenant model is introduced.

# 21. Final Recommendation

GentStationAI should be evolved in layers: first make the current application safe and deployable, then introduce tenant isolation and tiers, then add the public landing page, then build the Tier 2 CCTV foundation, and only after that expand into heavier video intelligence and integrations. This sequence protects the existing Tier 1 business value while creating a professional architecture capable of supporting multiple client companies.

The single most important rule for Codex is: do not implement isolated features that bypass tenant context, feature gates, audit logging, or production deployment discipline. Every new feature must be tenant-aware, tier-aware, testable, and deployable on the dedicated Ubuntu architecture.
