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

## Production Target

The supported production target is a dedicated Ubuntu server running Docker Compose with separate services for:

- `web` running the Streamlit app from `Dockerfile`
- `ai-worker` running `python -m core.ai_worker`
- `telegram-worker` running `python -m core.bot_worker`
- `report-scheduler` running `python -m core.report_scheduler`
- PostgreSQL
- Redis
- reverse proxy and backups outside the app container set

Start with the Production Guide in docs/production/README.md.

Important production notes:
- Do not commit `.env` or production env files.
- Keep the web app and workers as separate containers in production.
- Preserve current Tier 1 behavior until later multi-tenant phases explicitly change it.
- `render.yaml` remains in the repo only as a legacy reference and is not the production deployment target.

## Notes

- Session tokens are stored hashed in the database.
- Password reset still uses a temporary-password email flow; that is acceptable for development but should be replaced with one-time reset links before a true production launch.
- `ensure_schema()` is still the active schema bootstrap path. It is usable for local development, but the long-term next step is a real Alembic migration chain.
