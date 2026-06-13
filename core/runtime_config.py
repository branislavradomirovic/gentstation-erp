from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv


TRUE_VALUES = {"1", "true", "yes", "on"}
PRODUCTION_ENVS = {"production", "prod"}


def env_bool(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in TRUE_VALUES


def app_env() -> str:
    return os.getenv("APP_ENV", "").strip().lower()


def is_production_env() -> bool:
    render_flag = os.getenv("RENDER", "").strip().lower()
    render_service = os.getenv("RENDER_SERVICE_ID", "").strip()
    return (
        app_env() in PRODUCTION_ENVS
        or render_flag in TRUE_VALUES
        or bool(render_service)
    )


@lru_cache(maxsize=1)
def load_runtime_env() -> bool:
    """Load `.env` only for local or notebook-style development workflows."""
    if is_production_env():
        return False
    load_dotenv()
    return True


def should_spawn_embedded_workers() -> bool:
    """The web app may spawn helper workers only outside production."""
    return not is_production_env()


def background_workers_enabled_by_env() -> bool:
    default_worker_start = os.getenv("AUTO_START_BACKGROUND_WORKERS_DEFAULT", "0")
    global_worker_start = env_bool(
        "AUTO_START_BACKGROUND_WORKERS", default_worker_start
    )
    individual_flags = (
        env_bool("AUTO_START_TELEGRAM_BOT", default_worker_start),
        env_bool("AUTO_START_AI_WORKER", default_worker_start),
        env_bool("AUTO_START_REPORT_SCHEDULER", default_worker_start),
    )
    return global_worker_start or any(individual_flags)
