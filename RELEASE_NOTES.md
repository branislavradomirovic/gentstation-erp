# GentStationAI Release Notes

## v1.0.0 - Production Readiness Release

### Included in this release
- Multi-tenant PostgreSQL architecture with RLS and fail-closed tenant context enforcement.
- Tier 1 AI Daily Operations workflows for Telegram intake, AI reporting, dashboards, alerts, and scheduled reports.
- Tier 2 CCTV Intelligence framework for cameras, zones, review workflows, CCTV job pipelines, and benchmarking.
- Provider-agnostic integration framework for POS, pump, loyalty, and inventory metadata, mappings, and CSV placeholder imports.
- Platform Superadmin tooling for tenant administration and production observability.
- Postgres-only media and evidence persistence for submissions, CCTV evidence, and import blobs.

### Production operations
- Ubuntu/Docker Compose deployment bundle with dedicated web and worker services.
- Health checks for services, queue backlog, worker heartbeats, and disk pressure.
- Postgres-only backup and restore scripts plus incident runbooks.
- Launch, smoke-test, and pilot onboarding checklists.

### Security and isolation
- Tenant-scoped report, benchmarking, integration, and CCTV data paths.
- Platform Health restricted to Platform Superadmins only.
- Structured activity logging for production observability.

### Remaining risks
- Live deployment validation against the target Ubuntu server is still required after any new environment or DB restore.
- CCTV worker is not yet included in the default production compose stack, so Tier 2 operations need an explicit rollout decision.
- Resource limits in Docker Compose are defined as operator defaults and may need host-specific tuning before sustained AI workloads.
- Ollama/model availability and model quality remain operational dependencies outside the application codebase.
