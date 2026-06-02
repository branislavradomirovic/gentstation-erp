# GentStationAI

GentStationAI is a Streamlit operations application for gas-station management, AI-assisted video review, alerts, audit logs, and Telegram/email workflows.

## Local Development

The recommended notebook workflow is:

1. Start infrastructure only:

```bash
docker compose up -d postgres redis
```

2. Create a local `.env` from `.env.example` and keep the local-first defaults:

```text
DB_HOST=localhost
REDIS_URL=redis://localhost:6379/0
APP_ENV=development
AUTO_START_BACKGROUND_WORKERS=0
```

3. Install app dependencies locally:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

4. Run the web app from the notebook:

```bash
streamlit run app.py
```

5. Start workers only when you need Telegram intake or AI processing:

```bash
python -m core.bot_worker
python -m core.ai_worker
```

If you want the whole stack in Docker, use profiles:

```bash
docker compose --profile app --profile workers up --build
```

## Render Deployment

The repo includes a `render.yaml` blueprint for the eventual Docker deployment to Render.

Expected production shape:

- `web` service running the Streamlit app from `Dockerfile`
- `ai-worker` service running `python -m core.ai_worker`
- `telegram-worker` service running `python -m core.bot_worker`
- managed PostgreSQL
- managed Redis / Key Value

Important production env vars:

```text
APP_ENV=production
DATABASE_URL=<render postgres connection string>
REDIS_URL=<render key value connection string>
RUN_SCHEMA_MIGRATIONS_ON_STARTUP=1
STRICT_SCHEMA_INIT=1
AUTO_START_BACKGROUND_WORKERS=0
AUTO_START_AI_WORKER=0
AUTO_START_TELEGRAM_BOT=0
APP_LOGIN_URL=https://<your-render-domain>
```

The app and workers are designed to run as separate services. The web app does not need to spawn worker subprocesses in production.

## Notes

- Session tokens are stored hashed in the database.
- Password reset still uses a temporary-password email flow; that is acceptable for development but should be replaced with one-time reset links before a true production launch.
- `ensure_schema()` is still the active schema bootstrap path. It is usable for local development, but the long-term next step is a real Alembic migration chain.
