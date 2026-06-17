from __future__ import annotations

from pathlib import Path

import psycopg2
import pytest
from alembic import command
from alembic.config import Config

from tests.db_test_utils import (
    create_isolated_schema,
    drop_isolated_schema,
    resolve_test_database_url,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def isolated_schema_url():
    base_url = resolve_test_database_url()
    try:
        schema_name, scoped_url = create_isolated_schema(base_url, prefix="alembic")
    except Exception as exc:
        pytest.skip(f"Postgres schema setup unavailable: {exc}")

    try:
        yield schema_name, scoped_url
    finally:
        drop_isolated_schema(base_url, schema_name)


def test_alembic_upgrade_head_applies_multitenant_schema(isolated_schema_url) -> None:
    schema_name, scoped_url = isolated_schema_url
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", scoped_url)
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(config, "head")

    with psycopg2.connect(scoped_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tenants WHERE id = 1")
            assert cur.fetchone() == (1,)

            cur.execute(
                """
                SELECT to_regclass(%s),
                       to_regclass(%s),
                       to_regclass(%s)
                """,
                (
                    f"{schema_name}.tenant_subscriptions",
                    f"{schema_name}.tenant_settings",
                    f"{schema_name}.tenant_feature_flags",
                ),
            )
            assert cur.fetchone() == (
                f"{schema_name}.tenant_subscriptions",
                f"{schema_name}.tenant_settings",
                f"{schema_name}.tenant_feature_flags",
            )

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'users' AND column_name = 'tenant_id'
                """,
                (schema_name,),
            )
            assert cur.fetchone() == ("tenant_id",)

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'users' AND column_name IN ('lifecycle_state', 'phone')
                ORDER BY column_name
                """,
                (schema_name,),
            )
            assert cur.fetchall() == [
                ("lifecycle_state",),
                ("phone",),
            ]

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'station_categories' AND column_name = 'tenant_id'
                """,
                (schema_name,),
            )
            assert cur.fetchone() == ("tenant_id",)

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = 'submissions' AND column_name = 'video_blob'
                """,
                (schema_name,),
            )
            assert cur.fetchone() == ("video_blob",)

            cur.execute(
                """
                SELECT to_regclass(%s),
                       to_regclass(%s),
                       to_regclass(%s),
                       to_regclass(%s),
                       to_regclass(%s)
                """,
                (
                    f"{schema_name}.integration_station_mappings",
                    f"{schema_name}.integration_import_batches",
                    f"{schema_name}.report_schedules",
                    f"{schema_name}.report_subscriptions",
                    f"{schema_name}.report_delivery_attempts",
                ),
            )
            assert cur.fetchone() == (
                f"{schema_name}.integration_station_mappings",
                f"{schema_name}.integration_import_batches",
                f"{schema_name}.report_schedules",
                f"{schema_name}.report_subscriptions",
                f"{schema_name}.report_delivery_attempts",
            )


def test_run_alembic_upgrade_repairs_missing_baseline_table_on_later_revision(
    isolated_schema_url, monkeypatch
) -> None:
    schema_name, scoped_url = isolated_schema_url
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", scoped_url)
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(config, "head")

    with psycopg2.connect(scoped_url) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DROP TABLE scheduled_reports CASCADE")
            cur.execute(
                """
                SELECT version_num
                FROM alembic_version
                """
            )
            original_revision = cur.fetchone()[0]
            assert original_revision

    monkeypatch.setenv("DATABASE_URL", scoped_url)
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("SQLALCHEMY_DATABASE_URL", raising=False)

    from core.schema_migrations import run_alembic_upgrade_to_head

    run_alembic_upgrade_to_head()

    with psycopg2.connect(scoped_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s)",
                (f"{schema_name}.scheduled_reports",),
            )
            assert cur.fetchone() == (f"{schema_name}.scheduled_reports",)
