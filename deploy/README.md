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
3. Run `docker compose -f deploy/docker-compose.prod.yml up -d --build`.

Production guardrails:

- `app.py` does not spawn workers when `APP_ENV=production`.
- Workers run as dedicated containers.
- Healthcheck scripts live in `deploy/scripts/`.
- Reverse proxy traffic terminates at `reverse-proxy` and forwards to `web`.
