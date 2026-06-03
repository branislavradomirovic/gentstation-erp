# 11. Owner Delivery Checklist

## Purpose

Use this checklist before sending the package to the external deployment team.

## Must provide

- `deployment-handoff/` folder
- repository URL or source bundle
- exact release tag or commit SHA
- deployment target decision: single VM
- the real production `.env` values or equivalent secure secrets handoff
- PostgreSQL dump if the team must recreate current data

If delivering by repository URL only, also provide separately:

- `deployment-handoff/vm/.env.vm.example` if the team should use the packaged VM template
- `deployment-handoff/vm/.env.production.template`
- `deployment-handoff/vm/.env.production.actual` if you want the one-folder VM handoff reproduced exactly

## Secrets and credentials to provide securely

- `DATABASE_URL` or DB host/name/user/password values
- `REDIS_URL` if not using the default VM compose internal Redis URL
- `INITIAL_ADMIN_USERNAME`
- `INITIAL_ADMIN_PASSWORD`
- `INITIAL_ADMIN_EMAIL`
- `TELEGRAM_BOT_TOKEN` if Telegram is enabled
- `TELEGRAM_BOT_URL`
- `TELEGRAM_BOT_HANDLE`
- `SMTP_SERVER`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS`
- `SENDER_EMAIL`
- `MANAGER_EMAIL`
- `SUPPORT_RECIPIENT`
- `APP_LOGIN_URL`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_VISION_MODEL`

## Data to provide if the team must recreate the current environment

- PostgreSQL dump file
- any required `uploads/` content
- any required `downloads/` content

## Decisions to communicate

- whether AI features are in scope on day one
- whether Telegram features are in scope on day one
- whether email features are in scope on day one
- whether Ollama will run on the same VM or on another host
- whether the deployment is temporary or intended for longer-term production use

## Recommended owner message to the team

The owner should explicitly tell the team:

- this deployment should use the single-VM Docker Compose path
- the goal is to recreate the current environment as closely as possible
- whether the supplied PostgreSQL dump is the authoritative production dataset
- which URL/domain should be used publicly

## Final pre-send check

Before sending, verify:

- docs are included
- secrets are complete
- database dump is recent enough
- release tag or commit SHA is fixed
- the team knows who to contact for application questions
- hidden `.env*` files are included if the handoff is being sent as an archive rather than a repo-only transfer
