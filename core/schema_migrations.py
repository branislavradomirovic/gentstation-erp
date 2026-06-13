from __future__ import annotations

import logging
import os
import urllib.parse
from pathlib import Path

from alembic import command
from alembic.config import Config


logger = logging.getLogger("gentstation.schema_migrations")
ALEMBIC_INI_PATH = Path(__file__).resolve().parents[1] / "alembic.ini"
MIGRATIONS_PATH = Path(__file__).resolve().parents[1] / "migrations"


def alembic_assets_present() -> bool:
    return ALEMBIC_INI_PATH.exists() and MIGRATIONS_PATH.exists()


def get_alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", _migration_database_url())
    return config


def run_alembic_upgrade_to_head() -> None:
    if not alembic_assets_present():
        logger.warning("Alembic assets are missing; skipping migration run.")
        return

    logger.info("Running Alembic migrations to head.")
    command.upgrade(get_alembic_config(), "head")


def _migration_database_url() -> str:
    database_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URL")
    )
    if database_url:
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql+psycopg2://", 1)
        if database_url.startswith("postgresql://"):
            return database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return database_url

    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "gentstation")
    user = os.getenv("DB_USER", "gentstation_user")
    password = urllib.parse.quote_plus(
        os.getenv("DB_PASSWORD", "change_me_for_local_dev")
    )
    sslmode = os.getenv("DB_SSLMODE", "").strip()
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    if sslmode:
        url += f"?sslmode={urllib.parse.quote_plus(sslmode)}"
    return url
