---
title: Genstationai
emoji: G
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8501
pinned: false
license: apache-2.0
short_description: Generative AI operations dashboard for gas stations
---

# GentStationAI

GentStationAI is a Streamlit operations dashboard for gas-station network management, role-based administration, AI-assisted video review, alerts, audit logs, and Telegram/email workflows.

## Hugging Face Space MVP Deployment

Create the Space as a **Docker Space** and push this repository. The Space runs the `Dockerfile` and serves Streamlit on port `8501`.

Set these in **Settings -> Variables and secrets**:

| Name | Type | Required | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | Secret | Yes | Managed Postgres URL, for example from Supabase, Neon, Railway, or Render. Use SSL when your provider requires it. |
| `APP_ENV` | Variable | Yes | Set to `production`. |
| `RUN_SCHEMA_MIGRATIONS_ON_STARTUP` | Variable | MVP yes | Set to `1` for the first MVP deploy so the app creates its schema. Move to managed migrations before real production. |
| `STRICT_SCHEMA_INIT` | Variable | Recommended | Set to `1` so schema errors fail loudly. |
| `AUTO_START_BACKGROUND_WORKERS` | Variable | Recommended | Set to `0` for the Space MVP. |
| `AUTO_START_TELEGRAM_BOT` | Variable | Recommended | Set to `0` unless you provide Redis and want the bot process in the Space. |
| `AUTO_START_AI_WORKER` | Variable | Recommended | Set to `0` unless you provide Redis/Ollama and want AI processing in the Space. |
| `INITIAL_ADMIN_USERNAME` | Secret | First deploy | Optional, defaults to `admin` when `INITIAL_ADMIN_PASSWORD` is set. |
| `INITIAL_ADMIN_PASSWORD` | Secret | First deploy | Creates the first General Manager account if it does not already exist. Remove or rotate after first login. |
| `INITIAL_ADMIN_EMAIL` | Secret | Recommended | Email for the initial General Manager. |
| `OLLAMA_BASE_URL` | Secret or variable | Optional | External Ollama endpoint if AI video analysis is enabled. |
| `REDIS_URL` | Secret | Optional | External Redis URL if Telegram/worker flow is enabled. |
| `TELEGRAM_BOT_TOKEN` | Secret | Optional | Required only for Telegram intake. |
| `SMTP_USER` / `SMTP_PASS` | Secrets | Optional | Required only for email notifications/password reset. |

For MVP testing on Hugging Face, start with the web UI, database-backed administration, dashboards, audit logs, and manual data flows. Keep background workers disabled until the external Redis and AI endpoint are ready.

## Local Docker

Run the full local stack:

```bash
docker compose up --build
```

Local Compose includes PostgreSQL, Redis, the Streamlit app, a Telegram worker, and an AI worker. The app service intentionally does not spawn worker subprocesses; workers run as separate services.

## Security Notes

- Do not commit `.env` files or secrets.
- Use Hugging Face Space secrets for credentials.
- Session tokens are kept out of URLs.
- Password reset still uses a temporary-password email flow for MVP only; replace it with one-time reset links before production.
- `RUN_SCHEMA_MIGRATIONS_ON_STARTUP=1` is acceptable for MVP bootstrap, but production should use versioned Alembic migrations.
