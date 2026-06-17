# Production Deployment

This directory contains the Ubuntu production deployment bundle introduced in Phase 1.

Use it for dedicated-server deployments that run GentStationAI as separate services:

- `web`
- `ai-worker`
- `telegram-worker`
- `report-scheduler`
- `postgres`
- `redis`
- `reverse-proxy`
- optional `ollama`

Quick start:

1. Copy `env/.env.production.example` to `env/.env.production`.
2. Fill real secrets on the target Ubuntu server only.
3. Run `./deploy/scripts/deploy.sh` or `docker compose --env-file deploy/env/.env.production -f deploy/docker-compose.prod.yml up -d --build`.
4. Run `./deploy/scripts/healthcheck.sh` after deployment.
5. Complete `docs/production/LAUNCH_CHECKLIST.md` before pilot traffic.

Production guardrails:

- `app.py` does not spawn workers when `APP_ENV=production`.
- Workers run as dedicated containers.
- Healthcheck scripts live in `deploy/scripts/`.
- Reverse proxy traffic terminates at `reverse-proxy` and forwards to `web`.
- The production compose file is the Ubuntu entry point and does not include the CCTV worker yet.
- Resource limit defaults live in `deploy/env/.env.production.example` and should be tuned on the server before launch.
- The final smoke and launch checklists live in `docs/production/`.
