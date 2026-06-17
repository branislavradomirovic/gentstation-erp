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
    """
    Standardized Alembic configuration loader.
    Ensures absolute paths and avoids interpolation errors by using a dummy URL.
    """
    config = Config(str(ALEMBIC_INI_PATH.resolve()))
    config.config_ini_section = "alembic"
    # Ensure the script_location is an absolute path to the migrations folder
    config.set_main_option("script_location", str(MIGRATIONS_PATH.resolve()))
    # CRITICAL: Do not store the real URL in the Config object.
    # Alembic's ConfigParser triggers KeyError during interpolation if passwords contain '%'.
    # Since env.py overrides the URL via core.database, we use a safe dummy here.
    config.set_main_option("sqlalchemy.url", "postgresql://user:pass@localhost/placeholder")  # pragma: allowlist secret
    return config

def run_alembic_upgrade_to_head() -> None:
    if not alembic_assets_present():
        logger.warning("Alembic assets are missing; skipping migration run.")
        return

    config = get_alembic_config()

    from sqlalchemy import create_engine, inspect, text
    # Use the real URL directly for the engine, bypassing Alembic's Config interpolation
    engine = create_engine(_migration_database_url())

    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())

        has_alembic_version = "alembic_version" in tables
        # Define the set of tables that *must* exist for the baseline to be considered present.
        CORE_BASELINE_TABLES = {
            "station_categories",
            "regions",
            "stations",
            "users",
            "sessions",
            "activity_logs",
            "submissions",
            "ai_alerts",
            "slow_query_logs",
            "system_settings",
            "worker_health_logs",
            "redis_health_logs",
            "ai_inference_latency",
            "scheduled_reports",
            "ai_jobs",
            "ai_reports",
        }
        # Check if *any* of the core baseline tables exist.
        # This indicates a pre-Alembic database that needs to be stamped.
        any_core_table_exists = any(t in tables for t in CORE_BASELINE_TABLES)
        all_core_tables_exist = all(t in tables for t in CORE_BASELINE_TABLES)

        if has_alembic_version:
            # Check for ghost revisions from previous development phases
            res = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            current_db_rev = res[0] if res else None
            if any_core_table_exists and not all_core_tables_exist:
                logger.warning(
                    "Database is stamped at revision %s, but the baseline schema is only partially present. "
                    "Truncating alembic_version so the idempotent baseline migration can repair missing tables before later revisions run.",
                    current_db_rev,
                )
                conn.execute(text("TRUNCATE TABLE alembic_version"))
                logger.info("Cleared alembic_version row for partial baseline repair.")
                current_db_rev = None
            if current_db_rev is None and all_core_tables_exist:
                logger.warning(
                    "Alembic version table exists but contains no revision row while core tables are present. "
                    "Stamping database at baseline revision 89a5e1d5e3c2 to prevent DuplicateTable errors."  # pragma: allowlist secret
                )
                conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('89a5e1d5e3c2')"))  # pragma: allowlist secret
                logger.info("Inserted missing alembic baseline revision 89a5e1d5e3c2.")
            elif current_db_rev is None and any_core_table_exists:
                logger.warning(
                    "Alembic version table exists but the baseline schema is only partially present. "
                    "Leaving the revision unset so the idempotent baseline migration can repair missing tables."
                )
            # Re-stamp if database is stuck on a revision ID that no longer exists in the filesystem
            elif current_db_rev in ["20260613_0001", "20260613_0002", "0f1e2d3c4b5a"]:  # pragma: allowlist secret
                logger.warning(
                    "Ghost revision %s detected in database. Re-stamping to %s to restore linear history.",
                    current_db_rev, "89a5e1d5e3c2"  # pragma: allowlist secret
                )
                # Use raw SQL to force the version update.
                # alembic.command.stamp can fail if the current DB revision is unknown to the filesystem.
                conn.execute(text("UPDATE alembic_version SET version_num = '89a5e1d5e3c2'"))  # pragma: allowlist secret
                logger.info("Successfully forced database stamp to 89a5e1d5e3c2 via SQL.")
            # If alembic_version exists but core tables are missing, it's an inconsistent state.
            # Truncate alembic_version to force a full re-run of all migrations from scratch.
            elif not any_core_table_exists:
                logger.warning(
                    "Alembic version table exists (%s), but core baseline tables are missing. "
                    "Database is in an inconsistent state. Truncating alembic_version to force re-run of migrations.",
                    current_db_rev
                )
                conn.execute(text("TRUNCATE TABLE alembic_version"))
                logger.info("Successfully truncated alembic_version table.")
        elif all_core_tables_exist: # No alembic_version table, but all core tables are present. This is a full legacy DB.
            logger.warning(
                "Legacy database detected (no alembic_version table, but core tables exist). "
                "Stamping database at baseline revision 89a5e1d5e3c2 to prevent DuplicateTable errors."  # pragma: allowlist secret
            )
            # Explicitly create alembic_version table and insert the baseline revision
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('89a5e1d5e3c2')"))  # pragma: allowlist secret
            logger.info("Created alembic_version table and stamped to 89a5e1d5e3c2 via SQL.")
        elif any_core_table_exists:
            logger.warning(
                "Legacy database detected with only a partial baseline schema present. "
                "Running the idempotent baseline migration from scratch to repair missing tables."
            )
        else: # Fresh DB
            logger.info(
                "No alembic_version table and incomplete baseline detected. Running full upgrade from scratch."
            )
            # No stamp needed, command.upgrade('head') will start from None and create all tables.

    logger.info("Running Alembic migrations to head.")
    command.upgrade(config, "head")

    # Final verification: fetch and log the current revision from the database
    from alembic.runtime.migration import MigrationContext
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()
        logger.info("Migration successful. Database is now at revision: %s", current_rev)

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
