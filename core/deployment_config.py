from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_DIR = REPO_ROOT / "deploy"

PRODUCTION_ENV_VALUES = {"production", "prod"}
PRODUCTION_SERVICE_NAMES = (
    "web",
    "ai-worker",
    "telegram-worker",
    "report-scheduler",
    "postgres",
    "redis",
    "reverse-proxy",
)
PRODUCTION_OPTIONAL_SERVICE_NAMES = ("ollama",)

PRODUCTION_COMPOSE_FILE = DEPLOY_DIR / "docker-compose.prod.yml"
PRODUCTION_ENV_EXAMPLE_FILE = DEPLOY_DIR / "env" / ".env.production.example"
PRODUCTION_ENV_FILE = DEPLOY_DIR / "env" / ".env.production"
PRODUCTION_HEALTHCHECK_SCRIPT = DEPLOY_DIR / "scripts" / "healthcheck.sh"
PRODUCTION_WEB_HEALTHCHECK_SCRIPT = DEPLOY_DIR / "scripts" / "healthcheck_web.sh"
PRODUCTION_WORKER_HEALTHCHECK_SCRIPT = DEPLOY_DIR / "scripts" / "healthcheck_worker.sh"
PRODUCTION_BACKUP_SCRIPT = DEPLOY_DIR / "scripts" / "backup.sh"
PRODUCTION_RESTORE_SCRIPT = DEPLOY_DIR / "scripts" / "restore.sh"
PRODUCTION_RUNBOOK_FILE = DEPLOY_DIR / "scripts" / "RUNBOOKS.md"


def production_environment_defaults() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "AUTO_START_BACKGROUND_WORKERS": "0",
        "AUTO_START_TELEGRAM_BOT": "0",
        "AUTO_START_AI_WORKER": "0",
        "AUTO_START_REPORT_SCHEDULER": "0",
        "RUN_SCHEMA_MIGRATIONS_ON_STARTUP": "1",
        "STRICT_SCHEMA_INIT": "1",
        "SKIP_SCHEMA_INIT": "1",
    }
