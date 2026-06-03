# 01. Overview

## Application summary

GentStationAI is a Python application used for gas-station operations management. It provides:

- a Streamlit web application
- station dashboards and maps
- reporting and audit functionality
- AI-assisted processing and monitoring
- Telegram bot workflows
- email notifications
- scheduled background jobs

## Technology stack

- Python 3.11
- Streamlit
- PostgreSQL
- Redis
- SQLAlchemy and psycopg2
- Optional Ollama-based AI service integration
- Docker for packaging

## Deployment model

This application should not be deployed as a single monolithic process in production.

The intended production layout is:

- one `web` service for the Streamlit application
- one `ai-worker` service
- one `telegram-worker` service
- one `report-scheduler` service
- one PostgreSQL database
- one Redis instance

The repository already reflects this deployment shape in:

- `Dockerfile`
- `README.md`
- `render.yaml`

## Important production behavior

- The web process is intended to run independently from workers.
- Worker auto-start should remain disabled in production.
- Database schema initialization is performed by the application at startup when enabled.
- Worker processes are designed to skip schema initialization to reduce startup conflicts.
- Redis is required for worker-related functionality.
- Ollama is optional only if AI features are intentionally disabled; otherwise it must be reachable from the AI worker.

## Primary recommendation for AWS

Use Amazon ECS Fargate with separate services for the web app and each worker, plus managed PostgreSQL and Redis.

This is the easiest AWS setup that still matches the application’s architecture and minimizes server administration.
