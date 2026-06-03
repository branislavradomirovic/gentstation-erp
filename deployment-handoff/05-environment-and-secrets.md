# 05. Environment Variables And Secrets

## Source of truth

The starting point for environment configuration is:

- `.env.example`

The deployment team should use that file as the basis for production configuration, but production secrets must not be committed to source control.

## Core required variables

### Database

Required for production:

```text
DATABASE_URL=<postgres connection string>
APP_ENV=production
RUN_SCHEMA_MIGRATIONS_ON_STARTUP=1
STRICT_SCHEMA_INIT=1
```

Notes:

- In production-like environments the application expects `DATABASE_URL`.
- The app does not safely fall back to localhost in production.

### Redis

Required if workers/background processing are used:

```text
REDIS_URL=redis://<host>:6379/0
```

### Admin bootstrap

Required for initial admin setup:

```text
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=<secure password>
INITIAL_ADMIN_EMAIL=<admin email>
```

### Streamlit/web runtime

Recommended:

```text
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_BROWSER_GATHERUSAGESTATS=false
APP_LOGIN_URL=https://<public app url>
```

## Worker control variables

### Web service

Use:

```text
AUTO_START_BACKGROUND_WORKERS=0
AUTO_START_TELEGRAM_BOT=0
AUTO_START_AI_WORKER=0
AUTO_START_REPORT_SCHEDULER=0
```

Reason:

- workers should be deployed as separate services
- the web container should not spawn long-running subprocesses in production

### Worker services

Use:

```text
SKIP_SCHEMA_INIT=1
```

Reason:

- avoids worker-side schema initialization and lowers the chance of startup conflicts

## Integration-specific variables

### Telegram

Required only if Telegram functionality is enabled:

```text
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_BOT_URL=https://t.me/<bot_username>
TELEGRAM_BOT_HANDLE=<bot_username>
```

### SMTP/email

Required only if email features are enabled:

```text
SMTP_SERVER=<smtp host>
SMTP_PORT=<smtp port>
SMTP_USER=<smtp user>
SMTP_PASS=<smtp password>
SENDER_EMAIL=<from email>
MANAGER_EMAIL=<manager email>
SUPPORT_RECIPIENT=<support email>
```

### AI/Ollama

Required only if AI features are enabled:

```text
OLLAMA_BASE_URL=http://<reachable-ollama-endpoint>:11434
OLLAMA_MODEL=bakllava:latest
OLLAMA_VISION_MODEL=bakllava:latest
OLLAMA_LOCAL_ONLY=1
VIDEO_FRAME_SAMPLES=6
VIDEO_MAX_FRAME_DIMENSION=768
```

Important notes:

- `OLLAMA_BASE_URL` must be reachable from the AI worker runtime.
- `localhost` only works if Ollama is in the same runtime environment, which is not the default AWS plan.
- The external team should confirm whether Ollama is separately deployed, externally hosted, or temporarily out of scope.

## Recommended secret handling

Store as secrets:

- `DATABASE_URL`
- `INITIAL_ADMIN_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `SMTP_PASS`
- any SMTP/API credentials

Store as plain environment variables if preferred:

- `APP_ENV`
- `RUN_SCHEMA_MIGRATIONS_ON_STARTUP`
- `STRICT_SCHEMA_INIT`
- `APP_LOGIN_URL`
- worker enable/disable flags
- non-sensitive tuning values

## Recommended service-specific variable sets

### Web service minimum

```text
APP_ENV=production
DATABASE_URL=<secret>
REDIS_URL=<secret or env>
RUN_SCHEMA_MIGRATIONS_ON_STARTUP=1
STRICT_SCHEMA_INIT=1
AUTO_START_BACKGROUND_WORKERS=0
AUTO_START_TELEGRAM_BOT=0
AUTO_START_AI_WORKER=0
AUTO_START_REPORT_SCHEDULER=0
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=<secret>
INITIAL_ADMIN_EMAIL=<email>
APP_LOGIN_URL=https://<public url>
```

### AI worker minimum

```text
APP_ENV=production
DATABASE_URL=<secret>
REDIS_URL=<secret or env>
SKIP_SCHEMA_INIT=1
OLLAMA_BASE_URL=<reachable endpoint>
OLLAMA_MODEL=bakllava:latest
OLLAMA_VISION_MODEL=bakllava:latest
```

### Telegram worker minimum

```text
APP_ENV=production
DATABASE_URL=<secret>
REDIS_URL=<secret or env>
SKIP_SCHEMA_INIT=1
TELEGRAM_BOT_TOKEN=<secret>
TELEGRAM_BOT_URL=https://t.me/<bot_username>
TELEGRAM_BOT_HANDLE=<bot_username>
```

### Report scheduler minimum

```text
APP_ENV=production
DATABASE_URL=<secret>
REDIS_URL=<secret or env>
SKIP_SCHEMA_INIT=1
```
