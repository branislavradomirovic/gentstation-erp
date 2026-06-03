# 02. Architecture

## Logical components

### 1. Web application

Purpose:

- Hosts the user-facing Streamlit application
- Serves dashboards, settings, map views, reports, audit pages, and admin pages

Container command:

```bash
python -m streamlit run app.py --server.port=8501 --server.address=0.0.0.0
```

Source references:

- `app.py`
- `Dockerfile`

### 2. AI worker

Purpose:

- Processes AI-related background jobs
- Connects to Redis and PostgreSQL
- Calls the Ollama API endpoint configured by environment variables

Container command:

```bash
python -m core.ai_worker
```

Source references:

- `core/ai_worker.py`
- `core/video_processor.py`

### 3. Telegram worker

Purpose:

- Runs the Telegram bot integration
- Requires `TELEGRAM_BOT_TOKEN`
- Connects to PostgreSQL and Redis

Container command:

```bash
python -m core.bot_worker
```

Source references:

- `core/bot_worker.py`

### 4. Report scheduler

Purpose:

- Runs scheduled reporting/background scheduling tasks
- Connects to PostgreSQL and Redis

Container command:

```bash
python -m core.report_scheduler
```

Source references:

- `core/report_scheduler.py`

### 5. PostgreSQL

Purpose:

- Primary system of record
- Stores users, application data, audit data, station metadata, logs, session-related data, and other operational records

Observed behavior:

- The application prefers `DATABASE_URL` in production-like environments.
- In production-like environments, the app does not fall back to localhost if `DATABASE_URL` is missing.
- The app can run schema initialization on startup when enabled.

Source references:

- `core/database.py`
- `.env.example`

### 6. Redis

Purpose:

- Supports worker coordination and application background processing behavior

Source references:

- `.env.example`
- `core/database.py`

### 7. Ollama

Purpose:

- External AI inference endpoint for AI/vision-related functionality

Important note:

- This application does not package Ollama in the main Docker image.
- The deployment team must provide a reachable Ollama endpoint if AI functionality is required.

Source references:

- `.env.example`
- `core/video_processor.py`

## Recommended network flow

1. Users access the application through HTTPS on an Application Load Balancer.
2. The load balancer forwards traffic to the ECS Fargate `web` service.
3. The `web` service connects to:
   - RDS PostgreSQL
   - ElastiCache Redis
   - optional SMTP provider
4. The workers connect to:
   - RDS PostgreSQL
   - ElastiCache Redis
   - Telegram API for bot functionality
   - Ollama endpoint for AI functionality
   - SMTP provider where required

## Service separation requirements

The deployment team should preserve service separation:

- `web` must be its own ECS service
- `ai-worker` must be its own ECS service
- `telegram-worker` must be its own ECS service
- `report-scheduler` must be its own ECS service

Do not rely on the web process auto-spawning workers in production.

Recommended production environment flags for the web service:

```text
AUTO_START_BACKGROUND_WORKERS=0
AUTO_START_AI_WORKER=0
AUTO_START_TELEGRAM_BOT=0
AUTO_START_REPORT_SCHEDULER=0
```

Recommended production environment flags for worker services:

```text
SKIP_SCHEMA_INIT=1
```
