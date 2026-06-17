# GentStationAI Production Target

GentStationAI is intended to run on a dedicated Ubuntu 22.04 or 24.04 server
with Docker Engine and the Docker Compose plugin installed.

This repository keeps the production target intentionally simple:

- `web` runs the Streamlit application
- `ai-worker` processes video analysis jobs
- `telegram-worker` handles Telegram intake
- `report-scheduler` generates scheduled reports
- PostgreSQL stores application data
- Redis backs queues and short-lived state
- `reverse-proxy` terminates public traffic
- optional `ollama` can be added for local vision inference

Phase 0 guardrails:

- Do not commit real secrets or filled `.env` files.
- Keep deployment-specific values on the Ubuntu server only.
- Preserve the existing Tier 1 application behavior until later phases change it.
- Treat Render as legacy reference material, not the target production platform.
- Configure `APP_LOGIN_URL` for any staging, pre-production, or production deployment.
- `APP_BASE_URL` may be used as a fallback source for the same canonical URL if your deployment tooling already manages it.
- All pre-production credentials must be rotated before public production release or before loading real customer data.

Quick start on the server:

1. Copy the repository to the Ubuntu host.
2. Copy a sanitized env example to an untracked `.env`.
3. Fill in the real values on the server.
4. Launch the stack with the documented Docker Compose flow.

Operational checklists:

- `docs/production/LAUNCH_CHECKLIST.md`
- `docs/production/SMOKE_TEST_CHECKLIST.md`
- `deploy/PILOT_ONBOARDING.md`

This file is intentionally short and production-focused so it can serve as the
first checkpoint for the deployment path defined in the production readiness
plan.
