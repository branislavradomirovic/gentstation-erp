import os
from pathlib import Path

import psycopg2
import pytest
from alembic import command
from alembic.config import Config


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
RUN_DB_MIGRATION_TESTS = os.getenv("RUN_DB_MIGRATION_TESTS", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


@pytest.mark.skipif(
    not TEST_DATABASE_URL or not RUN_DB_MIGRATION_TESTS,
    reason="Set TEST_DATABASE_URL and RUN_DB_MIGRATION_TESTS=1 to run PostgreSQL migration integration tests.",
)
def test_alembic_upgrade_head_applies_multitenant_schema(tmp_path) -> None:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(config, "head")

    with psycopg2.connect(TEST_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tenants WHERE id = 1")
            assert cur.fetchone() == (1,)

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'tenant_id'
                """
            )
            assert cur.fetchone() == ("tenant_id",)
